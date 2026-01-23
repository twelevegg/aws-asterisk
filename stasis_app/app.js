/**
 * Stasis Application for Linphone SIP Integration
 *
 * This app handles incoming calls and creates ExternalMedia channels
 * to forward RTP audio to a UDP endpoint (Python receiver).
 *
 * Flow:
 * 1. Incoming call triggers StasisStart event
 * 2. Create ExternalMedia channel pointing to UDP receiver
 * 3. Create mixing bridge to connect both channels
 * 4. RTP audio flows to UDP receiver for processing
 */

const AriClient = require('ari-client');

// Configuration from environment variables
const ARI_URL = process.env.ARI_URL || 'http://127.0.0.1:8088/ari';
const ARI_USERNAME = process.env.ARI_USERNAME || 'asterisk';
const ARI_PASSWORD = process.env.ARI_PASSWORD || 'asterisk';
const EXTERNAL_MEDIA_HOST = process.env.EXTERNAL_MEDIA_HOST || '127.0.0.1';
const EXTERNAL_MEDIA_PORT = process.env.EXTERNAL_MEDIA_PORT || '12345';
const STASIS_APP_NAME = 'linphone-handler';

console.log('='.repeat(60));
console.log('Stasis Application Starting');
console.log('='.repeat(60));
console.log(`ARI URL: ${ARI_URL}`);
console.log(`External Media: ${EXTERNAL_MEDIA_HOST}:${EXTERNAL_MEDIA_PORT}`);
console.log('='.repeat(60));

// Track active bridges for cleanup
const activeBridges = new Map();

async function main() {
    try {
        // Connect to ARI
        const client = await AriClient.connect(ARI_URL, ARI_USERNAME, ARI_PASSWORD);
        console.log(`[INFO] Connected to ARI at ${ARI_URL}`);

        // Handle incoming calls (StasisStart event)
        client.on('StasisStart', async (event, channel) => {
            const callerId = channel.caller.number || 'Unknown';
            const channelId = channel.id;

            console.log('\n' + '='.repeat(60));
            console.log(`[CALL] Incoming call from: ${callerId}`);
            console.log(`[CALL] Channel ID: ${channelId}`);
            console.log('='.repeat(60));

            try {
                // Answer the channel
                await channel.answer();
                console.log(`[INFO] Channel answered: ${channelId}`);

                // Create ExternalMedia channel
                const externalChannel = await client.channels.externalMedia({
                    app: STASIS_APP_NAME,
                    external_host: `${EXTERNAL_MEDIA_HOST}:${EXTERNAL_MEDIA_PORT}`,
                    format: 'ulaw',
                    encapsulation: 'rtp',
                    transport: 'udp',
                    connection_type: 'client',
                    direction: 'both',
                    data: `call_${channelId}`
                });

                console.log(`[INFO] ExternalMedia channel created: ${externalChannel.id}`);
                console.log(`[INFO] RTP will be sent to: ${EXTERNAL_MEDIA_HOST}:${EXTERNAL_MEDIA_PORT}`);

                // Create mixing bridge
                const bridge = await client.bridges.create({
                    type: 'mixing',
                    name: `bridge_${channelId}`
                });
                console.log(`[INFO] Bridge created: ${bridge.id}`);

                // Store bridge info for cleanup
                activeBridges.set(channelId, {
                    bridge: bridge,
                    externalChannel: externalChannel
                });

                // Add channels to bridge
                await bridge.addChannel({ channel: [channel.id, externalChannel.id] });
                console.log(`[INFO] Channels added to bridge`);
                console.log(`[INFO] Audio is now flowing to UDP ${EXTERNAL_MEDIA_HOST}:${EXTERNAL_MEDIA_PORT}`);

            } catch (err) {
                console.error(`[ERROR] Failed to setup call: ${err.message}`);
                try {
                    await channel.hangup();
                } catch (e) {
                    console.debug(`[DEBUG] Hangup after error: ${e.message}`);
                }
            }
        });

        // Handle call end (StasisEnd event)
        client.on('StasisEnd', async (event, channel) => {
            const channelId = channel.id;
            console.log(`\n[CALL END] Channel ended: ${channelId}`);

            // Cleanup bridge and external channel
            const resources = activeBridges.get(channelId);
            if (resources) {
                try {
                    if (resources.externalChannel) {
                        await resources.externalChannel.hangup();
                        console.log(`[CLEANUP] External channel destroyed`);
                    }
                } catch (e) {
                    if (!e.message?.includes('not found')) {
                        console.debug(`[DEBUG] External channel cleanup: ${e.message}`);
                    }
                }

                try {
                    if (resources.bridge) {
                        await resources.bridge.destroy();
                        console.log(`[CLEANUP] Bridge destroyed`);
                    }
                } catch (e) {
                    if (!e.message?.includes('not found')) {
                        console.debug(`[DEBUG] Bridge cleanup: ${e.message}`);
                    }
                }

                activeBridges.delete(channelId);
            }
        });

        // Handle channel destroyed event
        client.on('ChannelDestroyed', (event, channel) => {
            console.log(`[EVENT] Channel destroyed: ${channel.id}`);
        });

        // Start the Stasis application
        await client.start(STASIS_APP_NAME);
        console.log(`[INFO] Stasis app '${STASIS_APP_NAME}' started and listening for calls...`);
        console.log('[INFO] Waiting for incoming calls to youngho@sip.linphone.org');

    } catch (err) {
        console.error(`[FATAL] Failed to connect to ARI: ${err.message}`);
        console.error('[HINT] Make sure Asterisk is running and ARI is enabled');
        process.exit(1);
    }
}

// Handle graceful shutdown
process.on('SIGINT', async () => {
    console.log('\n[INFO] Shutting down...');

    // Cleanup all active bridges
    for (const [channelId, resources] of activeBridges) {
        try {
            if (resources.bridge) {
                await resources.bridge.destroy();
                console.log(`[SHUTDOWN] Bridge ${channelId} destroyed`);
            }
        } catch (e) {
            console.debug(`[SHUTDOWN] Bridge cleanup: ${e.message}`);
        }
    }

    process.exit(0);
});

process.on('SIGTERM', () => {
    process.emit('SIGINT');
});

// Start the application
main();
