from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # puedes restringir luego a tus dominios reales
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Diccionario para almacenar dispositivos conectados {device_id: websocket}
devices: Dict[str, WebSocket] = {}

@app.websocket("/ws/{device_id}")
async def device_ws(websocket: WebSocket, device_id: str):
    await websocket.accept()
    devices[device_id] = websocket
    print(f"Dispositivo conectado: {device_id}")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Recibido de {device_id}: {data}")
    except Exception as e:
        print(f"Conexión cerrada {device_id}: {e}")
    finally:
        if device_id in devices:
            del devices[device_id]
            print(f"Dispositivo desconectado: {device_id}")

@app.get("/send/{device_id}/{message}")
async def send_to_device(device_id: str, message: str):
    websocket = devices.get(device_id)
    if websocket:
        await websocket.send_text(message)
        print(f"Enviado a {device_id}: {message}")
        return {"status": "ok"}
    return {"status": "device not connected"}
