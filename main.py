from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI()
latest_ws = None  # guardará la conexión del navegador

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.websocket("/")
async def ws_endpoint(ws: WebSocket):
    global latest_ws
    await ws.accept()
    if latest_ws is None:
        latest_ws = ws
    else:
        # intercambio simple entre Pi y navegador
        msg = await ws.receive_text()
        await latest_ws.send_text(msg)
        msg2 = await latest_ws.receive_text()
        await ws.send_text(msg2)
        latest_ws = None

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
