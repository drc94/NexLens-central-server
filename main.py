from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
from datetime import datetime

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

def log_message(source: str, message: str):
    """Función de logging consistente"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {source}: {message}")

# -----------------------------
# WebSocket para viewers (navegadores) - DEBE IR PRIMERO
# -----------------------------
@app.websocket("/ws/viewer")
async def viewer_ws(websocket: WebSocket):
    await websocket.accept()
    viewer_id = f"viewer_{id(websocket)}"
    viewers[viewer_id] = websocket
    log_message("VIEWER", f"Viewer {viewer_id} conectado. Total viewers: {len(viewers)}")
    
    try:
        while True:
            data = await websocket.receive_text()
            log_message(f"VIEWER_{viewer_id}", f"Mensaje: {data}")
    except Exception as e:
        log_message(f"VIEWER_{viewer_id}", f"Conexión cerrada: {e}")
    finally:
        viewers.pop(viewer_id, None)
        log_message("VIEWER", f"Viewer {viewer_id} desconectado. Total: {len(viewers)}")

# -----------------------------
# WebSocket para dispositivos (Raspberry Pi) - DEBE IR DESPUÉS
# -----------------------------
@app.websocket("/ws/{device_id}")
async def device_ws(websocket: WebSocket, device_id: str):
    await websocket.accept()
    devices[device_id] = websocket
    log_message("DEVICE", f"Dispositivo {device_id} conectado. Total dispositivos: {len(devices)}")
    
    try:
        while True:
            data = await websocket.receive_text()
            log_message(f"DEVICE_{device_id}", f"Mensaje recibido ({len(data)} chars)")
            
            # Reenviar frames a todos los viewers
            try:
                message_data = json.loads(data)
                message_type = message_data.get("type", "unknown")
                
                if message_type == "video_frame":
                    frame_num = message_data.get("frame_number", "N/A")
                    log_message("BROADCAST", f"Frame {frame_num} -> {len(viewers)} viewers")
                    await broadcast_to_viewers(message_data)
                else:
                    log_message(f"DEVICE_{device_id}", f"Tipo: {message_type}")
                    
            except json.JSONDecodeError as e:
                log_message(f"DEVICE_{device_id}", f"Error JSON: {e}")
                
    except Exception as e:
        log_message(f"DEVICE_{device_id}", f"Conexión cerrada: {e}")
    finally:
        devices.pop(device_id, None)
        log_message("DEVICE", f"Dispositivo {device_id} desconectado. Total: {len(devices)}")

# -----------------------------
# Función para broadcast a todos los viewers
# -----------------------------
async def broadcast_to_viewers(message: dict):
    if not viewers:
        log_message("BROADCAST", "No hay viewers conectados")
        return
        
    disconnected = []
    success_count = 0
    
    for viewer_id, websocket in viewers.items():
        try:
            await websocket.send_text(json.dumps(message))
            success_count += 1
        except Exception as e:
            log_message("BROADCAST", f"Error enviando a {viewer_id}: {e}")
            disconnected.append(viewer_id)
    
    # Limpiar viewers desconectados
    for viewer_id in disconnected:
        viewers.pop(viewer_id, None)
    
    if success_count > 0:
        log_message("BROADCAST", f"✅ Enviado a {success_count} viewers")

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
        log_message("WEBRTC", f"Answer enviada a {sdp.device_id}")

    return {"status": "ok"}

@app.get("/offer/{device_id}")
async def get_answer(device_id: str):
    return {"sdp": answers.get(device_id)}

# -----------------------------
# Endpoints de estado y diagnóstico
# -----------------------------
@app.get("/status")
async def get_status():
    return {
        "devices_connected": list(devices.keys()),
        "viewers_connected": len(viewers),
        "total_connections": len(devices) + len(viewers),
        "server_time": datetime.now().isoformat()
    }

@app.get("/test_broadcast")
async def test_broadcast():
    """Endpoint para testear el broadcast manualmente"""
    test_message = {
        "type": "test_frame",
        "device_id": "test_server",
        "data": "test_data_12345",
        "timestamp": datetime.now().isoformat(),
        "frame_number": 999
    }
    
    await broadcast_to_viewers(test_message)
    return {
        "status": "test message sent", 
        "viewers_count": len(viewers),
        "message": test_message
    }

@app.get("/debug")
async def debug():
    """Endpoint de debug completo"""
    return {
        "devices": list(devices.keys()),
        "viewers_count": len(viewers),
        "viewer_ids": list(viewers.keys()),
        "server_time": datetime.now().isoformat()
    }

@app.get("/")
async def root():
    return {
        "message": "Servidor de video WebRTC funcionando",
        "endpoints": {
            "status": "/status",
            "debug": "/debug", 
            "test_broadcast": "/test_broadcast",
            "websocket_viewer": "/ws/viewer",
            "websocket_device": "/ws/{device_id}"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
