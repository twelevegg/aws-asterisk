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
const STASIS_APP_NAME = 'linphone-handler';
const DIAL_TIMEOUT = 30; // seconds

// AgentRouter - Round-Robin agent selection with ARI registration check
class AgentRouter {
    constructor() {
        this.agents = [
            { id: 'agent01', endpoint: 'PJSIP/agent01', status: 'available' },
            { id: 'agent02', endpoint: 'PJSIP/agent02', status: 'available' },
            { id: 'agent03', endpoint: 'PJSIP/agent03', status: 'available' },
            { id: 'agent04', endpoint: 'PJSIP/agent04', status: 'available' },
            { id: 'agent05', endpoint: 'PJSIP/agent05', status: 'available' },
            { id: 'agent06', endpoint: 'PJSIP/agent06', status: 'available' }
        ];
        this.currentIndex = 0;
        this.ariClient = null;
    }

    setAriClient(client) {
        this.ariClient = client;
    }

    async isAgentRegistered(agentId) {
        if (!this.ariClient) return false;
        try {
            const endpoint = await this.ariClient.endpoints.get({
                tech: 'PJSIP',
                resource: agentId
            });
            return endpoint.state === 'online';
        } catch (err) {
            return false;
        }
    }

    async getNextAvailable() {
        let attempts = 0;

        while (attempts < this.agents.length) {
            const agent = this.agents[this.currentIndex];
            this.currentIndex = (this.currentIndex + 1) % this.agents.length;

            // Check actual registration status via ARI
            const isRegistered = await this.isAgentRegistered(agent.id);

            if (isRegistered && agent.status === 'available') {
                agent.status = 'busy';
                return agent;
            }

            attempts++;
        }

        console.log('[WARN] No registered and available agents');
        return null;
    }

    setAgentStatus(agentId, status) {
        const agent = this.agents.find(a => a.id === agentId);
        if (agent) {
            agent.status = status;
            console.log(`[AgentRouter] ${agentId} status: ${status}`);
        }
    }

    getAgentById(agentId) {
        return this.agents.find(a => a.id === agentId);
    }

    isAgentChannel(channelName) {
        return this.agents.some(agent => channelName.includes(agent.id));
    }

    getAgentIdFromChannel(channelName) {
        const agent = this.agents.find(a => channelName.includes(a.id));
        return agent ? agent.id : null;
    }
}

// PortPool - Dynamic port allocation
class PortPool {
    constructor(basePort = 12345, maxPort = 12400) {
        this.basePort = basePort;
        this.maxPort = maxPort;
        this.allocatedPorts = new Set();
    }

    allocate() {
        let customerPort = null;
        let agentPort = null;

        // Find two consecutive available ports
        for (let port = this.basePort; port < this.maxPort - 1; port += 2) {
            if (!this.allocatedPorts.has(port) && !this.allocatedPorts.has(port + 1)) {
                customerPort = port;
                agentPort = port + 1;
                break;
            }
        }

        if (!customerPort) {
            throw new Error('No available ports in pool');
        }

        this.allocatedPorts.add(customerPort);
        this.allocatedPorts.add(agentPort);

        return { customer: customerPort, agent: agentPort };
    }

    release(ports) {
        if (ports.customer) {
            this.allocatedPorts.delete(ports.customer);
        }
        if (ports.agent) {
            this.allocatedPorts.delete(ports.agent);
        }
    }

    getStats() {
        return {
            allocated: this.allocatedPorts.size,
            available: (this.maxPort - this.basePort) - this.allocatedPorts.size
        };
    }
}

// Initialize global instances
const agentRouter = new AgentRouter();
const portPool = new PortPool();

// Validate required environment variables
if (!ARI_PASSWORD) {
    console.error('FATAL: ARI_PASSWORD environment variable is required');
    console.error('Set it with: export ARI_PASSWORD=your_secure_password');
    process.exit(1);
}

console.log('='.repeat(60));
console.log('AICC Stasis App - Dual Snoop with Round-Robin');
console.log('='.repeat(60));
console.log(`ARI URL: ${ARI_URL}`);
console.log(`Port pool: ${portPool.basePort} - ${portPool.maxPort}`);
console.log(`Agents: ${agentRouter.agents.map(a => a.id).join(', ')}`);
console.log('='.repeat(60));

// Track active calls
const activeCalls = new Map();

async function main() {
    try {
        const client = await AriClient.connect(ARI_URL, ARI_USERNAME, ARI_PASSWORD);
        console.log('[INFO] Connected to ARI');

        // Set ARI client for agent registration checks
        agentRouter.setAriClient(client);

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
            if (agentRouter.isAgentChannel(channelName)) {
                const agentId = agentRouter.getAgentIdFromChannel(channelName);
                console.log(`[DEBUG] Agent channel joined: ${channelName} (${agentId})`);
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

                // 2. Allocate ports for this call
                const ports = portPool.allocate();
                console.log(`[${callId}] Allocated ports - Customer: ${ports.customer}, Agent: ${ports.agent}`);

                // 3. Select next available agent (checks ARI registration)
                const agent = await agentRouter.getNextAvailable();

                // If all agents busy, reject the call
                if (!agent) {
                    console.log(`[${callId}] No available agents - rejecting call`);
                    portPool.release(ports);
                    await channel.hangup();
                    return;
                }

                console.log(`[${callId}] Selected agent: ${agent.id} (${agent.endpoint})`);

                // 4. Create main bridge for customer <-> agent
                const mainBridge = await client.bridges.create({
                    type: 'mixing',
                    name: `main_${callId}`
                });
                console.log(`[${callId}] Main bridge created: ${mainBridge.id}`);

                // 5. Add customer to main bridge
                await mainBridge.addChannel({ channel: channel.id });
                console.log(`[${callId}] Customer added to bridge`);

                // 6. Dial selected agent
                console.log(`[${callId}] Dialing ${agent.endpoint}...`);
                const agentChannel = await client.channels.originate({
                    endpoint: agent.endpoint,
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
                    agentId: agent.id,
                    ports: ports,
                    resources: []
                };
                activeCalls.set(channel.id, callData);
                activeCalls.set(agentChannel.id, callData); // Also index by agent channel

                // 7. Wait for agent to answer, then setup snoop
                agentChannel.on('StasisStart', async () => {
                    console.log(`[${callId}] Agent ${agent.id} answered!`);

                    try {
                        // Add agent to main bridge
                        await mainBridge.addChannel({ channel: agentChannel.id });
                        console.log(`[${callId}] Agent added to bridge - Call connected!`);

                        // 8. Setup Dual Snoop for audio separation
                        await setupDualSnoop(client, channel, callData);

                    } catch (err) {
                        console.error(`[${callId}] Error setting up call:`, err.message);
                        // Release agent and ports on error
                        agentRouter.setAgentStatus(agent.id, 'available');
                        portPool.release(ports);
                    }
                });

                // Handle agent channel end
                agentChannel.on('StasisEnd', () => {
                    console.log(`[${callId}] Agent ${agent.id} hung up`);
                    agentRouter.setAgentStatus(agent.id, 'available');
                    cleanup(client, callData);
                });

                // Handle agent dial failure
                agentChannel.on('ChannelDestroyed', () => {
                    if (!callData.connected) {
                        console.log(`[${callId}] Agent ${agent.id} did not answer`);
                        agentRouter.setAgentStatus(agent.id, 'available');
                        cleanup(client, callData);
                    }
                });

            } catch (err) {
                console.error(`[${callId}] Error:`, err.message);

                // Get callData to cleanup properly
                const callData = activeCalls.get(channel.id);
                if (callData) {
                    if (callData.agentId) {
                        agentRouter.setAgentStatus(callData.agentId, 'available');
                    }
                    if (callData.ports) {
                        portPool.release(callData.ports);
                    }
                }

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
    const { callId, ports } = callData;

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
            external_host: `${EXTERNAL_HOST}:${ports.customer}`,
            format: 'ulaw',
            encapsulation: 'rtp',
            transport: 'udp',
            connection_type: 'client',
            direction: 'both'
        });
        callData.resources.push({ type: 'channel', id: customerExternal.id });

        await customerBridge.addChannel({ channel: customerSnoop.id });
        await customerBridge.addChannel({ channel: customerExternal.id });
        console.log(`[${callId}] Customer audio → UDP:${ports.customer}`);

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
            external_host: `${EXTERNAL_HOST}:${ports.agent}`,
            format: 'ulaw',
            encapsulation: 'rtp',
            transport: 'udp',
            connection_type: 'client',
            direction: 'both'
        });
        callData.resources.push({ type: 'channel', id: agentExternal.id });

        await agentBridge.addChannel({ channel: agentSnoop.id });
        await agentBridge.addChannel({ channel: agentExternal.id });
        console.log(`[${callId}] Agent audio → UDP:${ports.agent}`);

        callData.connected = true;
        console.log(`[${callId}] Dual Snoop active - Audio separation enabled`);

    } catch (err) {
        console.error(`[${callId}] Snoop setup error:`, err.message);
    }
}

async function cleanup(client, callData) {
    if (!callData || callData.cleaned) return;
    callData.cleaned = true;

    const { callId, agentId, ports } = callData;
    console.log(`[${callId}] Cleaning up resources...`);

    // Release agent back to available pool
    if (agentId) {
        agentRouter.setAgentStatus(agentId, 'available');
    }

    // Release ports back to pool
    if (ports) {
        portPool.release(ports);
        const stats = portPool.getStats();
        console.log(`[${callId}] Ports released - Pool stats: ${stats.allocated} allocated, ${stats.available} available`);
    }

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
