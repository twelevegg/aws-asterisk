"""
Continuous STT Session with Automatic 4.5-Minute Rotation.

Manages long-running STT sessions with warm standby rotation to avoid
Google Cloud Speech V2's 5-minute streaming limit.
"""

import asyncio
import logging
import time
from typing import Optional, Callable, Awaitable

from .streaming_stt import StreamingSTT, StreamingSTTSession, StreamingResult

logger = logging.getLogger("aicc.continuous_stt")


class ContinuousSTTSession:
    """
    Continuous STT session with automatic rotation.

    Features:
    - 4.5-minute rotation timer (270 seconds)
    - Warm standby session for seamless rotation
    - 2-second audio buffering during rotation
    - Transcript accumulation across rotations
    - 3-retry fallback to synchronous rotation

    Usage:
        session = ContinuousSTTSession(stt, call_id="123", speaker="customer")
        await session.start(result_callback)
        await session.feed_audio(audio_bytes)
        transcript = session.snapshot_transcript()  # Get and reset
        await session.stop()
    """

    ROTATION_INTERVAL = 270.0  # 4.5 minutes in seconds
    BUFFER_DURING_ROTATION = 2.0  # seconds
    STANDBY_RETRY_DELAY = 5.0  # seconds before retry
    MAX_STANDBY_RETRIES = 3

    def __init__(
        self,
        stt: StreamingSTT,
        call_id: str,
        speaker: str,
        rotation_interval: Optional[float] = None,
    ):
        """
        Initialize continuous session manager.

        Args:
            stt: StreamingSTT instance
            call_id: Call identifier
            speaker: Speaker identifier (customer/agent)
            rotation_interval: Override default rotation interval (seconds)
        """
        self._stt = stt
        self._call_id = call_id
        self._speaker = speaker
        self._rotation_interval = rotation_interval or self.ROTATION_INTERVAL

        self._active_session: Optional[StreamingSTTSession] = None
        self._standby_session: Optional[StreamingSTTSession] = None
        self._rotation_buffer: list[bytes] = []
        self._accumulated_transcript = ""
        self._rotation_timer: Optional[asyncio.Task] = None
        self._result_callback: Optional[Callable[[StreamingResult], Awaitable[None]]] = None

        self._is_rotating = False
        self._standby_failed = False  # Fallback mode flag
        self._running = False
        self._session_start_time: Optional[float] = None

    async def start(self, result_callback: Callable[[StreamingResult], Awaitable[None]]) -> None:
        """
        Start continuous STT session.

        Args:
            result_callback: Async callback(StreamingResult) for STT results

        Raises:
            Exception: If session start fails (gRPC connection error, etc.)
        """
        if self._running:
            logger.warning(f"[{self._call_id}:{self._speaker}] Session already running")
            return

        self._result_callback = result_callback
        self._running = True
        self._session_start_time = time.time()

        # Start initial active session
        try:
            self._active_session = self._create_session()
            await self._active_session.start(self._on_streaming_result)
            logger.info(
                f"[{self._call_id}:{self._speaker}] Continuous STT session started "
                f"(rotation interval: {self._rotation_interval}s)"
            )
        except Exception as e:
            self._running = False
            logger.error(f"[{self._call_id}:{self._speaker}] Failed to start session: {e}")
            raise

        # Schedule rotation timer
        self._rotation_timer = asyncio.create_task(self._rotation_scheduler())

        # Prepare standby session asynchronously (non-blocking)
        asyncio.create_task(self._prepare_standby_session())

    async def feed_audio(self, audio_data: bytes) -> None:
        """
        Feed audio data to active session.

        During rotation, audio is buffered and replayed to the new session.

        Args:
            audio_data: PCM LINEAR16 audio bytes (16kHz, mono)
        """
        if not self._running:
            return

        if self._is_rotating:
            # Buffer audio during rotation
            self._rotation_buffer.append(audio_data)
            # Limit buffer size (2 seconds at 16kHz, 16-bit, mono = ~64KB)
            max_buffer_size = int(self.BUFFER_DURING_ROTATION * 16000 * 2)  # 2 bytes per sample
            total_size = sum(len(chunk) for chunk in self._rotation_buffer)
            if total_size > max_buffer_size:
                # Drop oldest chunks to maintain size limit
                while total_size > max_buffer_size and self._rotation_buffer:
                    dropped = self._rotation_buffer.pop(0)
                    total_size -= len(dropped)
        else:
            # Normal operation: feed to active session
            if self._active_session:
                await self._active_session.feed_audio(audio_data)

    def snapshot_transcript(self) -> str:
        """
        Get accumulated transcript and reset.

        Used when turn boundary is detected to extract transcript
        without stopping the session.

        Returns:
            Accumulated transcript string (empty string if none)
        """
        transcript = self._accumulated_transcript
        self._accumulated_transcript = ""
        return transcript

    async def stop(self) -> None:
        """
        Stop continuous session and clean up resources.

        Gracefully terminates active and standby sessions.
        """
        if not self._running:
            return

        self._running = False

        # Cancel rotation timer
        if self._rotation_timer:
            self._rotation_timer.cancel()
            try:
                await self._rotation_timer
            except asyncio.CancelledError:
                pass

        # Stop active session
        if self._active_session:
            await self._active_session.stop()
            self._active_session = None

        # Stop standby session
        if self._standby_session:
            await self._standby_session.stop()
            self._standby_session = None

        if self._session_start_time:
            duration_sec = time.time() - self._session_start_time
            logger.info(
                f"[{self._call_id}:{self._speaker}] Continuous session stopped "
                f"(duration: {duration_sec:.1f}s)"
            )

    # --- Internal Methods ---

    def _create_session(self) -> StreamingSTTSession:
        """Create a new StreamingSTTSession instance."""
        return StreamingSTTSession(
            stt=self._stt,
            call_id=self._call_id,
            speaker=self._speaker,
        )

    async def _on_streaming_result(self, result: StreamingResult) -> None:
        """
        Internal callback for streaming results.

        Accumulates final transcripts and forwards to user callback.
        """
        # Accumulate final transcripts
        if result.is_final and result.transcript.strip():
            if self._accumulated_transcript:
                self._accumulated_transcript += " " + result.transcript
            else:
                self._accumulated_transcript = result.transcript

        # Forward to user callback
        if self._result_callback:
            await self._result_callback(result)

    async def _rotation_scheduler(self) -> None:
        """
        Background task that triggers session rotation.

        Runs every ROTATION_INTERVAL seconds.
        """
        try:
            while self._running:
                await asyncio.sleep(self._rotation_interval)
                if self._running:
                    logger.info(f"[{self._call_id}:{self._speaker}] Rotation timer triggered")
                    await self._rotate_session()
        except asyncio.CancelledError:
            logger.debug(f"[{self._call_id}:{self._speaker}] Rotation scheduler cancelled")
        except Exception as e:
            logger.error(f"[{self._call_id}:{self._speaker}] Rotation scheduler error: {e}")

    async def _prepare_standby_session(self) -> bool:
        """
        Prepare standby session with retry logic.

        Returns:
            True if standby ready, False if failed and entering fallback mode
        """
        for attempt in range(self.MAX_STANDBY_RETRIES):
            try:
                self._standby_session = self._create_session()
                await self._standby_session.start(self._on_streaming_result)
                logger.info(
                    f"[{self._call_id}:{self._speaker}] Standby session ready "
                    f"(attempt {attempt + 1}/{self.MAX_STANDBY_RETRIES})"
                )
                self._standby_failed = False
                return True
            except Exception as e:
                logger.warning(
                    f"[{self._call_id}:{self._speaker}] Standby session creation failed "
                    f"(attempt {attempt + 1}/{self.MAX_STANDBY_RETRIES}): {e}"
                )
                if self._standby_session:
                    try:
                        await self._standby_session.stop()
                    except Exception:
                        pass
                    self._standby_session = None

                if attempt < self.MAX_STANDBY_RETRIES - 1:
                    await asyncio.sleep(self.STANDBY_RETRY_DELAY)

        # All retries failed - enter fallback mode
        logger.error(
            f"[{self._call_id}:{self._speaker}] All standby attempts failed, "
            "entering fallback mode (synchronous rotation)"
        )
        self._standby_failed = True
        return False

    async def _rotate_session(self) -> None:
        """
        Rotate active session to avoid 5-minute limit.

        Strategy:
        - If standby ready: Instant swap (warm standby)
        - If standby failed: Synchronous rotation with buffering
        """
        self._is_rotating = True

        try:
            if self._standby_failed or not self._standby_session:
                # Fallback: Synchronous rotation
                await self._rotate_session_fallback()
            else:
                # Normal: Warm standby rotation
                await self._rotate_session_normal()
        except Exception as e:
            logger.error(f"[{self._call_id}:{self._speaker}] Rotation failed: {e}")
            # Attempt recovery
            try:
                await self._rotate_session_fallback()
            except Exception as recovery_error:
                logger.critical(
                    f"[{self._call_id}:{self._speaker}] Rotation recovery failed: {recovery_error}"
                )
                self._running = False
        finally:
            self._is_rotating = False

    async def _rotate_session_normal(self) -> None:
        """
        Normal rotation using warm standby session.

        Steps:
        1. Swap active -> standby
        2. Flush buffered audio to new active
        3. Stop old session in background
        4. Prepare next standby
        """
        logger.info(f"[{self._call_id}:{self._speaker}] Rotating session (warm standby)")

        old_session = self._active_session
        self._active_session = self._standby_session
        self._standby_session = None

        # Flush rotation buffer to new active session
        for audio in self._rotation_buffer:
            if self._active_session:
                await self._active_session.feed_audio(audio)
        self._rotation_buffer.clear()

        # Stop old session asynchronously (non-blocking)
        if old_session:
            asyncio.create_task(self._stop_session_safely(old_session, "old"))

        # Prepare next standby
        asyncio.create_task(self._prepare_standby_session())

    async def _rotate_session_fallback(self) -> None:
        """
        Fallback rotation without standby (synchronous).

        Used when standby preparation fails. Accepts brief interruption
        but minimizes audio loss via buffering.

        Steps:
        1. Stop old session
        2. Start new session
        3. Flush buffered audio
        4. Retry standby preparation
        """
        logger.warning(
            f"[{self._call_id}:{self._speaker}] Fallback rotation: synchronous session switch"
        )

        # Stop existing session
        if self._active_session:
            await self._active_session.stop()

        # Create and start new session
        self._active_session = self._create_session()
        await self._active_session.start(self._on_streaming_result)

        # Flush buffered audio
        for audio in self._rotation_buffer:
            await self._active_session.feed_audio(audio)
        self._rotation_buffer.clear()

        # Retry standby preparation
        self._standby_failed = False
        asyncio.create_task(self._prepare_standby_session())

    async def _stop_session_safely(self, session: StreamingSTTSession, label: str) -> None:
        """
        Stop a session with error handling.

        Args:
            session: Session to stop
            label: Label for logging (e.g., "old", "standby")
        """
        try:
            await session.stop()
            logger.debug(f"[{self._call_id}:{self._speaker}] Stopped {label} session")
        except Exception as e:
            logger.warning(
                f"[{self._call_id}:{self._speaker}] Error stopping {label} session: {e}"
            )
