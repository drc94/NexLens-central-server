from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Diccionarios de websockets conectados
# -----------------------------
devices = {}
viewers = {}

class Command(BaseModel):
    method: str
    endpoint: str
    body: dict | None = None

# -----------------------------
# WebSocket para dispositivos (Raspberry Pi)
# -----------------------------
@app.websocket("/ws/{device_id}")
async def device_ws(websocket: WebSocket, device_id: str):
    await websocket.accept()
    devices[device_id] = websocket
    print(f"Dispositivo {device_id} conectado.")
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Recibido de {device_id}: {data[:100]}...")  # Log solo primeros 100 chars
            
            # Reenviar frames a todos los viewers
            try:
                message_data = json.loads(data)
                if message_data.get("type") == "video_frame":
                    await broadcast_to_viewers(message_data)
            except json.JSONDecodeError:
                print(f"Mensaje no JSON de {device_id}")
                
    except Exception as e:
        print(f"Conexión cerrada {device_id}: {e}")
    finally:
        devices.pop(device_id, None)

# -----------------------------
# WebSocket para viewers (navegadores)
# -----------------------------
@app.websocket("/ws/viewer")
async def viewer_ws(websocket: WebSocket):
    await websocket.accept()
    viewer_id = f"viewer_{id(websocket)}"
    viewers[viewer_id] = websocket
    print(f"Viewer {viewer_id} conectado.")
    
    try:
        while True:
            # Los viewers pueden enviar mensajes de control si es necesario
            data = await websocket.receive_text()
            print(f"Recibido de viewer {viewer_id}: {data}")
    except Exception as e:
        print(f"Conexión cerrada viewer {viewer_id}: {e}")
    finally:
        viewers.pop(viewer_id, None)

# -----------------------------
# Función para broadcast a todos los viewers
# -----------------------------
async def broadcast_to_viewers(message: dict):
    if not viewers:
        return
        
    disconnected = []
    for viewer_id, websocket in viewers.items():
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            print(f"Error enviando a viewer {viewer_id}: {e}")
            disconnected.append(viewer_id)
    
    # Limpiar viewers desconectados
    for viewer_id in disconnected:
        viewers.pop(viewer_id, None)

# -----------------------------
# Enviar comandos HTTP / WebRTC
# -----------------------------
@app.post("/send/{device_id}")
async def send_command(device_id: str, cmd: Command):
    if device_id not in devices:
        return {"status": "device not connected"}
    
    await devices[device_id].send_text(json.dumps(cmd.dict()))
    return {"status": "ok"}

# -----------------------------
# Diccionarios para ofertas/respuestas
# -----------------------------
offers = {}
answers = {}

class SDP(BaseModel):
    sdp: str
    device_id: str

# -----------------------------
# Recibir offer de la Raspberry
# -----------------------------
@app.post("/answer")
async def receive_offer(sdp: SDP):
    offers[sdp.device_id] = sdp.sdp
    return {"status": "ok"}

@app.get("/answer/{device_id}")
async def get_offer(device_id: str):
    return {"sdp": offers.get(device_id)}

# -----------------------------
# Recibir answer del navegador y enviarlo al dispositivo
# -----------------------------
@app.post("/offer")
async def receive_answer(sdp: SDP):
    answers[sdp.device_id] = sdp.sdp

    # Enviar answer al dispositivo vía WebSocket
    ws = devices.get(sdp.device_id)
    if ws:
        await ws.send_text(json.dumps({
            "method": "WEBRTC_ANSWER",
            "endpoint": "",
            "body": {"sdp": sdp.sdp, "device_id": sdp.device_id}
        }))
        print(f"[Render] Answer enviada a {sdp.device_id}")

    return {"status": "ok"}

@app.get("/offer/{device_id}")
async def get_answer(device_id: str):
    return {"sdp": answers.get(device_id)}

# -----------------------------
# Endpoints de estado
# -----------------------------
@app.get("/status")
async def get_status():
    return {
        "devices_connected": list(devices.keys()),
        "viewers_connected": len(viewers),
        "total_connections": len(devices) + len(viewers)
    }

@app.get("/")
async def root():
    return {
        "message": "Servidor de video WebRTC funcionando",
        "endpoints": {
            "websocket_device": "/ws/{device_id}",
            "websocket_viewer": "/ws/viewer", 
            "status": "/status",
            "send_command": "/send/{device_id}",
            "webrtc_offer": "/offer",
            "webrtc_answer": "/answer"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
