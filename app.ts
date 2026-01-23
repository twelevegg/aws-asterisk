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

import AriClient, { Client, Channel, Bridge } from 'ari-client';
import { v4 as uuidv4 } from 'uuid';

// Configuration from environment variables with defaults
const config = {
    ariUrl: process.env.ARI_URL || 'http://127.0.0.1:8088/ari',
    ariUsername: process.env.ARI_USERNAME || 'asterisk',
    ariPassword: process.env.ARI_PASSWORD || 'asterisk',
    externalHost: process.env.EXTERNAL_HOST || '127.0.0.1',
    customerPort: process.env.CUSTOMER_PORT || '12345',
    agentPort: process.env.AGENT_PORT || '12346',
    appName: process.env.APP_NAME || 'linphone-handler',
};

// Call tracking data structure
interface CallData {
    callId: string;
    callerNumber: string;
    startTime: string;
    customerSnoop: string;
    agentSnoop: string;
    customerBridge: string;
    agentBridge: string;
    customerExternal: string;
    agentExternal: string;
}

// Active calls tracking
const activeCalls = new Map<string, CallData>();

async function setupCall(client: Client, channel: Channel, callId: string): Promise<void> {
    // 1. Snoop for Customer (incoming audio - what customer says)
    const customerSnoop = await client.channels.snoopChannel({
        channelId: channel.id,
        app: config.appName,
        spy: 'in',
        whisper: 'none'
    });
    console.log(`[${callId}] Customer Snoop created (spy: in)`);

    // 2. Bridge + ExternalMedia for Customer
    const customerBridge = await client.bridges.create({ type: 'mixing' });
    const customerExternal = await client.channels.externalMedia({
        app: config.appName,
        external_host: `${config.externalHost}:${config.customerPort}`,
        format: 'ulaw',
        encapsulation: 'rtp',
        transport: 'udp',
        connection_type: 'client',
        direction: 'both'
    });
    await customerBridge.addChannel({ channel: customerSnoop.id });
    await customerBridge.addChannel({ channel: customerExternal.id });
    console.log(`[${callId}] Customer audio streaming to UDP:${config.customerPort}`);

    // 3. Snoop for Agent (outgoing audio - what agent says)
    const agentSnoop = await client.channels.snoopChannel({
        channelId: channel.id,
        app: config.appName,
        spy: 'out',
        whisper: 'none'
    });
    console.log(`[${callId}] Agent Snoop created (spy: out)`);

    // 4. Bridge + ExternalMedia for Agent
    const agentBridge = await client.bridges.create({ type: 'mixing' });
    const agentExternal = await client.channels.externalMedia({
        app: config.appName,
        external_host: `${config.externalHost}:${config.agentPort}`,
        format: 'ulaw',
        encapsulation: 'rtp',
        transport: 'udp',
        connection_type: 'client',
        direction: 'both'
    });
    await agentBridge.addChannel({ channel: agentSnoop.id });
    await agentBridge.addChannel({ channel: agentExternal.id });
    console.log(`[${callId}] Agent audio streaming to UDP:${config.agentPort}`);

    // Track active call
    activeCalls.set(channel.id, {
        callId,
        callerNumber: channel.caller.number || 'unknown',
        startTime: new Date().toISOString(),
        customerSnoop: customerSnoop.id,
        agentSnoop: agentSnoop.id,
        customerBridge: customerBridge.id,
        agentBridge: agentBridge.id,
        customerExternal: customerExternal.id,
        agentExternal: agentExternal.id
    });
}

async function cleanupCall(client: Client, callData: CallData): Promise<void> {
    const cleanup = async (fn: () => Promise<void>, resource: string): Promise<void> => {
        try {
            await fn();
        } catch (e) {
            const error = e as Error;
            if (!error.message?.includes('not found')) {
                console.debug(`[${callData.callId}] Cleanup ${resource}: ${error.message}`);
            }
        }
    };

    await cleanup(() => client.channels.hangup({ channelId: callData.customerSnoop }), 'customerSnoop');
    await cleanup(() => client.channels.hangup({ channelId: callData.agentSnoop }), 'agentSnoop');
    await cleanup(() => client.channels.hangup({ channelId: callData.customerExternal }), 'customerExternal');
    await cleanup(() => client.channels.hangup({ channelId: callData.agentExternal }), 'agentExternal');
    await cleanup(() => client.bridges.destroy({ bridgeId: callData.customerBridge }), 'customerBridge');
    await cleanup(() => client.bridges.destroy({ bridgeId: callData.agentBridge }), 'agentBridge');
}

async function main(): Promise<void> {
    const client = await AriClient.connect(
        config.ariUrl,
        config.ariUsername,
        config.ariPassword
    );

    console.log('AICC Stasis v5 - Dual Snoop Connected (TypeScript)');
    console.log(`Customer audio → UDP:${config.customerPort}`);
    console.log(`Agent audio → UDP:${config.agentPort}`);

    client.on('StasisStart', async (event: any, channel: Channel) => {
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
            await setupCall(client, channel, callId);
            await channel.continueInDialplan();
            console.log(`[${callId}] Connecting to agent02...`);
        } catch (err) {
            const error = err as Error;
            console.error(`[${callId}] Error:`, error.message);
            try {
                await channel.continueInDialplan();
            } catch (e) {
                const innerError = e as Error;
                console.error(`[${callId}] Failed to continue:`, innerError.message);
            }
        }
    });

    client.on('StasisEnd', async (event: any, channel: Channel) => {
        const callData = activeCalls.get(channel.id);
        if (callData) {
            const duration = (Date.now() - new Date(callData.startTime).getTime()) / 1000;
            console.log(`\n[${callData.callId}] Call ended - Duration: ${duration.toFixed(1)}s`);
            await cleanupCall(client, callData);
            activeCalls.delete(channel.id);
            console.log(`[${callData.callId}] Cleanup complete`);
        }
    });

    // Cleanup on exit
    process.on('SIGINT', async () => {
        console.log('\nShutting down...');
        for (const [channelId, callData] of activeCalls) {
            console.log(`Cleaning up call: ${callData.callId}`);
            await cleanupCall(client, callData);
        }
        activeCalls.clear();
        console.log('Cleanup complete');
        process.exit(0);
    });

    await client.start(config.appName);
    console.log('\nWaiting for calls...\n');
}

main().catch(err => {
    console.error('Fatal:', err.message);
    process.exit(1);
});
