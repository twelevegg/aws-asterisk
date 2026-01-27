/**
 * AICC Stasis App - Dual Snoop with Agent Dial
 *
 * Flow:
 * 1. Customer calls youngho@sip.linphone.org
 * 2. Asterisk answers and dials agent02
 * 3. Both channels connected via bridge
 * 4. Dual Snoop separates audio:
 *    - Customer (in) → UDP:12345
 *    - Agent (out) → UDP:12346
 */

const AriClient = require('ari-client');
const { v4: uuidv4 } = require('uuid');

// Configuration
const ARI_URL = process.env.ARI_URL || 'http://127.0.0.1:8088/ari';
const ARI_USERNAME = process.env.ARI_USERNAME || 'asterisk';
const ARI_PASSWORD = process.env.ARI_PASSWORD;  // Required - no default
const EXTERNAL_HOST = process.env.EXTERNAL_HOST || '127.0.0.1';
const CUSTOMER_PORT = process.env.CUSTOMER_PORT || '12345';
const AGENT_PORT = process.env.AGENT_PORT || '12346';
const STASIS_APP_NAME = 'linphone-handler';
const AGENT_ENDPOINT = process.env.AGENT_ENDPOINT || 'PJSIP/agent02';
const DIAL_TIMEOUT = 30; // seconds

// Validate required environment variables
if (!ARI_PASSWORD) {
    console.error('FATAL: ARI_PASSWORD environment variable is required');
    console.error('Set it with: export ARI_PASSWORD=your_secure_password');
    process.exit(1);
}

console.log('='.repeat(60));
console.log('AICC Stasis App - Dual Snoop with Agent Dial');
console.log('='.repeat(60));
console.log(`ARI URL: ${ARI_URL}`);
console.log(`Customer audio → UDP:${CUSTOMER_PORT}`);
console.log(`Agent audio → UDP:${AGENT_PORT}`);
console.log(`Agent endpoint: ${AGENT_ENDPOINT}`);
console.log('='.repeat(60));

// Track active calls
const activeCalls = new Map();

async function main() {
    try {
        const client = await AriClient.connect(ARI_URL, ARI_USERNAME, ARI_PASSWORD);
        console.log('[INFO] Connected to ARI');

        client.on('StasisStart', async (event, channel) => {
            const channelName = channel.name || '';

            // Skip helper channels (Snoop, ExternalMedia, etc.)
            if (channelName.includes('UnicastRTP') ||
                channelName.includes('Snoop') ||
                channelName.includes('ExternalMedia')) {
                console.log(`[DEBUG] Ignoring helper channel: ${channelName}`);
                return;
            }

            // Skip agent channel (will be handled separately)
            if (channelName.includes('agent02')) {
                console.log(`[DEBUG] Agent channel joined: ${channelName}`);
                return;
            }

            const callId = uuidv4();
            const callerNumber = channel.caller.number || 'Unknown';

            console.log('\n' + '='.repeat(60));
            console.log(`[${callId}] Incoming call from: ${callerNumber}`);
            console.log(`[${callId}] Customer channel: ${channel.id}`);
            console.log('='.repeat(60));

            try {
                // 1. Answer the customer channel
                await channel.answer();
                console.log(`[${callId}] Customer channel answered`);

                // 2. Create main bridge for customer <-> agent
                const mainBridge = await client.bridges.create({
                    type: 'mixing',
                    name: `main_${callId}`
                });
                console.log(`[${callId}] Main bridge created: ${mainBridge.id}`);

                // 3. Add customer to main bridge
                await mainBridge.addChannel({ channel: channel.id });
                console.log(`[${callId}] Customer added to bridge`);

                // 4. Dial agent02
                console.log(`[${callId}] Dialing ${AGENT_ENDPOINT}...`);
                const agentChannel = await client.channels.originate({
                    endpoint: AGENT_ENDPOINT,
                    app: STASIS_APP_NAME,
                    appArgs: `dialed_${callId}`,
                    callerId: callerNumber,
                    timeout: DIAL_TIMEOUT
                });
                console.log(`[${callId}] Agent channel created: ${agentChannel.id}`);

                // Store call data for tracking
                const callData = {
                    callId,
                    callerNumber,
                    startTime: new Date(),
                    customerChannel: channel.id,
                    agentChannel: agentChannel.id,
                    mainBridge: mainBridge.id,
                    resources: []
                };
                activeCalls.set(channel.id, callData);
                activeCalls.set(agentChannel.id, callData); // Also index by agent channel

                // 5. Wait for agent to answer, then setup snoop
                agentChannel.on('StasisStart', async () => {
                    console.log(`[${callId}] Agent answered!`);

                    try {
                        // Add agent to main bridge
                        await mainBridge.addChannel({ channel: agentChannel.id });
                        console.log(`[${callId}] Agent added to bridge - Call connected!`);

                        // 6. Setup Dual Snoop for audio separation
                        await setupDualSnoop(client, channel, callData);

                    } catch (err) {
                        console.error(`[${callId}] Error setting up call:`, err.message);
                    }
                });

                // Handle agent channel end
                agentChannel.on('StasisEnd', () => {
                    console.log(`[${callId}] Agent hung up`);
                    cleanup(client, callData);
                });

                // Handle agent dial failure
                agentChannel.on('ChannelDestroyed', () => {
                    if (!callData.connected) {
                        console.log(`[${callId}] Agent did not answer`);
                        cleanup(client, callData);
                    }
                });

            } catch (err) {
                console.error(`[${callId}] Error:`, err.message);
                try {
                    await channel.hangup();
                } catch (e) {
                    // Ignore hangup errors
                }
            }
        });

        client.on('StasisEnd', async (event, channel) => {
            const callData = activeCalls.get(channel.id);
            if (callData && channel.id === callData.customerChannel) {
                const duration = (new Date() - callData.startTime) / 1000;
                console.log(`\n[${callData.callId}] Customer hung up - Duration: ${duration.toFixed(1)}s`);
                cleanup(client, callData);
            }
        });

        await client.start(STASIS_APP_NAME);
        console.log('\n[INFO] Waiting for calls to youngho@sip.linphone.org...\n');

    } catch (err) {
        console.error('[FATAL] Failed to connect to ARI:', err.message);
        process.exit(1);
    }
}

async function setupDualSnoop(client, customerChannel, callData) {
    const { callId } = callData;

    try {
        // Snoop for Customer audio (what customer says - 'in' direction)
        const customerSnoop = await client.channels.snoopChannel({
            channelId: customerChannel.id,
            app: STASIS_APP_NAME,
            spy: 'in',
            whisper: 'none'
        });
        console.log(`[${callId}] Customer Snoop created (spy: in)`);
        callData.resources.push({ type: 'channel', id: customerSnoop.id });

        // Bridge + ExternalMedia for Customer
        const customerBridge = await client.bridges.create({ type: 'mixing' });
        callData.resources.push({ type: 'bridge', id: customerBridge.id });

        const customerExternal = await client.channels.externalMedia({
            app: STASIS_APP_NAME,
            external_host: `${EXTERNAL_HOST}:${CUSTOMER_PORT}`,
            format: 'ulaw',
            encapsulation: 'rtp',
            transport: 'udp',
            connection_type: 'client',
            direction: 'both'
        });
        callData.resources.push({ type: 'channel', id: customerExternal.id });

        await customerBridge.addChannel({ channel: customerSnoop.id });
        await customerBridge.addChannel({ channel: customerExternal.id });
        console.log(`[${callId}] Customer audio → UDP:${CUSTOMER_PORT}`);

        // Snoop for Agent audio (what agent says - 'out' direction)
        const agentSnoop = await client.channels.snoopChannel({
            channelId: customerChannel.id,
            app: STASIS_APP_NAME,
            spy: 'out',
            whisper: 'none'
        });
        console.log(`[${callId}] Agent Snoop created (spy: out)`);
        callData.resources.push({ type: 'channel', id: agentSnoop.id });

        // Bridge + ExternalMedia for Agent
        const agentBridge = await client.bridges.create({ type: 'mixing' });
        callData.resources.push({ type: 'bridge', id: agentBridge.id });

        const agentExternal = await client.channels.externalMedia({
            app: STASIS_APP_NAME,
            external_host: `${EXTERNAL_HOST}:${AGENT_PORT}`,
            format: 'ulaw',
            encapsulation: 'rtp',
            transport: 'udp',
            connection_type: 'client',
            direction: 'both'
        });
        callData.resources.push({ type: 'channel', id: agentExternal.id });

        await agentBridge.addChannel({ channel: agentSnoop.id });
        await agentBridge.addChannel({ channel: agentExternal.id });
        console.log(`[${callId}] Agent audio → UDP:${AGENT_PORT}`);

        callData.connected = true;
        console.log(`[${callId}] Dual Snoop active - Audio separation enabled`);

    } catch (err) {
        console.error(`[${callId}] Snoop setup error:`, err.message);
    }
}

async function cleanup(client, callData) {
    if (!callData || callData.cleaned) return;
    callData.cleaned = true;

    const { callId } = callData;
    console.log(`[${callId}] Cleaning up resources...`);

    // Cleanup resources in reverse order
    for (const resource of callData.resources.reverse()) {
        try {
            if (resource.type === 'channel') {
                await client.channels.hangup({ channelId: resource.id });
            } else if (resource.type === 'bridge') {
                await client.bridges.destroy({ bridgeId: resource.id });
            }
        } catch (e) {
            // Ignore cleanup errors
        }
    }

    // Cleanup main bridge
    if (callData.mainBridge) {
        try {
            await client.bridges.destroy({ bridgeId: callData.mainBridge });
        } catch (e) {
            // Ignore
        }
    }

    // Hangup remaining channels
    for (const chId of [callData.customerChannel, callData.agentChannel]) {
        if (chId) {
            try {
                await client.channels.hangup({ channelId: chId });
            } catch (e) {
                // Ignore
            }
        }
    }

    activeCalls.delete(callData.customerChannel);
    activeCalls.delete(callData.agentChannel);
    console.log(`[${callId}] Cleanup complete`);
}

// Graceful shutdown
process.on('SIGINT', async () => {
    console.log('\n[INFO] Shutting down...');
    process.exit(0);
});

process.on('SIGTERM', () => {
    process.emit('SIGINT');
});

main();
