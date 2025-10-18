from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
from datetime import datetime
import aiohttp
from typing import Dict, Any
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

# -----------------------------
# Almacenamiento de conexiones
# -----------------------------
webrtc_connections = {}
proxy_connections = {}

class ProxyRequest(BaseModel):
    method: str
    endpoint: str
    body: Dict[str, Any] = None
    headers: Dict[str, str] = None

# -----------------------------
# WebRTC Signaling
# -----------------------------
@app.websocket("/ws/webrtc/{client_id}")
async def webrtc_websocket(websocket: WebSocket, client_id: str):
    await websocket.accept()
    webrtc_connections[client_id] = websocket
    logger.info(f"WebRTC: {client_id} conectado. Total: {len(webrtc_connections)}")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message_type = message.get("type")
            
            # Reenviar mensajes a su destino
            target_id = message.get("target")
            if target_id and target_id in webrtc_connections:
                await webrtc_connections[target_id].send_text(json.dumps({
                    **message,
                    "sender": client_id
                }))
                
            # Manejar respuestas proxy desde dispositivos
            if message_type == "proxy_response":
                await handle_proxy_response(message)
                
    except WebSocketDisconnect:
        logger.info(f"WebRTC: {client_id} desconectado")
    except Exception as e:
        logger.error(f"WebRTC Error {client_id}: {e}")
    finally:
        webrtc_connections.pop(client_id, None)

# -----------------------------
# WebSocket Proxy para Peticiones HTTP
# -----------------------------
@app.websocket("/ws/proxy/{device_id}")
async def proxy_websocket(websocket: WebSocket, device_id: str):
    """WebSocket que reenvía peticiones HTTP a dispositivos específicos"""
    await websocket.accept()
    
    # Guardar conexión proxy
    proxy_id = f"proxy_{id(websocket)}"
    proxy_connections[proxy_id] = {
        "websocket": websocket,
        "device_id": device_id
    }
    
    logger.info(f"Proxy WS: {proxy_id} conectado para dispositivo {device_id}")
    
    try:
        while True:
            # Recibir petición del cliente
            data = await websocket.receive_text()
            request_data = json.loads(data)
            
            method = request_data.get("method", "GET")
            endpoint = request_data.get("endpoint", "")
            body = request_data.get("body")
            headers = request_data.get("headers", {})
            
            logger.info(f"Proxy WS: {method} {endpoint} para {device_id}")
            
            # Reenviar petición al dispositivo via WebRTC
            if device_id in webrtc_connections:
                # Crear mensaje de petición proxy
                proxy_message = {
                    "type": "proxy_request",
                    "method": method,
                    "endpoint": endpoint,
                    "body": body,
                    "headers": headers,
                    "proxy_id": proxy_id,
                    "target": device_id
                }
                
                # Enviar al dispositivo - USAR send() en lugar de send_text()
                await webrtc_connections[device_id].send_text(json.dumps(proxy_message))
                logger.info(f"Proxy WS: Petición enviada a {device_id}")
                
            else:
                # Dispositivo no conectado
                error_response = {
                    "status_code": 503,
                    "content": "Dispositivo no conectado",
                    "headers": {}
                }
                await websocket.send_text(json.dumps(error_response))
                logger.warning(f"Proxy WS: Dispositivo {device_id} no conectado")
                
    except WebSocketDisconnect:
        logger.info(f"Proxy WS: {proxy_id} desconectado")
    except Exception as e:
        logger.error(f"Proxy WS Error {proxy_id}: {e}")
        try:
            error_response = {
                "status_code": 500,
                "content": f"Error interno: {str(e)}",
                "headers": {}
            }
            await websocket.send_text(json.dumps(error_response))
        except:
            pass
    finally:
        proxy_connections.pop(proxy_id, None)

# -----------------------------
# Manejar respuestas proxy desde dispositivos
# -----------------------------
async def handle_proxy_response(response_data: dict):
    """Manejar respuesta de petición proxy desde un dispositivo"""
    proxy_id = response_data.get("proxy_id")
    
    if proxy_id in proxy_connections:
        try:
            # Enviar respuesta al cliente proxy
            await proxy_connections[proxy_id]["websocket"].send_text(json.dumps({
                "status_code": response_data.get("status_code", 200),
                "content": response_data.get("content", ""),
                "headers": response_data.get("headers", {})
            }))
            logger.info(f"Proxy Response: {response_data.get('status_code')} para {proxy_id}")
            
        except Exception as e:
            logger.error(f"Error enviando respuesta proxy: {e}")
    else:
        logger.warning(f"Proxy ID no encontrado: {proxy_id}")

# -----------------------------
# Endpoints de gestión
# -----------------------------
@app.get("/devices")
async def list_devices():
    """Listar dispositivos conectados"""
    connected_devices = list(webrtc_connections.keys())
    return {
        "connected_devices": connected_devices,
        "total_connected": len(connected_devices)
    }

@app.get("/status")
async def get_status():
    return {
        "webrtc_connections": list(webrtc_connections.keys()),
        "proxy_connections": len(proxy_connections),
        "total_connections": len(webrtc_connections) + len(proxy_connections),
        "server_time": datetime.now().isoformat()
    }

@app.get("/")
async def root():
    return {
        "message": "Servidor WebRTC + WebSocket Proxy funcionando",
        "endpoints": {
            "webrtc_signaling": "/ws/webrtc/{client_id}",
            "websocket_proxy": "/ws/proxy/{device_id}", 
            "status": "/status",
            "devices": "/devices"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
