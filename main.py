from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
from datetime import datetime
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Diccionarios para WebRTC signaling
# -----------------------------
webrtc_connections = {}

class WebRTCMessage(BaseModel):
    type: str  # offer, answer, candidate, ice_candidate
    sdp: str = None
    candidate: dict = None
    target: str = None
    sender: str = None

def log_message(source: str, message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {source}: {message}")

# -----------------------------
# WebSocket para WebRTC signaling
# -----------------------------
@app.websocket("/ws/webrtc/{client_id}")
async def webrtc_websocket(websocket: WebSocket, client_id: str):
    await websocket.accept()
    webrtc_connections[client_id] = websocket
    log_message("WEBRTC", f"Cliente {client_id} conectado. Total: {len(webrtc_connections)}")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message_type = message.get("type")
            
            log_message(f"WEBRTC_{client_id}", f"Mensaje: {message_type}")
            
            # Reenviar mensajes a su destino
            target_id = message.get("target")
            if target_id and target_id in webrtc_connections:
                await webrtc_connections[target_id].send_text(json.dumps({
                    **message,
                    "sender": client_id
                }))
                log_message("WEBRTC", f"✅ Mensaje {message_type} de {client_id} -> {target_id}")
            else:
                log_message("WEBRTC", f"❌ Target {target_id} no encontrado")
                
    except WebSocketDisconnect:
        log_message(f"WEBRTC_{client_id}", "Desconectado")
    except Exception as e:
        log_message(f"WEBRTC_{client_id}", f"Error: {e}")
    finally:
        webrtc_connections.pop(client_id, None)
        log_message("WEBRTC", f"Cliente {client_id} desconectado. Total: {len(webrtc_connections)}")

# -----------------------------
# Endpoints de estado
# -----------------------------
@app.get("/status")
async def get_status():
    return {
        "webrtc_connections": list(webrtc_connections.keys()),
        "total_clients": len(webrtc_connections),
        "server_time": datetime.now().isoformat()
    }

@app.get("/")
async def root():
    return {
        "message": "Servidor WebRTC Signaling funcionando",
        "endpoints": {
            "webrtc_signaling": "/ws/webrtc/{client_id}",
            "status": "/status"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
