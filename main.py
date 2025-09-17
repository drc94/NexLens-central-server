from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Diccionario para almacenar dispositivos conectados {device_id: websocket}
devices = {}

@app.websocket("/ws/{device_id}")
async def device_ws(websocket: WebSocket, device_id: str):
    await websocket.accept()
    devices[device_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Recibido de {device_id}: {data}")
    except Exception as e:
        print(f"Conexión cerrada {device_id}: {e}")
    finally:
        del devices[device_id]

@app.get("/send/{device_id}/{message}")
async def send_to_device(device_id: str, message: str):
    if device_id in devices:
        await devices[device_id].send_text(message)
        return {"status": "ok"}
    return {"status": "device not connected"}
