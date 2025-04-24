const recordButton = document.getElementById('recordButton');
const statusElement = document.getElementById('status');
const transcriptElement = document.getElementById('transcript');

const uploadForm = document.getElementById('uploadForm');
const audioFileInput = document.getElementById('audioFile');
const uploadStatus = document.getElementById('uploadStatus');
const uploadTranscript = document.getElementById('uploadTranscript');

let mediaRecorder;
let socket;
let isRecording = false;

// Verificar compatibilidad
if (!navigator.mediaDevices?.getUserMedia || !window.WebSocket) {
    showError("Tu navegador no es compatible con esta aplicación");
    recordButton.disabled = true;
}

recordButton.addEventListener('click', toggleRecording);

async function toggleRecording() {
    if (isRecording) {
        await stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    try {
        resetUI();
        statusElement.textContent = "Iniciando...";

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/transcribe`;
        socket = new WebSocket(wsUrl);

        socket.onopen = async () => {
            console.log("✅ WebSocket conectado");

            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        channelCount: 1,
                        sampleRate: 16000,
                        sampleSize: 16,
                        echoCancellation: true,
                        noiseSuppression: true
                    },
                    video: false
                });

                mediaRecorder = new MediaRecorder(stream, {
                    mimeType: 'audio/webm;codecs=opus',
                    audioBitsPerSecond: 128000
                });

                mediaRecorder.ondataavailable = async (event) => {
                    if (event.data.size > 0 && socket?.readyState === WebSocket.OPEN) {
                        try {
                            const audioBlob = new Blob([event.data], { type: 'audio/webm' });
                            socket.send(await audioBlob.arrayBuffer());
                            console.log(`🎤 Audio enviado: ${event.data.size} bytes`);
                        } catch (error) {
                            console.error("Error enviando audio:", error);
                        }
                    }
                };

                mediaRecorder.start(1000); // Enviar chunks cada 1 segundo
                isRecording = true;
                updateUI("Escuchando... Habla ahora", "recording");

            } catch (error) {
                console.error("Error al acceder al micrófono:", error);
                showError("No se pudo acceder al micrófono");
                socket?.close();
            }
        };

        socket.onmessage = (event) => {
            const text = event.data; // El texto recibido desde Whisper
            if (text && text.trim()) { // Verificar si el texto no está vacío
                // Agregar el texto al textarea y asegurarse de que cada nueva transcripción se agregue en una nueva línea
                transcriptElement.value += text + "\n";
                transcriptElement.scrollTop = transcriptElement.scrollHeight; // Asegura que el textarea haga scroll al final
                console.log("📝 Texto actualizado en el textarea:", transcriptElement.value);
            }
        };

        socket.onerror = (error) => {
            console.error("WebSocket error:", error);
            showError("Error de conexión");
            stopRecording();
        };

        socket.onclose = () => {
            if (isRecording) {
                showError("Conexión cerrada");
                stopRecording();
            }
        };

    } catch (error) {
        console.error("Error inicial:", error);
        showError("Error al iniciar: " + error.message);
    }
}

async function stopRecording() {
    if (!isRecording) return;

    isRecording = false;
    updateUI("Finalizando...", "");

    if (mediaRecorder?.state === 'recording') {
        mediaRecorder.stop();
    }

    await new Promise(resolve => setTimeout(resolve, 1500));

    if (socket) socket.close();

    if (mediaRecorder?.stream) {
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }

    updateUI("Grabación detenida", "");
}

// Subida de archivos
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    uploadStatus.textContent = "";
    uploadStatus.className = "";
    uploadTranscript.value = "";

    const file = audioFileInput.files[0];
    if (!file) {
        uploadStatus.textContent = "Por favor, selecciona un archivo.";
        uploadStatus.className = "error";
        return;
    }

    uploadStatus.textContent = "Transcribiendo archivo...";
    
    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/transcribe-webm', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error("Error en el servidor");
        }

        const data = await response.json();
        const text = cleanText(data.transcription);
        uploadTranscript.value = text || "No se recibió ninguna transcripción.";
        uploadStatus.textContent = "✅ Transcripción completa";

    } catch (error) {
        console.error("Error en transcripción de archivo:", error);
        uploadStatus.textContent = "❌ Error al transcribir el archivo";
        uploadStatus.className = "error";
    }
});

// Funciones auxiliares
function cleanText(text) {
    if (!text) return "";
    return text
        .replace(/Subtítulos realizados por la comunidad de Amara\.org/gi, "")
        .replace(/\s+/g, ' ')
        .trim();
}

function resetUI() {
    transcriptElement.value = "";
    statusElement.className = "";
    recordButton.disabled = true;
}

function updateUI(message, className) {
    statusElement.textContent = message;
    statusElement.className = className;
    recordButton.textContent = isRecording ? "Detener Grabación" : "Comenzar Dictado";
    recordButton.disabled = false;
}

function showError(message) {
    statusElement.textContent = message;
    statusElement.className = "error";
    recordButton.disabled = false;
}
    