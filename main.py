from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
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

# Almacenar conexiones
connections = {}

@app.websocket("/ws/webrtc/{client_id}")
async def webrtc_websocket(websocket: WebSocket, client_id: str):
    await websocket.accept()
    connections[client_id] = websocket
    print(f"✅ {client_id} conectado")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Reenviar a destino
            target_id = message.get("target")
            if target_id in connections:
                await connections[target_id].send_text(json.dumps({
                    **message,
                    "sender": client_id
                }))
                
    except Exception as e:
        print(f"❌ {client_id} desconectado: {e}")
    finally:
        connections.pop(client_id, None)

@app.get("/status")
async def status():
    return {
        "connections": list(connections.keys()),
        "total": len(connections)
    }

@app.get("/")
async def root():
    return {"message": "Servidor WebRTC/HLS Signaling"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
