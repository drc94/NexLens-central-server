from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento de conexiones
webrtc_connections = {}
proxy_connections = {}

@app.websocket("/ws/webrtc/{client_id}")
async def webrtc_websocket(websocket: WebSocket, client_id: str):
    await websocket.accept()
    webrtc_connections[client_id] = websocket
    logger.info(f"WebRTC Signaling: {client_id} conectado")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message_type = message.get("type")
            
            # Reenviar mensajes de señalización
            target_id = message.get("target")
            if target_id and target_id in webrtc_connections:
                await webrtc_connections[target_id].send_text(json.dumps({
                    **message,
                    "sender": client_id
                }))
                logger.debug(f"WebRTC: {message_type} de {client_id} a {target_id}")
                
    except WebSocketDisconnect:
        logger.info(f"WebRTC: {client_id} desconectado")
    finally:
        webrtc_connections.pop(client_id, None)

@app.websocket("/ws/proxy/{device_id}")
async def proxy_websocket(websocket: WebSocket, device_id: str):
    await websocket.accept()
    
    proxy_id = f"proxy_{id(websocket)}"
    proxy_connections[proxy_id] = {"websocket": websocket, "device_id": device_id}
    logger.info(f"Proxy: {proxy_id} para {device_id}")
    
    try:
        while True:
            data = await websocket.receive_text()
            request_data = json.loads(data)
            
            method = request_data.get("method", "GET")
            endpoint = request_data.get("endpoint", "")
            body = request_data.get("body")
            headers = request_data.get("headers", {})
            
            logger.info(f"Proxy: {method} {endpoint}")
            
            if device_id in webrtc_connections:
                proxy_message = {
                    "type": "proxy_request",
                    "method": method,
                    "endpoint": endpoint,
                    "body": body,
                    "headers": headers,
                    "proxy_id": proxy_id,
                    "target": device_id
                }
                
                await webrtc_connections[device_id].send_text(json.dumps(proxy_message))
                
            else:
                await websocket.send_text(json.dumps({
                    "status_code": 503,
                    "content": "Dispositivo no conectado"
                }))
                
    except WebSocketDisconnect:
        logger.info(f"Proxy: {proxy_id} desconectado")
    finally:
        proxy_connections.pop(proxy_id, None)

async def handle_proxy_response(response_data: dict):
    proxy_id = response_data.get("proxy_id")
    if proxy_id in proxy_connections:
        try:
            await proxy_connections[proxy_id]["websocket"].send_text(json.dumps({
                "status_code": response_data.get("status_code", 200),
                "content": response_data.get("content", ""),
                "headers": response_data.get("headers", {})
            }))
        except Exception as e:
            logger.error(f"Error proxy response: {e}")

@app.get("/proxy-thumbnail/{device_id}")
async def proxy_thumbnail(device_id: str, path: str):
    if device_id not in webrtc_connections:
        raise HTTPException(status_code=404, detail="Dispositivo no conectado")
    
    try:
        import websockets
        from fastapi.responses import Response
        
        async with websockets.connect(f"wss://nexlens-central-server.onrender.com/ws/proxy/{device_id}") as ws:
            await ws.send(json.dumps({
                "method": "GET",
                "endpoint": path,
                "headers": {"Accept": "image/*"}
            }))
            
            response = await ws.recv()
            response_data = json.loads(response)
            
            if response_data.get("status_code") != 200:
                raise HTTPException(status_code=404)
            
            content_type = response_data.get("headers", {}).get("content-type", "image/gif")
            return Response(content=response_data.get("content", ""), media_type=content_type)
            
    except Exception as e:
        logger.error(f"Error thumbnail: {e}")
        placeholder_svg = '<svg width="200" height="120"><rect width="200" height="120" fill="#F3F4F6"/><text x="100" y="60" font-family="Arial" font-size="14" fill="#999" text-anchor="middle">Thumbnail</text></svg>'
        return Response(content=placeholder_svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {"message": "WebRTC Signaling Server"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
