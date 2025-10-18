from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
from datetime import datetime
import aiohttp
from typing import Dict, Any
import logging
import hashlib
import hmac
import secrets

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
download_connections = {}
thumbnail_requests = {}

class ProxyRequest(BaseModel):
    method: str
    endpoint: str
    body: Dict[str, Any] = None
    headers: Dict[str, str] = None

# Clave secreta para firmar URLs (guarda en environment variables en Render)
URL_SECRET = "tu_clave_secreta_nexlens_2024"

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
                
            # Manejar respuestas de descarga
            if message_type == "file_chunk":
                await handle_file_chunk(message)
                
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
                
                # Enviar al dispositivo
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
# WebSocket para Descargas
# -----------------------------
@app.websocket("/ws/download/{device_id}")
async def download_websocket(websocket: WebSocket, device_id: str):
    """WebSocket dedicado para transferencia de archivos grandes"""
    await websocket.accept()
    
    download_id = f"download_{id(websocket)}"
    download_connections[download_id] = {
        "websocket": websocket,
        "device_id": device_id
    }
    
    logger.info(f"Download WS: {download_id} conectado para {device_id}")
    
    try:
        while True:
            # El cliente solicita un archivo
            data = await websocket.receive_text()
            request = json.loads(data)
            
            if request["type"] == "download_request":
                filename = request["filename"]
                chunk_size = request.get("chunk_size", 64 * 1024)  # 64KB por defecto
                
                # Reenviar solicitud al dispositivo via WebRTC
                if device_id in webrtc_connections:
                    download_request_id = secrets.token_urlsafe(16)
                    
                    # Enviar solicitud de descarga al dispositivo
                    await webrtc_connections[device_id].send_text(json.dumps({
                        "type": "file_download",
                        "filename": filename,
                        "download_id": download_request_id,
                        "client_download_id": download_id,
                        "chunk_size": chunk_size
                    }))
                    
                    logger.info(f"Download WS: Solicitud de descarga enviada para {filename}")
                    
                else:
                    await websocket.send_text(json.dumps({
                        "type": "download_error",
                        "error": "Dispositivo no conectado"
                    }))
                    
    except WebSocketDisconnect:
        logger.info(f"Download WS: {download_id} desconectado")
    except Exception as e:
        logger.error(f"Download WS Error {download_id}: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "download_error",
                "error": str(e)
            }))
        except:
            pass
    finally:
        download_connections.pop(download_id, None)

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
# Manejar chunks de archivos desde dispositivos
# -----------------------------
async def handle_file_chunk(chunk_data: dict):
    """Manejar chunk de archivo desde un dispositivo"""
    client_download_id = chunk_data.get("client_download_id")
    
    if client_download_id in download_connections:
        try:
            # Enviar chunk al cliente de descarga
            await download_connections[client_download_id]["websocket"].send_text(json.dumps({
                "type": "file_chunk",
                "chunk_index": chunk_data.get("chunk_index"),
                "chunk_data": chunk_data.get("chunk_data"),
                "total_chunks": chunk_data.get("total_chunks"),
                "filename": chunk_data.get("filename")
            }))
            
        except Exception as e:
            logger.error(f"Error enviando chunk de archivo: {e}")
    else:
        logger.warning(f"Download ID no encontrado: {client_download_id}")

# -----------------------------
# Proxy para Thumbnails
# -----------------------------
@app.get("/proxy-thumbnail/{device_id}")
async def proxy_thumbnail(device_id: str, path: str):
    """Proxy para thumbnails - Solución temporal"""
    if device_id not in webrtc_connections:
        raise HTTPException(status_code=404, detail="Dispositivo no conectado")
    
    # Crear ID único para esta solicitud
    thumbnail_id = f"thumb_{secrets.token_urlsafe(8)}"
    
    # Crear evento para esperar la respuesta
    response_event = asyncio.Event()
    thumbnail_response = {}
    
    # Handler temporal para la respuesta
    original_handlers = {}
    
    def create_response_handler(device_id, thumbnail_id, response_event, thumbnail_response):
        async def response_handler(message):
            try:
                data = json.loads(message)
                if (data.get('type') == 'proxy_response' and 
                    data.get('proxy_id') == thumbnail_id):
                    
                    thumbnail_response['status_code'] = data.get('status_code', 200)
                    thumbnail_response['content'] = data.get('content', '')
                    thumbnail_response['headers'] = data.get('headers', {})
                    response_event.set()
                    
            except Exception as e:
                logger.error(f"Error en thumbnail handler: {e}")
                response_event.set()
        
        return response_handler
    
    # Guardar handler original y configurar el nuevo
    original_handler = webrtc_connections[device_id]._on_message
    new_handler = create_response_handler(device_id, thumbnail_id, response_event, thumbnail_response)
    webrtc_connections[device_id]._on_message = new_handler
    
    try:
        # Enviar solicitud de thumbnail al dispositivo
        await webrtc_connections[device_id].send_text(json.dumps({
            "type": "proxy_request",
            "method": "GET", 
            "endpoint": path,
            "proxy_id": thumbnail_id,
            "target": device_id
        }))
        
        logger.info(f"Thumbnail request enviada: {path} para {device_id}")
        
        # Esperar respuesta con timeout
        try:
            await asyncio.wait_for(response_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout esperando thumbnail: {path}")
            raise HTTPException(status_code=504, detail="Timeout esperando thumbnail")
        
        # Verificar respuesta
        if thumbnail_response.get('status_code', 404) != 200:
            raise HTTPException(status_code=404, detail="Thumbnail no encontrado en dispositivo")
        
        content = thumbnail_response.get('content', '')
        headers = thumbnail_response.get('headers', {})
        
        # Determinar content-type
        content_type = headers.get('content-type', 'image/gif')
        if not content_type.startswith('image/'):
            content_type = 'image/gif'
        
        from fastapi.responses import Response
        return Response(
            content=content,
            media_type=content_type
        )
        
    except Exception as e:
        logger.error(f"Error en proxy thumbnail: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
    
    finally:
        # Restaurar handler original
        webrtc_connections[device_id]._on_message = original_handler

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
        "download_connections": len(download_connections),
        "total_connections": len(webrtc_connections) + len(proxy_connections) + len(download_connections),
        "server_time": datetime.now().isoformat()
    }

@app.get("/proxy/signed-url/{device_id}")
async def get_signed_url(device_id: str, filename: str, action: str = "download"):
    """Generar URL firmada para acceso directo P2P"""
    if device_id not in webrtc_connections:
        raise HTTPException(status_code=404, detail="Dispositivo no conectado")
    
    # Crear token firmado con expiración
    timestamp = str(int(datetime.now().timestamp()))
    token_data = f"{device_id}:{filename}:{action}:{timestamp}"
    signature = hmac.new(URL_SECRET.encode(), token_data.encode(), hashlib.sha256).hexdigest()
    
    return {
        "signed_url": f"/proxy/direct/{device_id}/{filename}",
        "token": f"{timestamp}:{signature}",
        "expires_in": 300  # 5 minutos
    }

@app.get("/")
async def root():
    return {
        "message": "Servidor WebRTC + WebSocket Proxy funcionando",
        "endpoints": {
            "webrtc_signaling": "/ws/webrtc/{client_id}",
            "websocket_proxy": "/ws/proxy/{device_id}",
            "websocket_download": "/ws/download/{device_id}",
            "status": "/status",
            "devices": "/devices",
            "thumbnail_proxy": "/proxy-thumbnail/{device_id}?path=/thumbnails/filename.gif",
            "signed_url": "/proxy/signed-url/{device_id}?filename=XXX&action=download"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
