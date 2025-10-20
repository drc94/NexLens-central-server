from flask import Flask, request
from flask_socketio import SocketIO
import logging
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'webrtc_secret_key_2024')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Almacén para sesiones P2P
sessions = {}

@app.route('/')
def index():
    return {
        "status": "active",
        "service": "WebRTC Signaling Server",
        "instructions": "Usa el cliente HTML para conectarte"
    }

@app.route('/health')
def health():
    return {"status": "healthy", "sessions_active": len(sessions)}

@socketio.on('connect')
def handle_connect():
    print(f'🔌 Cliente conectado: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'🔌 Cliente desconectado: {request.sid}')
    # Limpiar sesiones del cliente desconectado
    for session_id, data in list(sessions.items()):
        if data.get('client_id') == request.sid:
            del sessions[session_id]
            print(f"🗑️ Sesión {session_id} eliminada")

@socketio.on('offer')
def handle_offer(data):
    """Recibir offer del Raspberry Pi"""
    session_id = data.get('session_id')
    if session_id:
        sessions[session_id] = {
            'offer': data['offer'],
            'client_id': request.sid
        }
        print(f"📥 Offer almacenado - Sesión: {session_id}")

@socketio.on('get_offer')
def handle_get_offer(data):
    """Cliente web solicita offer"""
    session_id = data.get('session_id')
    if session_id in sessions:
        socketio.emit('offer', {
            'offer': sessions[session_id]['offer'],
            'session_id': session_id
        }, room=request.sid)
        print(f"📤 Offer enviado al cliente - Sesión: {session_id}")
    else:
        socketio.emit('error', {
            'message': 'No hay stream disponible. Asegúrate de que la Raspberry Pi esté conectada.'
        }, room=request.sid)
        print(f"❌ Cliente solicitó sesión inexistente: {session_id}")

@socketio.on('answer')
def handle_answer(data):
    """Recibir answer del cliente web"""
    session_id = data.get('session_id')
    if session_id in sessions:
        # Enviar answer al Raspberry Pi
        target_client = sessions[session_id]['client_id']
        socketio.emit('answer', {
            'answer': data['answer'],
            'session_id': session_id
        }, room=target_client)
        print(f"📨 Answer enviado a Raspberry Pi - Sesión: {session_id}")

@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    """Retransmitir ICE candidates"""
    session_id = data.get('session_id')
    if session_id in sessions:
        # Enviar al otro cliente
        sender_client = request.sid
        target_client = sessions[session_id]['client_id']
        
        if sender_client != target_client:
            # Enviar al Raspberry Pi
            socketio.emit('ice_candidate', {
                'candidate': data['candidate'],
                'session_id': session_id
            }, room=target_client)
        else:
            # Enviar al cliente web
            socketio.emit('ice_candidate', {
                'candidate': data['candidate'],
                'session_id': session_id
            }, room=sender_client)
        print(f"❄️ ICE candidate retransmitido - Sesión: {session_id}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    print(f"🚀 Starting WebRTC Signaling Server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=debug, log_output=True)
