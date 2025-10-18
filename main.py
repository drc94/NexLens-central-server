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
# Almacenamiento de conexiones y configuraciones
# -----------------------------
webrtc_connections = {}
device_configs: Dict[str, str] = {}  # device_id -> local_url

class ProxyRequest(BaseModel):
    method: str
    endpoint: str
    body: Dict[str, Any] = None
    headers: Dict[str, str] = None

class DeviceConfig(BaseModel):
    device_id: str
    local_base_url: str  # Ej: "http://localhost:5000"

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
                logger.info(f"WebRTC: {message_type} de {client_id} -> {target_id}")
                
    except WebSocketDisconnect:
        logger.info(f"WebRTC: {client_id} desconectado")
    except Exception as e:
        logger.error(f"WebRTC Error {client_id}: {e}")
    finally:
        webrtc_connections.pop(client_id, None)

# -----------------------------
# Proxy HTTP para Raspberry Pi
# -----------------------------
@app.api_route("/proxy/{device_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_request(device_id: str, path: str, request: Request):
    """Proxy que reenvía peticiones a la Raspberry Pi local"""
    
    # Verificar si el dispositivo está registrado
    if device_id not in device_configs:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    
    local_base_url = device_configs[device_id]
    target_url = f"{local_base_url}/{path}"
    
    # Obtener headers (excluir algunos headers de FastAPI)
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ['host', 'content-length', 'content-encoding']:
            headers[key] = value
    
    # Obtener body si existe
    body = None
    if request.method in ['POST', 'PUT', 'PATCH']:
        try:
            body = await request.json()
        except:
            body = await request.body()
    
    logger.info(f"Proxy: {request.method} {target_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                json=body if isinstance(body, dict) else None,
                data=body if not isinstance(body, dict) else None,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                # Leer respuesta
                response_content = await response.read()
                
                # Devolver respuesta
                return {
                    "status_code": response.status,
                    "content": response_content.decode('utf-8') if response_content else None,
                    "headers": dict(response.headers)
                }
                
    except aiohttp.ClientError as e:
        logger.error(f"Proxy Error: {e}")
        raise HTTPException(status_code=502, detail=f"Error conectando con el dispositivo: {e}")
    except asyncio.TimeoutError:
        logger.error(f"Proxy Timeout: {target_url}")
        raise HTTPException(status_code=504, detail="Timeout conectando con el dispositivo")

# -----------------------------
# Gestión de dispositivos
# -----------------------------
@app.post("/register-device")
async def register_device(config: DeviceConfig):
    """Registrar un dispositivo y su URL local"""
    device_configs[config.device_id] = config.local_base_url
    logger.info(f"Dispositivo registrado: {config.device_id} -> {config.local_base_url}")
    return {"status": "registered", "device_id": config.device_id}

@app.delete("/unregister-device/{device_id}")
async def unregister_device(device_id: str):
    """Eliminar registro de dispositivo"""
    if device_id in device_configs:
        device_configs.pop(device_id)
        logger.info(f"Dispositivo eliminado: {device_id}")
        return {"status": "unregistered"}
    else:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

@app.get("/devices")
async def list_devices():
    """Listar todos los dispositivos registrados"""
    return {"devices": device_configs}

# -----------------------------
# Proxy vía WebSocket (para operaciones en tiempo real)
# -----------------------------
@app.websocket("/ws/proxy/{device_id}")
async def proxy_websocket(websocket: WebSocket, device_id: str):
    """WebSocket para proxy de peticiones en tiempo real"""
    await websocket.accept()
    
    if device_id not in device_configs:
        await websocket.close(code=1008, reason="Dispositivo no registrado")
        return
    
    local_base_url = device_configs[device_id]
    
    try:
        while True:
            # Recibir petición del cliente
            data = await websocket.receive_text()
            request_data = json.loads(data)
            
            method = request_data.get("method", "GET")
            endpoint = request_data.get("endpoint", "")
            body = request_data.get("body")
            headers = request_data.get("headers", {})
            
            target_url = f"{local_base_url}/{endpoint.lstrip('/')}"
            
            logger.info(f"WebSocket Proxy: {method} {target_url}")
            
            # Ejecutar petición
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=target_url,
                    headers=headers,
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    response_content = await response.text()
                    
                    # Enviar respuesta al cliente
                    await websocket.send_text(json.dumps({
                        "status_code": response.status,
                        "content": response_content,
                        "headers": dict(response.headers)
                    }))
                    
    except WebSocketDisconnect:
        logger.info(f"WebSocket Proxy desconectado: {device_id}")
    except Exception as e:
        logger.error(f"WebSocket Proxy Error: {e}")
        await websocket.close(code=1011, reason=str(e))

# -----------------------------
# Endpoints de estado
# -----------------------------
@app.get("/status")
async def get_status():
    return {
        "webrtc_connections": list(webrtc_connections.keys()),
        "registered_devices": device_configs,
        "total_connections": len(webrtc_connections),
        "server_time": datetime.now().isoformat()
    }

@app.get("/")
async def root():
    return {
        "message": "Servidor Proxy + WebRTC funcionando",
        "endpoints": {
            "webrtc_signaling": "/ws/webrtc/{client_id}",
            "http_proxy": "/proxy/{device_id}/{path}",
            "websocket_proxy": "/ws/proxy/{device_id}",
            "device_management": "/register-device, /unregister-device, /devices",
            "status": "/status"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
