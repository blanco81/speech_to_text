import io
import re
import asyncio
import wave
import tempfile
from typing import AsyncGenerator
from openai import OpenAI

class WhisperService:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.sample_rate = 16000
        self.ffmpeg_process = None
        self.buffer_size = 40960  # ~1.3 segundos de audio
        self.chunk_size = self.sample_rate * 2 * 2  # 2 segundos: 16kHz * 2 bytes * 2 seg

    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None], language: str = "es") -> AsyncGenerator[str, None]:
        """Transcribe y envía fragmentos de texto parcialmente en tiempo real"""
        try:
            self.ffmpeg_process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-f", "webm",
                "-i", "pipe:0",
                "-acodec", "pcm_s16le",
                "-ar", str(self.sample_rate),
                "-ac", "1",
                "-f", "wav",
                "-flush_packets", "1",
                "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            buffer = bytearray()

            async def feed_ffmpeg():
                async for chunk in audio_stream:
                    self.ffmpeg_process.stdin.write(chunk)
                    await self.ffmpeg_process.stdin.drain()
                self.ffmpeg_process.stdin.close()

            writer_task = asyncio.create_task(feed_ffmpeg())

            while True:
                pcm_chunk = await self.ffmpeg_process.stdout.read(self.buffer_size)
                if not pcm_chunk:
                    break

                buffer.extend(pcm_chunk)

                while len(buffer) >= self.chunk_size:
                    window = buffer[:self.chunk_size]
                    buffer = buffer[self.chunk_size:]

                    text = await self._transcribe_from_pcm(window, language)
                    if text:
                        print(f"🗣️ Fragmento: {text}")
                        yield text  # envía texto parcial al frontend

            # Transcribe cualquier resto de audio
            if buffer:
                text = await self._transcribe_from_pcm(buffer, language)
                if text:
                    print(f"🗣️ Final: {text}")
                    yield text

            await writer_task

        finally:
            await self._cleanup()

    async def _transcribe_from_pcm(self, pcm_data: bytes, language: str) -> str:
        """Transcribe fragmentos PCM"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            with wave.open(temp_file, 'wb') as wav_writer:
                wav_writer.setnchannels(1)
                wav_writer.setsampwidth(2)
                wav_writer.setframerate(self.sample_rate)
                wav_writer.writeframes(pcm_data)

            temp_file_path = temp_file.name

        try:
            with open(temp_file_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    prompt="Transcripción clara en español.",
                    temperature=0.2
                )
            return self._clean_text(response.text)
        except Exception as e:
            print(f"❌ Error transcribiendo archivo: {e}")
            return ""

    def _clean_text(self, text: str) -> str:
        """Limpia texto de basura o metadatos"""
        patterns = [
            r"Subtítulos?[\s\S]*Amara\.org",
            r"\bAmara\b",
            r"\[.*?\]",
            r"^\s*$"
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return re.sub(r'\s+', ' ', text).strip()

    async def _cleanup(self):
        """Libera recursos del proceso"""
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.stdin.close()
                await self.ffmpeg_process.wait()
            except Exception as e:
                print(f"⚠️ Error limpiando recursos: {str(e)[:200]}")
