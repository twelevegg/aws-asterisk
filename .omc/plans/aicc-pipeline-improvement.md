# AICC Pipeline Production Readiness Improvement Plan

## 1. Overview

This plan addresses critical security, stability, and scalability issues identified in the AICC Pipeline system before production deployment. The system currently handles SIP calls through Asterisk PBX, processes audio via a Python pipeline with VAD and STT, and sends results via WebSocket.

**Current State:** Development-ready with significant security vulnerabilities and single-call limitations.
**Target State:** Production-ready with multi-call support, secure authentication, and robust error handling.

**Timeline:**
- CRITICAL: 24 hours
- HIGH: 1 week
- MEDIUM: 1 month

---

## 2. CRITICAL Priority (24 Hours)

### 2.1 Multi-Call Support - Dynamic Port Allocation

- **Location:** `python/aicc_pipeline/core/udp_receiver.py:65`, `python/aicc_pipeline/core/pipeline.py:294`
- **Problem:** Fixed UDP ports (12345/12346) and single `_call_id` variable prevent concurrent call handling. Production requires multiple simultaneous calls.
- **Solution:**
  1. Create a `PortPool` class to manage dynamic port allocation (range: 20000-30000)
  2. Define `CallSession` dataclass with all required fields
  3. Implement port-to-call mapping: each call gets unique port pair, receiver looks up call_id by port
  4. Modify `UDPReceiver` to accept dynamically assigned ports
  5. Create REST API for Node.js to request ports and register call metadata

  ```python
  # New file: python/aicc_pipeline/core/call_session.py
  from dataclasses import dataclass, field
  from datetime import datetime
  from typing import Optional

  @dataclass
  class CallSession:
      """Represents an active call session with all associated state."""
      call_id: str
      customer_port: int
      agent_port: int
      customer_number: Optional[str] = None
      agent_id: Optional[str] = None
      start_time: datetime = field(default_factory=datetime.utcnow)
      # Processors are set after initialization
      customer_processor: Optional["SpeakerProcessor"] = None
      agent_processor: Optional["SpeakerProcessor"] = None
      # Receivers are set after initialization
      customer_receiver: Optional["UDPReceiver"] = None
      agent_receiver: Optional["UDPReceiver"] = None
  ```

  ```python
  # New file: python/aicc_pipeline/core/port_pool.py
  from typing import Dict, Tuple, Optional
  import threading

  class PortPool:
      """Thread-safe dynamic port allocation pool."""

      def __init__(self, start: int = 20000, end: int = 30000):
          self.available = set(range(start, end, 2))  # Even ports for customer, odd for agent
          self.allocated: Dict[str, Tuple[int, int]] = {}
          self._port_to_call: Dict[int, str] = {}  # Maps port -> call_id for lookup
          self._lock = threading.Lock()

      def allocate(self, call_id: str) -> Tuple[int, int]:
          """Allocate a port pair for a call. Raises ValueError if pool exhausted."""
          with self._lock:
              if not self.available:
                  raise ValueError("Port pool exhausted - no available ports")
              customer_port = self.available.pop()
              agent_port = customer_port + 1
              self.allocated[call_id] = (customer_port, agent_port)
              self._port_to_call[customer_port] = call_id
              self._port_to_call[agent_port] = call_id
              return customer_port, agent_port

      def release(self, call_id: str) -> None:
          """Release ports back to the pool."""
          with self._lock:
              if call_id in self.allocated:
                  ports = self.allocated.pop(call_id)
                  self._port_to_call.pop(ports[0], None)
                  self._port_to_call.pop(ports[1], None)
                  self.available.add(ports[0])

      def get_call_id_by_port(self, port: int) -> Optional[str]:
          """Look up call_id by port number for incoming UDP packets."""
          with self._lock:
              return self._port_to_call.get(port)

      @property
      def available_count(self) -> int:
          """Number of available port pairs."""
          with self._lock:
              return len(self.available)
  ```

  ```python
  # Update python/aicc_pipeline/core/pipeline.py - Replace _call_id with session registry
  from .call_session import CallSession
  from .port_pool import PortPool
  from typing import Dict

  class AICCPipeline:
      def __init__(self, config: Optional[PipelineConfig] = None):
          self.config = config or get_config()
          self._ws_manager: Optional[WebSocketManager] = None
          self._port_pool = PortPool()
          self._sessions: Dict[str, CallSession] = {}  # call_id -> CallSession
          self._running = False
  ```

- **Acceptance Criteria:**
  - [ ] 10 concurrent calls can be processed without port conflicts
  - [ ] Each call has isolated audio streams and state
  - [ ] Ports are released within 5 seconds of call end
  - [ ] Port exhaustion raises clear error (not KeyError)
- **Verification:**
  ```bash
  # Load test with multiple concurrent calls
  python tests/load_test_concurrent_calls.py --calls 10
  # Verify port cleanup
  netstat -an | grep -E '2[0-9]{4}' | wc -l  # Should be 0 after calls end
  # Verify port exhaustion handling
  python -c "from aicc_pipeline.core.port_pool import PortPool; p = PortPool(20000, 20002); p.allocate('c1'); p.allocate('c2')"
  # Should raise ValueError on exhaustion
  ```
- **Backward Compatibility:** Add environment variable `LEGACY_FIXED_PORTS=true` for single-call fallback during migration.
- **Test Scaffolding Required:** Create `tests/load_test_concurrent_calls.py` with multi-call simulation.

---

### 2.2 ARI Credentials Security

- **Location:** `config/ari.conf:17`, `stasis_app/app.js:19`
- **Problem:** Hardcoded password `asterisk` in both config and code. Critical security vulnerability.
- **Solution:**
  1. Move credentials to environment variables
  2. Update `ari.conf` to use includes for sensitive data
  3. Modify `app.js` to read from environment

  ```javascript
  // stasis_app/app.js:19 - Replace hardcoded credentials
  const ariConfig = {
      url: process.env.ARI_URL || 'http://localhost:8088',
      username: process.env.ARI_USERNAME || 'asterisk',
      password: process.env.ARI_PASSWORD,  // Required - no default
      app: 'aicc-stasis'
  };

  if (!ariConfig.password) {
      console.error('FATAL: ARI_PASSWORD environment variable required');
      process.exit(1);
  }
  ```

  ```ini
  ; config/ari.conf - Remove password, reference external file
  [asterisk]
  type = user
  read_only = no
  password_format = plain
  ; Password loaded from /etc/asterisk/secrets/ari.secret
  #include "/etc/asterisk/secrets/ari.secret"
  ```

- **Acceptance Criteria:**
  - [ ] No passwords in version control
  - [ ] Application fails to start without `ARI_PASSWORD` set
  - [ ] Secrets file has 600 permissions
- **Verification:**
  ```bash
  grep -r "password.*=" config/ stasis_app/ --include="*.js" --include="*.conf" | grep -v "password_format"
  # Should return empty
  ```

---

### 2.3 SIP Password Security

- **Location:** `sql/seed_agents.sql` (all agents use `Aivle12!`)
- **Problem:** All SIP agents share the same password. Compromising one compromises all.
- **Solution:**
  1. Generate unique passwords per agent using secure random
  2. Store hashed passwords in DB, plaintext only in secure secrets manager
  3. Update seed script to generate unique passwords

  ```sql
  -- sql/seed_agents.sql - Replace with password generation
  -- Passwords should be generated externally and injected
  INSERT INTO ps_auths (id, auth_type, password, username)
  VALUES
    ('agent1', 'userpass', '${AGENT1_PASSWORD}', 'agent1'),
    ('agent2', 'userpass', '${AGENT2_PASSWORD}', 'agent2');
  ```

  Create password generation script:
  ```bash
  # scripts/generate_agent_passwords.sh
  #!/bin/bash
  for agent in agent1 agent2; do
      password=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c16)
      echo "export ${agent^^}_PASSWORD='$password'" >> /etc/asterisk/secrets/agents.env
  done
  ```

- **Acceptance Criteria:**
  - [ ] Each agent has unique 16+ character password
  - [ ] Passwords not stored in version control
  - [ ] Password rotation script exists
- **Verification:**
  ```bash
  # Ensure no duplicate passwords in database
  sudo asterisk -rx "database show" | grep password | sort | uniq -d
  # Should return empty
  ```

---

### 2.4 Terraform State Security

- **Location:** `terraform/main.tf`, `.gitignore`
- **Problem:** tfstate stored locally in plaintext, not excluded from git. Contains sensitive infrastructure data.
- **Current Files:**
  - `terraform/terraform.tfstate` (exists locally)
  - `terraform/terraform.tfstate.backup` (exists locally)
- **Solution:**
  1. Check if tfstate files are tracked in git history
  2. If tracked, remove from git history using BFG Repo Cleaner or `git filter-branch`
  3. Configure S3 backend with encryption
  4. Add tfstate patterns to .gitignore
  5. Enable state locking with DynamoDB

  **Step 1: Check git tracking status**
  ```bash
  # Check if currently tracked
  git ls-files terraform/*.tfstate

  # Check if ever committed in history
  git log --oneline --all -- "terraform/*.tfstate"
  ```

  **Step 2: Remove from git history (if found)**
  ```bash
  # Option A: Using BFG Repo Cleaner (recommended, faster)
  # Download bfg.jar first
  java -jar bfg.jar --delete-files "*.tfstate" .
  git reflog expire --expire=now --all && git gc --prune=now --aggressive

  # Option B: Using git filter-branch (slower, built-in)
  git filter-branch --force --index-filter \
    "git rm --cached --ignore-unmatch terraform/*.tfstate terraform/*.tfstate.backup" \
    --prune-empty --tag-name-filter cat -- --all
  git reflog expire --expire=now --all && git gc --prune=now --aggressive
  ```

  **Step 3: Configure S3 backend**
  ```hcl
  # terraform/backend.tf - New file
  terraform {
    backend "s3" {
      bucket         = "aicc-terraform-state"
      key            = "aws-asterisk/terraform.tfstate"
      region         = "ap-northeast-2"
      encrypt        = true
      dynamodb_table = "terraform-locks"
    }
  }
  ```

  **Step 4: Update .gitignore**
  ```gitignore
  # .gitignore - Add these lines
  *.tfstate
  *.tfstate.*
  .terraform/
  *.tfvars
  !*.tfvars.example
  ```

- **Acceptance Criteria:**
  - [ ] No tfstate files in repository (current or history)
  - [ ] S3 bucket has encryption enabled
  - [ ] State locking prevents concurrent modifications
- **Verification:**
  ```bash
  # Verify not in current repo
  git ls-files | grep -E '\.tfstate'  # Should return empty

  # Verify not in history
  git log --oneline --all -- "terraform/*.tfstate" | wc -l  # Should be 0

  # Verify S3 encryption
  aws s3api get-bucket-encryption --bucket aicc-terraform-state
  ```

---

### 2.5 Health Check Implementation

- **Location:** New file `python/aicc_pipeline/health/checker.py`
- **Problem:** No way to verify system health. Failures go undetected until users report issues.
- **Solution:**
  1. Create health check HTTP endpoint
  2. Add component-level health verification
  3. Integrate with AWS ALB health checks

  ```python
  # python/aicc_pipeline/health/checker.py
  from aiohttp import web
  import asyncio

  class HealthChecker:
      def __init__(self, pipeline, port=8080):
          self.pipeline = pipeline
          self.port = port

      async def check_components(self) -> dict:
          return {
              "udp_receiver": self.pipeline.udp_receiver.is_healthy(),
              "stt_service": await self.pipeline.stt.health_check(),
              "websocket": self.pipeline.ws_manager.is_connected(),
              "port_pool": self.pipeline._port_pool.available_count > 100,
          }

      async def health_handler(self, request):
          health = await self.check_components()
          status = 200 if all(health.values()) else 503
          return web.json_response(health, status=status)

      async def start(self):
          app = web.Application()
          app.router.add_get('/health', self.health_handler)
          app.router.add_get('/health/live', lambda r: web.Response(text='OK'))
          app.router.add_get('/health/ready', self.health_handler)
          runner = web.AppRunner(app)
          await runner.setup()
          site = web.TCPSite(runner, '0.0.0.0', self.port)
          await site.start()
  ```

- **Acceptance Criteria:**
  - [ ] `/health/live` returns 200 if process is running
  - [ ] `/health/ready` returns 200 only when all components healthy
  - [ ] Response time < 100ms
- **Verification:**
  ```bash
  curl -w "%{http_code}" http://localhost:8080/health/ready
  # Should return 200 with JSON body
  ```

---

### 2.6 Async Task Tracking

- **Location:** `python/aicc_pipeline/core/pipeline.py:27-34` (`_safe_task()` definition), called at lines 207, 326, 357, 364
- **Problem:** Fire-and-forget tasks with no tracking. Lost exceptions, potential memory leaks.
- **Solution:**
  1. Create task registry for tracking background tasks
  2. Add task completion callbacks
  3. Implement periodic cleanup of completed tasks

  ```python
  # python/aicc_pipeline/core/task_registry.py
  import asyncio
  from typing import Dict, Set
  import logging

  class TaskRegistry:
      def __init__(self):
          self.tasks: Dict[str, asyncio.Task] = {}
          self.failed_tasks: Set[str] = set()
          self._cleanup_task = None

      def register(self, name: str, coro) -> asyncio.Task:
          task = asyncio.create_task(coro)
          self.tasks[name] = task
          task.add_done_callback(lambda t: self._on_complete(name, t))
          return task

      def _on_complete(self, name: str, task: asyncio.Task):
          if task.exception():
              logging.error(f"Task {name} failed: {task.exception()}")
              self.failed_tasks.add(name)
          self.tasks.pop(name, None)

      async def shutdown(self, timeout=5.0):
          for task in self.tasks.values():
              task.cancel()
          await asyncio.gather(*self.tasks.values(), return_exceptions=True)
  ```

  Update `pipeline.py` - replace `_safe_task` calls:
  ```python
  # At line 207 in _process_vad_state:
  self.task_registry.register(f"finalize_turn_{self.call_id}_{time.time()}", self._finalize_turn())

  # At line 326 in _on_first_packet:
  self.task_registry.register(f"send_metadata_start_{self._call_id}", self._ws_manager.send(event))
  ```

- **Acceptance Criteria:**
  - [ ] All background tasks are tracked
  - [ ] Task failures are logged with context
  - [ ] Graceful shutdown waits for task completion
- **Verification:**
  ```python
  # In tests
  assert len(pipeline.task_registry.tasks) == expected_active_tasks
  assert len(pipeline.task_registry.failed_tasks) == 0
  ```

---

## 3. HIGH Priority (1 Week)

### 3.1 Call Metadata Synchronization

- **Location:** `stasis_app/app.js` (activeCalls), `python/aicc_pipeline/core/pipeline.py`
- **Problem:** No synchronization of call metadata between Node.js and Python. Call info like caller ID lost.
- **Solution:**
  1. Create REST API for metadata exchange
  2. Node.js calls Python API with call metadata when call starts
  3. Use port-to-call mapping (from 2.1) to associate UDP packets with calls

  ```python
  # python/aicc_pipeline/api/call_metadata.py
  from aiohttp import web

  class CallMetadataAPI:
      def __init__(self, pipeline):
          self.pipeline = pipeline

      async def register_call(self, request):
          """Register a new call with metadata. Node.js calls this when call starts."""
          data = await request.json()
          call_id = data['call_id']

          # Allocate ports from pool
          customer_port, agent_port = self.pipeline._port_pool.allocate(call_id)

          # Create session with metadata
          session = CallSession(
              call_id=call_id,
              customer_port=customer_port,
              agent_port=agent_port,
              customer_number=data.get('customer_number'),
              agent_id=data.get('agent_id'),
          )
          self.pipeline._sessions[call_id] = session

          # Start UDP receivers for this call
          await self.pipeline._start_call_receivers(session)

          return web.json_response({
              'status': 'registered',
              'customer_port': customer_port,
              'agent_port': agent_port
          })

      async def end_call(self, request):
          call_id = request.match_info['call_id']
          await self.pipeline.end_call(call_id)
          return web.json_response({'status': 'ended'})
  ```

  ```javascript
  // stasis_app/app.js - Add after call setup
  // Request ports from Python pipeline first
  const portResponse = await axios.post(`${PIPELINE_URL}/api/calls`, {
      call_id: channel.id,
      customer_number: channel.caller.number,
      agent_id: agentId,
  });

  // Use returned ports for ExternalMedia
  const { customer_port, agent_port } = portResponse.data;

  // Create ExternalMedia with dynamic ports
  await client.channels.externalMedia({
      // ... use customer_port for customer snoop
  });
  ```

- **Acceptance Criteria:**
  - [ ] Call metadata available in Python within 100ms of call start
  - [ ] WebSocket messages include accurate caller info
  - [ ] Metadata cleaned up after call end
- **Verification:**
  ```bash
  # Check WebSocket output includes metadata
  wscat -c ws://localhost:8765 | grep "customer_number"
  ```

---

### 3.2 Streaming STT Migration

- **Location:** `python/aicc_pipeline/stt/google_stt.py`
- **Problem:** Batch STT adds latency. Real-time transcription requires streaming.
- **Solution:**
  1. Implement Google Speech V2 streaming API
  2. Use bidirectional streaming for continuous recognition
  3. Handle interim results for faster feedback

  ```python
  # python/aicc_pipeline/stt/streaming_stt.py
  from google.cloud.speech_v2 import SpeechAsyncClient
  from google.cloud.speech_v2.types import cloud_speech

  class StreamingSTT:
      def __init__(self, project_id: str):
          self.client = SpeechAsyncClient()
          self.project_id = project_id

      async def stream_recognize(self, audio_generator, call_id: str):
          config = cloud_speech.RecognitionConfig(
              explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                  encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                  sample_rate_hertz=16000,
                  audio_channel_count=1,
              ),
              language_codes=["ko-KR"],
              model="telephony",
          )

          streaming_config = cloud_speech.StreamingRecognitionConfig(
              config=config,
              streaming_features=cloud_speech.StreamingRecognitionFeatures(
                  interim_results=True,
              ),
          )

          async def request_generator():
              yield cloud_speech.StreamingRecognizeRequest(
                  recognizer=f"projects/{self.project_id}/locations/global/recognizers/_",
                  streaming_config=streaming_config,
              )
              async for chunk in audio_generator:
                  yield cloud_speech.StreamingRecognizeRequest(audio=chunk)

          responses = await self.client.streaming_recognize(requests=request_generator())
          async for response in responses:
              for result in response.results:
                  yield result
  ```

- **Acceptance Criteria:**
  - [ ] Transcript appears within 500ms of speech
  - [ ] Interim results available for UI feedback
  - [ ] No increased error rate vs batch STT
- **Verification:**
  ```python
  # Measure latency from audio input to transcript
  async def test_streaming_latency():
      start = time.time()
      async for result in stt.stream_recognize(audio_gen, "test"):
          latency = time.time() - start
          assert latency < 0.5  # 500ms
          break
  ```

---

### 3.3 WebSocket Authentication

- **Location:** `python/aicc_pipeline/websocket/manager.py` (OUTBOUND client that connects TO external servers)
- **Problem:** No authentication on outbound WebSocket connections. External servers cannot verify our identity.
- **Architecture Note:** `WebSocketManager` is an OUTBOUND CLIENT. It connects TO external WebSocket servers, not the other way around. The `connect()` method at line 130 is `websockets.connect()` which initiates outbound connections.
- **Solution:**
  1. Add JWT-based authentication headers to outbound connections
  2. Include auth token in connection handshake
  3. Handle token refresh for long-lived connections

  ```python
  # python/aicc_pipeline/websocket/auth.py
  import jwt
  from datetime import datetime, timedelta

  class WebSocketAuth:
      def __init__(self, secret_key: str, client_id: str):
          self.secret_key = secret_key
          self.client_id = client_id

      def generate_token(self, permissions: list = None) -> str:
          """Generate JWT token for outbound WebSocket authentication."""
          payload = {
              'client_id': self.client_id,
              'permissions': permissions or ['send_transcripts'],
              'exp': datetime.utcnow() + timedelta(hours=1),
              'iat': datetime.utcnow(),
          }
          return jwt.encode(payload, self.secret_key, algorithm='HS256')
  ```

  Update `manager.py` - modify `_connect_one()` at line 118:
  ```python
  async def _connect_one(self, url: str) -> bool:
      """Connect to a single WebSocket server with authentication."""
      try:
          logger.info(f"Connecting to: {url}")

          # Build auth headers for outbound connection
          extra_headers = {}
          if self._auth:
              token = self._auth.generate_token()
              extra_headers['Authorization'] = f'Bearer {token}'

          ws = await websockets.connect(
              url,
              ping_interval=self.ping_interval,
              ping_timeout=self.ping_timeout,
              extra_headers=extra_headers,  # Add auth headers
          )
          self._connections[url] = ws
          logger.info(f"Connected: {url}")
          return True
      except Exception as e:
          logger.warning(f"Connection failed: {url} - {e}")
          return False
  ```

  Update `WebSocketManager.__init__()`:
  ```python
  def __init__(
      self,
      urls: List[str],
      queue_maxsize: int = 1000,
      reconnect_interval: float = 5.0,
      ping_interval: float = 20.0,
      ping_timeout: float = 10.0,
      auth: Optional[WebSocketAuth] = None,  # Add auth parameter
  ):
      # ... existing code ...
      self._auth = auth
  ```

- **Acceptance Criteria:**
  - [ ] Outbound connections include Authorization header
  - [ ] Servers can validate our JWT tokens
  - [ ] Token refresh before expiry on long connections
- **Verification:**
  ```bash
  # Start a test WebSocket server that logs headers
  python -c "
  import asyncio, websockets
  async def handler(ws, path):
      print('Headers:', ws.request_headers)
      await ws.recv()
  asyncio.run(websockets.serve(handler, 'localhost', 8765))
  "
  # Connect with auth - should see Authorization header in logs
  ```

---

### 3.4 UDP Network Security

- **Location:** `python/aicc_pipeline/core/udp_receiver.py:65`
- **Problem:** UDP bound to `0.0.0.0` accepts traffic from any source. No authentication.
- **Solution:**
  1. Bind to specific internal interface
  2. Implement source IP whitelist
  3. Add SRTP for RTP encryption (optional, complex)

  ```python
  # python/aicc_pipeline/core/udp_receiver.py:65 - Update bind
  class SecureUDPReceiver:
      def __init__(self, bind_address: str = '127.0.0.1', allowed_sources: list = None):
          self.bind_address = bind_address
          self.allowed_sources = set(allowed_sources or ['127.0.0.1'])

      def _validate_source(self, addr: tuple) -> bool:
          return addr[0] in self.allowed_sources

      async def receive(self):
          # ... existing code ...
          data, addr = await self.transport.recvfrom()
          if not self._validate_source(addr):
              logging.warning(f"Rejected packet from unauthorized source: {addr}")
              return None
          return data
  ```

- **Acceptance Criteria:**
  - [ ] UDP only accepts from whitelisted IPs
  - [ ] Rejected packets logged
  - [ ] Configuration via environment variable
- **Verification:**
  ```bash
  # Send from non-whitelisted IP - should be rejected
  echo "test" | nc -u PIPELINE_HOST 20000
  # Check logs for rejection
  grep "unauthorized source" /var/log/aicc/pipeline.log
  ```

---

### 3.5 ARI HTTP Binding Security

- **Location:** `config/http.conf:8`
- **Problem:** ARI HTTP bound to `0.0.0.0` exposes management interface publicly.
- **Solution:**
  1. Bind to localhost only
  2. Use reverse proxy with authentication for external access
  3. Add firewall rules as defense in depth

  ```ini
  ; config/http.conf - Update line 8
  [general]
  enabled=yes
  bindaddr=127.0.0.1  ; Changed from 0.0.0.0
  bindport=8088
  ```

  Add nginx reverse proxy for external access:
  ```nginx
  # /etc/nginx/sites-available/asterisk-ari
  server {
      listen 8443 ssl;
      ssl_certificate /etc/ssl/certs/ari.crt;
      ssl_certificate_key /etc/ssl/private/ari.key;

      location /ari/ {
          auth_basic "ARI Access";
          auth_basic_user_file /etc/nginx/.htpasswd;
          proxy_pass http://127.0.0.1:8088/ari/;
      }
  }
  ```

- **Acceptance Criteria:**
  - [ ] ARI not accessible from external IPs directly
  - [ ] Authenticated access available via reverse proxy
  - [ ] Existing internal connections unaffected
- **Verification:**
  ```bash
  # Direct external access - should fail
  curl -m 5 http://EXTERNAL_IP:8088/ari/asterisk/info
  # Via proxy with auth - should succeed
  curl -u admin:password https://EXTERNAL_IP:8443/ari/asterisk/info
  ```

---

### 3.6 ThreadPoolExecutor Cleanup

- **Location:** `python/aicc_pipeline/stt/google_stt.py:205-207` (`shutdown()` method)
- **Problem:** `shutdown(wait=False)` causes thread leaks. Pending work lost.
- **Solution:**
  1. Track active executor tasks
  2. Implement graceful shutdown with timeout
  3. Add context manager for automatic cleanup

  ```python
  # python/aicc_pipeline/stt/google_stt.py - Update shutdown at lines 205-207
  from concurrent.futures import Future, wait
  from typing import Set

  class GoogleCloudSTT:
      def __init__(self, ...):
          # ... existing init ...
          self._executor = ThreadPoolExecutor(max_workers=2)
          self._pending_futures: Set[Future] = set()

      def _sync_transcribe(self, audio_data: bytes) -> TranscriptResult:
          # Wrap existing method to track futures
          future = self._executor.submit(self._do_transcribe, audio_data)
          self._pending_futures.add(future)
          future.add_done_callback(self._pending_futures.discard)
          return future.result()

      def shutdown(self, timeout: float = 10.0):
          """Graceful shutdown with timeout."""
          # Wait for pending tasks
          if self._pending_futures:
              done, pending = wait(self._pending_futures, timeout=timeout)
              if pending:
                  logging.warning(f"{len(pending)} STT tasks cancelled during shutdown")

          self._executor.shutdown(wait=True)

      async def __aenter__(self):
          return self

      async def __aexit__(self, *args):
          self.shutdown()
  ```

- **Acceptance Criteria:**
  - [ ] All pending tasks complete or timeout during shutdown
  - [ ] No thread leaks after shutdown
  - [ ] Warning logged for cancelled tasks
- **Verification:**
  ```python
  import threading
  initial_threads = threading.active_count()
  async with GoogleCloudSTT(...) as stt:
      # Use service
      pass
  assert threading.active_count() <= initial_threads
  ```

---

### 3.7 Non-Blocking UDP Callback

- **Location:** `python/aicc_pipeline/core/udp_receiver.py` - entire `start()` method (lines 69-114)
- **Problem:** The `start()` method uses `loop.sock_recv()` in a while loop with synchronous callback `self.on_audio()`. Under high load, processing delays cause packet loss because the loop blocks waiting for callback completion.
- **Solution:**
  1. Refactor to use `asyncio.DatagramProtocol` for true async UDP handling
  2. Use asyncio queue for decoupling receive from processing
  3. Add backpressure handling with packet dropping under extreme load

  ```python
  # python/aicc_pipeline/core/udp_receiver.py - Complete refactor
  import asyncio
  import logging
  from typing import Callable, Optional, Tuple

  logger = logging.getLogger("aicc.udp")

  class UDPProtocol(asyncio.DatagramProtocol):
      """Async UDP protocol that queues received datagrams."""

      def __init__(self, queue: asyncio.Queue, max_queue_size: int = 1000):
          self.queue = queue
          self.max_queue_size = max_queue_size
          self.dropped_packets = 0
          self.transport = None

      def connection_made(self, transport):
          self.transport = transport

      def datagram_received(self, data: bytes, addr: Tuple[str, int]):
          try:
              self.queue.put_nowait((data, addr))
          except asyncio.QueueFull:
              self.dropped_packets += 1
              if self.dropped_packets % 100 == 0:
                  logger.warning(f"Dropped {self.dropped_packets} packets due to backpressure")

  class AsyncUDPReceiver:
      """Non-blocking UDP receiver using DatagramProtocol."""

      def __init__(
          self,
          port: int,
          speaker: str,
          on_audio: Callable[[bytes, str], None],
          queue_size: int = 1000,
      ):
          self.port = port
          self.speaker = speaker
          self.on_audio = on_audio
          self.queue_size = queue_size

          self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
          self._protocol: Optional[UDPProtocol] = None
          self._transport = None
          self._running = False
          self._process_task: Optional[asyncio.Task] = None

      async def start(self):
          """Start receiving UDP packets (non-blocking)."""
          loop = asyncio.get_event_loop()

          self._transport, self._protocol = await loop.create_datagram_endpoint(
              lambda: UDPProtocol(self._queue, self.queue_size),
              local_addr=('0.0.0.0', self.port)
          )

          self._running = True
          self._process_task = asyncio.create_task(self._process_loop())
          logger.info(f"Listening on UDP:{self.port} ({self.speaker})")

      async def _process_loop(self):
          """Process queued packets without blocking receive."""
          while self._running:
              try:
                  data, addr = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                  # Process in separate task to avoid blocking queue consumer
                  asyncio.create_task(self._handle_packet(data, addr))
              except asyncio.TimeoutError:
                  continue
              except Exception as e:
                  if self._running:
                      logger.error(f"Process loop error ({self.speaker}): {e}")

      async def _handle_packet(self, data: bytes, addr: Tuple[str, int]):
          """Handle a single packet (runs concurrently)."""
          try:
              # Parse RTP and convert audio (existing logic)
              rtp = RTPPacket.parse(data)
              pcm_16k = AudioConverter.convert(rtp.payload)
              self.on_audio(pcm_16k, self.speaker)
          except Exception as e:
              logger.warning(f"Packet handling error ({self.speaker}): {e}")

      def stop(self):
          self._running = False
          if self._transport:
              self._transport.close()
          if self._process_task:
              self._process_task.cancel()
  ```

- **Acceptance Criteria:**
  - [ ] 10,000 packets/second processed without loss
  - [ ] Dropped packets counted and logged
  - [ ] Processing errors don't block receive loop
- **Verification:**
  ```bash
  # Load test
  python tests/udp_load_test.py --pps 10000 --duration 60
  # Check dropped packets
  grep "Dropped.*packets" /var/log/aicc/pipeline.log
  ```
- **Test Scaffolding Required:** Create `tests/udp_load_test.py`.

---

### 3.8 Audioop Migration

- **Location:** `python/aicc_pipeline/audio/converter.py:7`
- **Problem:** `audioop` module deprecated in Python 3.11, removed in 3.13.
- **Solution:**
  1. Replace with `scipy.signal` or `numpy` equivalents
  2. Maintain same API for backward compatibility

  ```python
  # python/aicc_pipeline/audio/converter.py - Replace audioop
  import numpy as np
  from scipy import signal

  def ulaw2lin(data: bytes) -> bytes:
      """Convert u-law to linear PCM using numpy."""
      ulaw_table = np.array([
          # u-law to linear conversion table (256 entries)
          # ... standard u-law decoding table ...
      ], dtype=np.int16)

      ulaw_bytes = np.frombuffer(data, dtype=np.uint8)
      linear = ulaw_table[ulaw_bytes]
      return linear.tobytes()

  def resample(data: bytes, from_rate: int, to_rate: int) -> bytes:
      """Resample audio using scipy."""
      samples = np.frombuffer(data, dtype=np.int16)
      num_samples = int(len(samples) * to_rate / from_rate)
      resampled = signal.resample(samples, num_samples)
      return resampled.astype(np.int16).tobytes()

  def lin2lin(data: bytes, from_width: int, to_width: int) -> bytes:
      """Convert between sample widths."""
      if from_width == to_width:
          return data

      dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
      samples = np.frombuffer(data, dtype=dtype_map[from_width])

      # Scale to target width
      scale = (2 ** (to_width * 8 - 1)) / (2 ** (from_width * 8 - 1))
      converted = (samples * scale).astype(dtype_map[to_width])
      return converted.tobytes()
  ```

- **Acceptance Criteria:**
  - [ ] All existing tests pass with new implementation
  - [ ] Audio quality unchanged (SNR within 0.1 dB)
  - [ ] Python 3.13 compatible
- **Verification:**
  ```python
  # Compare output with reference
  def test_ulaw_conversion():
      test_data = b'\x00\x7f\xff\x80'
      old_result = audioop.ulaw2lin(test_data, 2)  # Reference
      new_result = ulaw2lin(test_data)
      assert old_result == new_result
  ```

---

### 3.9 Metrics Collection

- **Location:** New file `python/aicc_pipeline/metrics/collector.py`
- **Problem:** No operational metrics for monitoring, alerting, or capacity planning.
- **Solution:**
  1. Implement Prometheus metrics collection
  2. Add metrics for key operations
  3. Create CloudWatch integration for AWS deployment

  ```python
  # python/aicc_pipeline/metrics/collector.py
  from prometheus_client import Counter, Histogram, Gauge, start_http_server

  # Define metrics
  CALLS_TOTAL = Counter('aicc_calls_total', 'Total calls processed', ['status'])
  CALL_DURATION = Histogram('aicc_call_duration_seconds', 'Call duration')
  ACTIVE_CALLS = Gauge('aicc_active_calls', 'Currently active calls')
  STT_LATENCY = Histogram('aicc_stt_latency_seconds', 'STT processing latency')
  UDP_PACKETS = Counter('aicc_udp_packets_total', 'UDP packets received', ['port'])
  UDP_DROPPED = Counter('aicc_udp_dropped_total', 'UDP packets dropped')
  WEBSOCKET_MESSAGES = Counter('aicc_ws_messages_total', 'WebSocket messages sent', ['type'])
  PORT_POOL_AVAILABLE = Gauge('aicc_port_pool_available', 'Available ports in pool')

  class MetricsCollector:
      def __init__(self, port=9090):
          self.port = port

      def start(self):
          start_http_server(self.port)

      def call_started(self):
          ACTIVE_CALLS.inc()

      def call_ended(self, duration: float, status: str):
          ACTIVE_CALLS.dec()
          CALLS_TOTAL.labels(status=status).inc()
          CALL_DURATION.observe(duration)

      def stt_completed(self, latency: float):
          STT_LATENCY.observe(latency)

      def packet_received(self, port: int):
          UDP_PACKETS.labels(port=str(port)).inc()

      def packet_dropped(self):
          UDP_DROPPED.inc()
  ```

- **Acceptance Criteria:**
  - [ ] Prometheus endpoint available at :9090/metrics
  - [ ] All key operations instrumented
  - [ ] Grafana dashboard template provided
- **Verification:**
  ```bash
  curl http://localhost:9090/metrics | grep aicc_
  # Should show all defined metrics
  ```

---

## 4. MEDIUM Priority (1 Month)

### 4.1 Ring Buffer for Audio

- **Location:** `python/aicc_pipeline/audio/buffer.py` (new) or integrated in pipeline
- **Problem:** Audio buffers grow unbounded during long calls, causing memory issues.
- **Solution:**
  1. Implement fixed-size ring buffer
  2. Add overflow detection
  3. Configure size based on maximum expected latency

  ```python
  # python/aicc_pipeline/audio/ring_buffer.py
  from collections import deque
  from threading import Lock

  class RingBuffer:
      def __init__(self, max_duration_seconds: float = 30.0, sample_rate: int = 16000):
          self.max_samples = int(max_duration_seconds * sample_rate)
          self.buffer = deque(maxlen=self.max_samples)
          self.overflow_count = 0
          self.lock = Lock()

      def write(self, data: bytes):
          with self.lock:
              samples = len(data) // 2  # 16-bit samples
              if len(self.buffer) + samples > self.max_samples:
                  self.overflow_count += 1
              self.buffer.extend(data)

      def read(self, num_samples: int) -> bytes:
          with self.lock:
              result = bytes(list(self.buffer)[:num_samples * 2])
              for _ in range(min(num_samples, len(self.buffer))):
                  self.buffer.popleft()
              return result
  ```

- **Acceptance Criteria:**
  - [ ] Buffer memory usage bounded at configured max
  - [ ] Overflow events tracked
  - [ ] 1-hour call uses constant memory
- **Verification:**
  ```python
  import tracemalloc
  tracemalloc.start()
  # Process 1 hour of audio
  current, peak = tracemalloc.get_traced_memory()
  assert peak < 100 * 1024 * 1024  # < 100MB
  ```

---

### 4.2 Dynamic STT Workers

- **Location:** `python/aicc_pipeline/stt/google_stt.py`
- **Problem:** Fixed `workers=2` doesn't scale with load.
- **Solution:**
  1. Implement auto-scaling based on queue depth
  2. Add min/max worker bounds
  3. Scale down during idle periods

  ```python
  # python/aicc_pipeline/stt/adaptive_executor.py
  class AdaptiveSTTExecutor:
      def __init__(self, min_workers=2, max_workers=10):
          self.min_workers = min_workers
          self.max_workers = max_workers
          self.current_workers = min_workers
          self.queue = asyncio.Queue()
          self.workers = []
          self._start_workers(min_workers)

      async def _scale_check(self):
          while True:
              queue_depth = self.queue.qsize()
              target = min(self.max_workers, max(self.min_workers, queue_depth // 5))

              if target > self.current_workers:
                  self._start_workers(target - self.current_workers)
              elif target < self.current_workers and self.queue.empty():
                  await self._stop_workers(self.current_workers - target)

              await asyncio.sleep(5)
  ```

- **Acceptance Criteria:**
  - [ ] Workers scale up when queue > 10
  - [ ] Workers scale down after 30s idle
  - [ ] Metrics track worker count changes
- **Verification:**
  ```bash
  # Under load
  curl http://localhost:9090/metrics | grep stt_workers
  # Should show increased count
  ```

---

### 4.3 Node.js Error Handling

- **Location:** `stasis_app/app.js`
- **Problem:** Insufficient error handling. Unhandled rejections crash the process.
- **Solution:**
  1. Add global error handlers
  2. Implement retry logic for ARI operations
  3. Add structured logging

  ```javascript
  // stasis_app/app.js - Add at top
  process.on('uncaughtException', (error) => {
      console.error('Uncaught Exception:', error);
      // Attempt graceful shutdown
      cleanup().then(() => process.exit(1));
  });

  process.on('unhandledRejection', (reason, promise) => {
      console.error('Unhandled Rejection at:', promise, 'reason:', reason);
  });

  // Retry wrapper
  async function withRetry(operation, maxRetries = 3, delay = 1000) {
      for (let i = 0; i < maxRetries; i++) {
          try {
              return await operation();
          } catch (error) {
              if (i === maxRetries - 1) throw error;
              console.warn(`Retry ${i + 1}/${maxRetries} after error:`, error.message);
              await new Promise(r => setTimeout(r, delay * (i + 1)));
          }
      }
  }

  // Example usage
  async function createSnoop(channel, options) {
      return withRetry(() => channel.snoop(options));
  }
  ```

- **Acceptance Criteria:**
  - [ ] No unhandled rejection crashes
  - [ ] ARI operations retry on transient failures
  - [ ] Error context preserved in logs
- **Verification:**
  ```bash
  # Simulate ARI failure
  sudo systemctl stop asterisk
  # App should log errors and attempt reconnect, not crash
  journalctl -u aicc-stasis -f
  ```

---

### 4.4 ActiveCalls Memory Management

- **Location:** `stasis_app/app.js` - activeCalls Map
- **Problem:** Calls not properly cleaned up on errors leave orphan entries.
- **Solution:**
  1. Add TTL-based automatic cleanup
  2. Implement periodic garbage collection
  3. Add leak detection metrics

  ```javascript
  // stasis_app/app.js
  class ActiveCallsManager {
      constructor(ttlMs = 3600000) { // 1 hour default TTL
          this.calls = new Map();
          this.ttlMs = ttlMs;
          this._startCleanupInterval();
      }

      set(callId, data) {
          this.calls.set(callId, {
              ...data,
              createdAt: Date.now()
          });
      }

      get(callId) {
          const entry = this.calls.get(callId);
          return entry ? entry : null;
      }

      delete(callId) {
          return this.calls.delete(callId);
      }

      _startCleanupInterval() {
          setInterval(() => {
              const now = Date.now();
              for (const [callId, data] of this.calls) {
                  if (now - data.createdAt > this.ttlMs) {
                      console.warn(`Cleaning up stale call: ${callId}`);
                      this.delete(callId);
                  }
              }
          }, 60000); // Check every minute
      }

      get size() {
          return this.calls.size;
      }
  }

  const activeCalls = new ActiveCallsManager();
  ```

- **Acceptance Criteria:**
  - [ ] Stale calls cleaned up after TTL
  - [ ] Cleanup logged for debugging
  - [ ] Memory stable over 24 hours
- **Verification:**
  ```javascript
  // In tests
  activeCalls.set('test', {});
  // Fast forward time
  jest.advanceTimersByTime(3600001);
  expect(activeCalls.size).toBe(0);
  ```

---

### 4.5 Deque for O(1) Operations

- **Location:** `python/aicc_pipeline/vad/detector.py:180` (ONLY occurrence in codebase)
- **Problem:** `list.pop(0)` is O(n). Causes performance issues with large buffers.
- **Solution:**
  1. Replace with `collections.deque`
  2. Use `popleft()` for O(1) removal

  ```python
  # python/aicc_pipeline/vad/detector.py - Update _history initialization and usage
  from collections import deque

  # In __init__:
  self._history = deque(maxlen=self.smoothing_window)

  # At line 180, replace:
  # OLD: self._history.pop(0)
  # With: (not needed - deque with maxlen auto-removes oldest)
  def _get_smoothed_confidence(self, confidence: float) -> float:
      """Apply smoothing window to confidence."""
      self._history.append(confidence)
      # No need to manually pop - deque maxlen handles it
      return sum(self._history) / len(self._history)
  ```

- **Acceptance Criteria:**
  - [ ] No `list.pop(0)` in codebase
  - [ ] Performance test shows O(1) behavior
- **Verification:**
  ```bash
  grep -r "\.pop(0)" python/ --include="*.py"
  # Should return empty
  ```

---

### 4.6 Zero-Downtime Deployment

- **Location:** `deploy.sh`, `terraform/`
- **Problem:** Current deployment requires service interruption.
- **Solution:**
  1. Implement blue-green deployment
  2. Add health check gates
  3. Create rollback automation

  ```bash
  # scripts/deploy_blue_green.sh
  #!/bin/bash
  set -e

  ACTIVE=$(aws elbv2 describe-target-groups --query "TargetGroups[?TargetGroupName=='aicc-active'].TargetGroupArn" --output text)
  STANDBY=$(aws elbv2 describe-target-groups --query "TargetGroups[?TargetGroupName=='aicc-standby'].TargetGroupArn" --output text)

  # Deploy to standby
  ./deploy.sh --target standby

  # Wait for health
  aws elbv2 wait target-in-service --target-group-arn $STANDBY

  # Switch traffic
  aws elbv2 modify-listener --listener-arn $LISTENER --default-actions Type=forward,TargetGroupArn=$STANDBY

  # Keep old active for rollback (5 min)
  sleep 300

  # Swap names
  aws elbv2 add-tags --resource-arns $STANDBY --tags Key=Name,Value=aicc-active
  aws elbv2 add-tags --resource-arns $ACTIVE --tags Key=Name,Value=aicc-standby
  ```

- **Acceptance Criteria:**
  - [ ] Zero dropped calls during deployment
  - [ ] Rollback completes in < 30 seconds
  - [ ] Health checks gate traffic switch
- **Verification:**
  ```bash
  # During deployment
  while true; do curl -s http://lb/health | jq .status; sleep 1; done
  # Should never show unhealthy
  ```

---

### 4.7 Rollback Strategy

- **Location:** `scripts/rollback.sh` (new)
- **Problem:** No automated rollback on deployment failure.
- **Solution:**
  1. Create versioned deployment artifacts
  2. Implement one-command rollback
  3. Add deployment history tracking

  ```bash
  # scripts/rollback.sh
  #!/bin/bash
  set -e

  VERSIONS_DIR="/opt/aicc/versions"
  CURRENT_LINK="/opt/aicc/current"

  list_versions() {
      ls -1t $VERSIONS_DIR | head -10
  }

  rollback() {
      local target=${1:-$(ls -1t $VERSIONS_DIR | sed -n '2p')}  # Previous version

      if [[ ! -d "$VERSIONS_DIR/$target" ]]; then
          echo "Version not found: $target"
          exit 1
      fi

      echo "Rolling back to: $target"
      ln -sfn "$VERSIONS_DIR/$target" "$CURRENT_LINK"
      sudo systemctl restart aicc-pipeline
      sudo systemctl restart aicc-stasis

      echo "Waiting for health..."
      for i in {1..30}; do
          if curl -sf http://localhost:8080/health/ready; then
              echo "Rollback successful"
              exit 0
          fi
          sleep 1
      done

      echo "ERROR: Health check failed after rollback"
      exit 1
  }

  case $1 in
      list) list_versions ;;
      *) rollback "$1" ;;
  esac
  ```

- **Acceptance Criteria:**
  - [ ] Last 5 versions retained
  - [ ] Rollback completes in < 60 seconds
  - [ ] Health verified after rollback
- **Verification:**
  ```bash
  ./rollback.sh list  # Shows available versions
  ./rollback.sh v1.2.3  # Rolls back to specific version
  ```

---

### 4.8 CORS Configuration

- **Location:** `config/ari.conf:9` (`allowed_origins=*`)
- **Problem:** `allowed_origins=*` allows any origin. Security risk for cross-site requests.
- **Solution:**
  1. Restrict to known origins
  2. Add environment-based configuration

  ```ini
  ; config/ari.conf - Update line 9
  [general]
  enabled=yes
  pretty=yes
  ; Production: restrict to known origins (was: allowed_origins=*)
  allowed_origins=https://admin.aicc.example.com,https://dashboard.aicc.example.com
  ```

- **Acceptance Criteria:**
  - [ ] Only listed origins allowed
  - [ ] Unknown origins receive CORS error
- **Verification:**
  ```bash
  # From allowed origin - should work
  curl -H "Origin: https://admin.aicc.example.com" http://localhost:8088/ari/asterisk/info
  # From unknown origin - should fail CORS
  curl -H "Origin: https://evil.com" http://localhost:8088/ari/asterisk/info
  ```

---

### 4.9 RDS Deletion Protection

- **Location:** `terraform/main.tf` (if RDS exists)
- **Problem:** Database can be accidentally deleted.
- **Solution:**
  1. Enable deletion protection
  2. Add lifecycle rules

  ```hcl
  # terraform/main.tf
  resource "aws_db_instance" "aicc" {
    # ... existing config ...

    deletion_protection = true

    lifecycle {
      prevent_destroy = true
    }

    # Backups
    backup_retention_period = 7
    backup_window           = "03:00-04:00"

    # Maintenance
    maintenance_window = "sun:04:00-sun:05:00"
    auto_minor_version_upgrade = true
  }
  ```

- **Acceptance Criteria:**
  - [ ] `terraform destroy` cannot delete RDS
  - [ ] Manual AWS console deletion blocked
  - [ ] Daily backups retained for 7 days
- **Verification:**
  ```bash
  terraform plan -destroy
  # Should show RDS protected from destruction
  ```

---

## 5. Dependency and Execution Order

```
Phase 1: CRITICAL (Parallel where possible)
+-- 2.1 Multi-Call Support (CallSession + PortPool) ---+
+-- 2.2 ARI Credentials Security (Independent)        |
+-- 2.3 SIP Password Security (Independent)           |
+-- 2.4 Terraform State Security (Independent)        |
+-- 2.5 Health Check Implementation -------------------+-> Depends on 2.1 (port pool status)
+-- 2.6 Async Task Tracking (Independent)             |
                                                      |
Phase 2: HIGH (After Phase 1)                         |
+-- 3.1 Call Metadata Sync ----------------------------+ Depends on 2.1 (multi-call)
+-- 3.2 Streaming STT ---------------------------------> Independent
+-- 3.3 WebSocket Auth (OUTBOUND) ---------------------> Independent
+-- 3.4 UDP Network Security --------------------------> Depends on 2.1 (dynamic ports)
+-- 3.5 ARI HTTP Binding ------------------------------> After 2.2 (combined security update)
+-- 3.6 ThreadPoolExecutor Cleanup --------------------> Before 3.2 (STT refactor)
+-- 3.7 Non-Blocking UDP (DatagramProtocol) -----------> After 3.4 (UDP refactor)
+-- 3.8 Audioop Migration -----------------------------> Independent
+-- 3.9 Metrics Collection ----------------------------> After 2.5 (health integration)

Phase 3: MEDIUM (After Phase 2)
+-- 4.1 Ring Buffer ----------------------------------> Independent
+-- 4.2 Dynamic STT Workers --------------------------> After 3.2 (streaming STT)
+-- 4.3 Node.js Error Handling -----------------------> Independent
+-- 4.4 ActiveCalls Memory ---------------------------> After 4.3 (error handling first)
+-- 4.5 Deque Optimization (vad/detector.py:180) -----> With 4.1 (buffer refactor)
+-- 4.6 Zero-Downtime Deployment ---------------------> After all code changes
+-- 4.7 Rollback Strategy ----------------------------> With 4.6 (deployment refactor)
+-- 4.8 CORS Configuration (allowed_origins) ---------> With 3.5 (ARI security)
+-- 4.9 RDS Deletion Protection ----------------------> Independent
```

---

## 6. Risk Factors and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Multi-call refactor breaks existing functionality | HIGH | MEDIUM | Feature flag for gradual rollout; extensive integration testing |
| Credential rotation causes service disruption | HIGH | LOW | Test in staging; document rollback procedure |
| Streaming STT increases costs | MEDIUM | HIGH | Monitor usage; implement request throttling |
| UDP security breaks Asterisk integration | HIGH | MEDIUM | Test all configurations; keep whitelist updatable |
| Blue-green deployment complexity | MEDIUM | MEDIUM | Start with manual process; automate incrementally |
| Python 3.13 migration issues | LOW | LOW | Test with Python 3.13 in CI before upgrade |

### Rollback Procedures

**If Multi-Call breaks:**
```bash
export LEGACY_FIXED_PORTS=true
sudo systemctl restart aicc-pipeline
```

**If Credential change breaks ARI:**
```bash
# Restore old password temporarily
sudo cp /etc/asterisk/ari.conf.bak /etc/asterisk/ari.conf
sudo asterisk -rx "core reload"
```

**If Streaming STT fails:**
```bash
# Fall back to batch STT
export STT_MODE=batch
sudo systemctl restart aicc-pipeline
```

---

## 7. Verification Checklist

### Phase 1 Complete Criteria
- [ ] 10 concurrent calls work without issues
- [ ] No hardcoded passwords in codebase (`grep -r "password.*=" | wc -l` = 0 in code)
- [ ] Terraform state in S3 with encryption (and removed from git history)
- [ ] Health endpoint returns 200 with all components healthy
- [ ] All background tasks tracked (zero orphan tasks after shutdown)
- [ ] Each agent has unique SIP password

### Phase 2 Complete Criteria
- [ ] WebSocket metadata includes accurate caller info
- [ ] STT latency < 500ms (p95)
- [ ] Outbound WebSocket connections include auth headers
- [ ] UDP rejects non-whitelisted sources
- [ ] ARI not accessible from external network
- [ ] No thread leaks after STT shutdown
- [ ] 10k pps UDP throughput without loss
- [ ] Python 3.13 compatibility (audioop removed)
- [ ] Prometheus metrics available

### Phase 3 Complete Criteria
- [ ] Memory stable over 24 hours
- [ ] STT workers scale with load
- [ ] No unhandled exceptions in logs
- [ ] Stale calls auto-cleaned
- [ ] No O(n) list operations (no `.pop(0)` in codebase)
- [ ] Zero-downtime deployment works
- [ ] Rollback completes in < 60s
- [ ] CORS restricted to known origins
- [ ] RDS deletion protected

### Production Readiness Final Check
- [ ] All CRITICAL items complete
- [ ] All HIGH items complete or have approved exception
- [ ] Load test: 50 concurrent calls for 1 hour
- [ ] Security scan: no HIGH/CRITICAL findings
- [ ] Documentation updated
- [ ] Runbook created for operations
- [ ] Alerts configured for key metrics
- [ ] Disaster recovery tested

---

## 8. Test Scaffolding

The following test files need to be created as part of implementation:

1. **`tests/load_test_concurrent_calls.py`** - Multi-call load testing
   - Simulates N concurrent calls
   - Verifies port allocation/release
   - Measures throughput and latency

2. **`tests/udp_load_test.py`** - UDP packet load testing
   - Sends configurable PPS (packets per second)
   - Measures packet loss rate
   - Verifies non-blocking behavior

---

## 9. Commit Strategy

### Commit 1: Security Foundations
```
feat(security): environment-based credential management

- Move ARI credentials to environment variables
- Generate unique SIP passwords per agent
- Configure Terraform S3 backend with encryption
- Remove tfstate from git history
- Update .gitignore for sensitive files

BREAKING CHANGE: ARI_PASSWORD env var now required
```

### Commit 2: Multi-Call Architecture
```
feat(core): implement multi-call support with dynamic port allocation

- Add PortPool for dynamic UDP port management
- Define CallSession dataclass for call state
- Implement port-to-call mapping for UDP packet routing
- Replace single _call_id with sessions registry
- Add LEGACY_FIXED_PORTS flag for backward compatibility
- Add ValueError on port pool exhaustion
```

### Commit 3: Observability
```
feat(ops): add health checks and metrics collection

- Implement /health/live and /health/ready endpoints
- Add Prometheus metrics for calls, STT, UDP, WebSocket
- Create Grafana dashboard template
- Integrate with AWS ALB health checks
```

### Commit 4: Async Task Management
```
fix(core): proper async task tracking and cleanup

- Add TaskRegistry for background task management
- Implement graceful shutdown with timeout
- Log failed tasks with context
- Fix ThreadPoolExecutor leak in STT service
```

### Commit 5: Network Security
```
feat(security): network layer hardening

- Bind ARI HTTP to localhost only
- Add UDP source IP whitelist
- Implement WebSocket JWT auth for outbound connections
- Add nginx reverse proxy configuration
- Restrict CORS to known origins (allowed_origins)
```

### Commit 6: Streaming STT
```
feat(stt): migrate to Google Speech V2 streaming API

- Implement bidirectional streaming recognition
- Add interim results support
- Create fallback to batch mode
- Maintain backward compatible API
```

### Commit 7: Performance Optimizations
```
perf: buffer and collection optimizations

- Replace audioop with scipy.signal
- Implement ring buffer for bounded memory
- Convert list.pop(0) to deque at vad/detector.py:180
- Refactor UDP receiver to use DatagramProtocol with async queue
```

### Commit 8: Deployment Infrastructure
```
feat(deploy): zero-downtime deployment with rollback

- Implement blue-green deployment script
- Add version management and rollback
- Create health-gated traffic switching
- Enable RDS deletion protection
```

---

**PLAN_READY: .omc/plans/aicc-pipeline-improvement.md**
