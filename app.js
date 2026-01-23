/**
 * AICC Stasis v5 - Dual Snoop for Speaker Separation
 *
 * 고객(in) → UDP:12345
 * 상담사(out) → UDP:12346
 *
 * Environment Variables:
 *   ARI_URL          - ARI endpoint (default: http://127.0.0.1:8088/ari)
 *   ARI_USERNAME     - ARI username (default: asterisk)
 *   ARI_PASSWORD     - ARI password (default: asterisk)
 *   EXTERNAL_HOST    - External media host (default: 127.0.0.1)
 *   CUSTOMER_PORT    - Customer audio UDP port (default: 12345)
 *   AGENT_PORT       - Agent audio UDP port (default: 12346)
 *   APP_NAME         - Stasis app name (default: linphone-handler)
 */
const AriClient = require('ari-client');
const { v4: uuidv4 } = require('uuid');

// Configuration from environment variables with defaults
const ARI_URL = process.env.ARI_URL || 'http://127.0.0.1:8088/ari';
const ARI_USERNAME = process.env.ARI_USERNAME || 'asterisk';
const ARI_PASSWORD = process.env.ARI_PASSWORD || 'asterisk';
const EXTERNAL_HOST = process.env.EXTERNAL_HOST || '127.0.0.1';
const CUSTOMER_PORT = process.env.CUSTOMER_PORT || '12345';
const AGENT_PORT = process.env.AGENT_PORT || '12346';
const APP_NAME = process.env.APP_NAME || 'linphone-handler';

// Active calls tracking
const activeCalls = new Map();

async function main() {
    const client = await AriClient.connect(ARI_URL, ARI_USERNAME, ARI_PASSWORD);
    console.log('AICC Stasis v5 - Dual Snoop Connected');
    console.log(`Customer audio → UDP:${CUSTOMER_PORT}`);
    console.log(`Agent audio → UDP:${AGENT_PORT}`);

    client.on('StasisStart', async (event, channel) => {
        const name = channel.name || '';

        // Skip helper channels
        if (name.includes('UnicastRTP') || name.includes('Snoop') || name.includes('ExternalMedia')) {
            return;
        }

        const callId = uuidv4();
        const callerNumber = channel.caller.number || 'unknown';
        
        console.log(`\n${'='.repeat(60)}`);
        console.log(`[${callId}] New call from: ${callerNumber}`);
        console.log(`${'='.repeat(60)}`);

        try {
            // 1. Snoop for Customer (incoming audio - what customer says)
            const customerSnoop = await client.channels.snoopChannel({
                channelId: channel.id,
                app: APP_NAME,
                spy: 'in',      // 고객이 말하는 것
                whisper: 'none'
            });
            console.log(`[${callId}] Customer Snoop created (spy: in)`);

            // 2. Bridge + ExternalMedia for Customer
            const customerBridge = await client.bridges.create({ type: 'mixing' });
            const customerExternal = await client.channels.externalMedia({
                app: APP_NAME,
                external_host: `${EXTERNAL_HOST}:${CUSTOMER_PORT}`,
                format: 'ulaw',
                encapsulation: 'rtp',
                transport: 'udp',
                connection_type: 'client',
                direction: 'both'
            });
            await customerBridge.addChannel({ channel: customerSnoop.id });
            await customerBridge.addChannel({ channel: customerExternal.id });
            console.log(`[${callId}] Customer audio streaming to UDP:${CUSTOMER_PORT}`);

            // 3. Snoop for Agent (outgoing audio - what agent says)
            const agentSnoop = await client.channels.snoopChannel({
                channelId: channel.id,
                app: APP_NAME,
                spy: 'out',     // 상담사가 말하는 것
                whisper: 'none'
            });
            console.log(`[${callId}] Agent Snoop created (spy: out)`);

            // 4. Bridge + ExternalMedia for Agent
            const agentBridge = await client.bridges.create({ type: 'mixing' });
            const agentExternal = await client.channels.externalMedia({
                app: APP_NAME,
                external_host: `${EXTERNAL_HOST}:${AGENT_PORT}`,
                format: 'ulaw',
                encapsulation: 'rtp',
                transport: 'udp',
                connection_type: 'client',
                direction: 'both'
            });
            await agentBridge.addChannel({ channel: agentSnoop.id });
            await agentBridge.addChannel({ channel: agentExternal.id });
            console.log(`[${callId}] Agent audio streaming to UDP:${AGENT_PORT}`);

            // Track active call
            activeCalls.set(channel.id, {
                callId,
                callerNumber,
                startTime: new Date().toISOString(),
                customerSnoop: customerSnoop.id,
                agentSnoop: agentSnoop.id,
                customerBridge: customerBridge.id,
                agentBridge: agentBridge.id,
                customerExternal: customerExternal.id,
                agentExternal: agentExternal.id
            });

            // Continue to dialplan (connect to agent)
            await channel.continueInDialplan();
            console.log(`[${callId}] Connecting to agent02...`);

        } catch (err) {
            console.error(`[${callId}] Error:`, err.message);
            try { 
                await channel.continueInDialplan(); 
            } catch (e) {
                console.error(`[${callId}] Failed to continue:`, e.message);
            }
        }
    });

    client.on('StasisEnd', async (event, channel) => {
        const callData = activeCalls.get(channel.id);
        if (callData) {
            const duration = (new Date() - new Date(callData.startTime)) / 1000;
            console.log(`\n[${callData.callId}] Call ended - Duration: ${duration.toFixed(1)}s`);
            activeCalls.delete(channel.id);
        }
    });

    // Cleanup on exit
    process.on('SIGINT', async () => {
        console.log('\nShutting down...');
        for (const [channelId, callData] of activeCalls) {
            console.log(`Cleaning up call: ${callData.callId}`);
        }
        process.exit(0);
    });

    await client.start(APP_NAME);
    console.log('\nWaiting for calls...\n');
}

main().catch(err => {
    console.error('Fatal:', err.message);
    process.exit(1);
});
