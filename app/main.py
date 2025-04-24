from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from app.services import WhisperService
import os
from dotenv import load_dotenv
import logging
import io
from starlette.websockets import WebSocketState

load_dotenv()

app = FastAPI()

# Configura logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instancia el servicio Whisper
whisper_service = WhisperService(api_key=os.getenv("OPENAI_API_KEY"))

# Archivos estáticos
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("app/static/index.html")

@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔌 WebSocket conectado")

    try:
        async def audio_generator():
            """Genera chunks de audio desde el WebSocket"""
            while True:
                try:
                    data = await websocket.receive_bytes()
                    logger.info(f"🎧 Recibido {len(data)} bytes")
                    yield data
                except WebSocketDisconnect:
                    logger.info("❌ Cliente desconectado")
                    break
                except Exception as e:
                    logger.error(f"⚠️ Error al recibir audio: {str(e)}")
                    break

        transcription_generator = whisper_service.transcribe_stream(audio_generator())

        # Iterar sobre las transcripciones generadas
        async for transcription in transcription_generator:
            if transcription:
                try:
                    # Mostrar la transcripción en la consola
                    logger.info(f"🗣️ Transcripción: {transcription}")

                    if websocket.client_state == WebSocketState.CONNECTED:
                        # Enviar transcripción al cliente WebSocket
                        await websocket.send_text(transcription)
                    else:
                        logger.warning("🔌 WebSocket desconectado antes de enviar texto")
                        break
                except Exception as e:
                    logger.error(f"⚠️ Error al enviar texto: {str(e)}")
                    break

    except Exception as e:
        logger.error(f"🚨 Error en WebSocket: {str(e)}")

    finally:
        if websocket.client_state in (WebSocketState.CONNECTED, WebSocketState.CONNECTING):
            try:
                await websocket.close()
                logger.info("🔒 WebSocket cerrado correctamente")
            except Exception as e:
                logger.warning(f"⚠️ WebSocket ya cerrado o error al cerrar: {str(e)}")



@app.post("/transcribe-webm")
async def transcribe_webm(file: UploadFile = File(...)):
    try:
        webm_bytes = await file.read()
        wav_bytes = whisper_service.convert_webm_to_wav(webm_bytes)

        if not wav_bytes:
            return JSONResponse(content={"error": "Error al convertir el archivo WebM a WAV"}, status_code=400)

        wav_buffer = io.BytesIO(wav_bytes)
        transcription = await whisper_service._transcribe_audio(wav_buffer, language="es")

        if not transcription:
            return JSONResponse(content={"error": "No se pudo obtener una transcripción"}, status_code=500)

        return {"transcription": transcription}

    except Exception as e:
        logger.error(f"Error procesando archivo webm: {str(e)}")
        return JSONResponse(content={"error": "Error interno del servidor"}, status_code=500)
