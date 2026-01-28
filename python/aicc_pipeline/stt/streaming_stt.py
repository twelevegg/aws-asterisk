"""
Google Cloud Speech V2 Streaming STT.

Provides real-time speech-to-text with interim results.
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional, Callable, Awaitable
from dataclasses import dataclass

logger = logging.getLogger("aicc.streaming_stt")

try:
    from google.cloud.speech_v2 import SpeechAsyncClient
    from google.cloud.speech_v2.types import cloud_speech
    SPEECH_V2_AVAILABLE = True
except ImportError:
    SPEECH_V2_AVAILABLE = False
    logger.warning("google-cloud-speech v2 not available, streaming STT disabled")


@dataclass
class StreamingResult:
    """Result from streaming recognition."""
    transcript: str
    is_final: bool
    confidence: float = 0.0
    stability: float = 0.0


class StreamingSTT:
    """
    Streaming speech-to-text using Google Cloud Speech V2.

    Features:
    - Real-time transcription with interim results
    - Korean language support (ko-KR)
    - Telephony model optimized for phone calls
    """

    def __init__(
        self,
        project_id: str,
        location: str = "global",
        language_code: str = "ko-KR",
        model: str = "telephony",
        sample_rate: int = 16000,
    ):
        if not SPEECH_V2_AVAILABLE:
            raise ImportError(
                "google-cloud-speech v2 required. "
                "pip install google-cloud-speech>=2.0.0"
            )

        self.project_id = project_id
        self.location = location
        self.language_code = language_code
        self.model = model
        self.sample_rate = sample_rate

        self._client: Optional[SpeechAsyncClient] = None

    async def _get_client(self) -> SpeechAsyncClient:
        """Get or create async client."""
        if self._client is None:
            self._client = SpeechAsyncClient()
        return self._client

    def _create_config(self) -> cloud_speech.StreamingRecognitionConfig:
        """Create streaming recognition config."""
        recognition_config = cloud_speech.RecognitionConfig(
            explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.sample_rate,
                audio_channel_count=1,
            ),
            language_codes=[self.language_code],
            model=self.model,
        )

        streaming_config = cloud_speech.StreamingRecognitionConfig(
            config=recognition_config,
            streaming_features=cloud_speech.StreamingRecognitionFeatures(
                interim_results=True,
            ),
        )

        return streaming_config

    async def stream_recognize(
        self,
        audio_generator: AsyncGenerator[bytes, None],
        call_id: str = "unknown",
    ) -> AsyncGenerator[StreamingResult, None]:
        """
        Stream audio and yield transcription results.

        Args:
            audio_generator: Async generator yielding audio chunks (LINEAR16, 16kHz)
            call_id: Call ID for logging

        Yields:
            StreamingResult with transcript, is_final flag, and confidence
        """
        client = await self._get_client()
        config = self._create_config()

        recognizer = f"projects/{self.project_id}/locations/{self.location}/recognizers/_"

        async def request_generator():
            # First request with config
            yield cloud_speech.StreamingRecognizeRequest(
                recognizer=recognizer,
                streaming_config=config,
            )

            # Subsequent requests with audio
            async for chunk in audio_generator:
                if chunk:
                    yield cloud_speech.StreamingRecognizeRequest(audio=chunk)

        try:
            responses = await client.streaming_recognize(requests=request_generator())

            async for response in responses:
                for result in response.results:
                    if result.alternatives:
                        alt = result.alternatives[0]
                        yield StreamingResult(
                            transcript=alt.transcript,
                            is_final=result.is_final,
                            confidence=alt.confidence if result.is_final else 0.0,
                            stability=result.stability if hasattr(result, 'stability') else 0.0,
                        )

                        if result.is_final:
                            logger.debug(
                                f"[{call_id}] Final: '{alt.transcript}' "
                                f"(confidence: {alt.confidence:.2f})"
                            )

        except Exception as e:
            logger.error(f"[{call_id}] Streaming STT error: {e}")
            raise

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            # SpeechAsyncClient doesn't have explicit close, but we can reset
            self._client = None
            logger.debug("Streaming STT client closed")


class StreamingSTTSession:
    """
    Manages a single streaming session for one speaker.

    Handles chunking, buffering, and result aggregation.
    """

    def __init__(
        self,
        stt: StreamingSTT,
        call_id: str,
        speaker: str,
        chunk_duration_ms: int = 100,
    ):
        self.stt = stt
        self.call_id = call_id
        self.speaker = speaker
        self.chunk_duration_ms = chunk_duration_ms

        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def _audio_generator(self) -> AsyncGenerator[bytes, None]:
        """Generate audio chunks from queue."""
        while self._running:
            try:
                chunk = await asyncio.wait_for(
                    self._audio_queue.get(),
                    timeout=1.0
                )
                yield chunk
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    async def start(self, result_callback: Callable[[StreamingResult], Awaitable[None]]) -> None:
        """
        Start streaming session.

        Args:
            result_callback: Async callback(StreamingResult) for results
        """
        self._running = True

        async def process():
            try:
                async for result in self.stt.stream_recognize(
                    self._audio_generator(),
                    call_id=f"{self.call_id}:{self.speaker}"
                ):
                    await result_callback(result)
            except Exception as e:
                logger.error(f"Session error [{self.call_id}:{self.speaker}]: {e}")
            finally:
                self._running = False

        self._task = asyncio.create_task(process())
        logger.info(f"Started streaming session [{self.call_id}:{self.speaker}]")

    async def feed_audio(self, audio_data: bytes) -> None:
        """Feed audio data to the session."""
        if self._running:
            await self._audio_queue.put(audio_data)

    async def stop(self) -> None:
        """Stop the streaming session."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped streaming session [{self.call_id}:{self.speaker}]")
