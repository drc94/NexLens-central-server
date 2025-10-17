from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Diccionario de websockets conectados
# -----------------------------
devices = {}

class Command(BaseModel):
    method: str
    endpoint: str
    body: dict | None = None

@app.websocket("/ws/{device_id}")
async def device_ws(websocket: WebSocket, device_id: str):
    await websocket.accept()
    devices[device_id] = websocket
    print(f"{device_id} conectado.")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Recibido de {device_id}: {data}")
    except Exception as e:
        print(f"Conexión cerrada {device_id}: {e}")
    finally:
        devices.pop(device_id, None)

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
