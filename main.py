from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# Permitir conexiones desde cualquier origen (para navegador local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Guardar la última conexión (muy simple)
pi_ws = None

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global pi_ws
    await ws.accept()

    if pi_ws is None:
        print("📷 Raspberry conectada")
        pi_ws = ws
        await ws.send_text('{"role":"pi"}')
        try:
            while True:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_text("pong")
        except:
            pi_ws = None
    else:
        print("🖥️ Navegador conectado")
        try:
            await ws.send_text('{"role":"browser"}')
            offer = await ws.receive_text()
            await pi_ws.send_text(offer)
            answer = await pi_ws.receive_text()
            await ws.send_text(answer)
        except:
            pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
