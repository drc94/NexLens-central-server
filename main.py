from flask import Flask, render_template
from flask_socketio import SocketIO
import logging
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tu_secret_key_aqui'
socketio = SocketIO(app, cors_allowed_origins="*")

# Almacén simple para sesiones P2P
sessions = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Cliente desconectado: {request.sid}')
    # Limpiar sesiones cuando un cliente se desconecta
    for session_id, data in sessions.items():
        if data['client_id'] == request.sid:
            del sessions[session_id]
            break

@socketio.on('offer')
def handle_offer(data):
    """Recibir offer del Raspberry Pi y almacenarlo"""
    session_id = data.get('session_id')
    sessions[session_id] = {
        'offer': data['offer'],
        'client_id': request.sid,
        'pi_connected': True
    }
    print(f"Offer recibido para sesión: {session_id}")

@socketio.on('get_offer')
def handle_get_offer(data):
    """Enviar offer al cliente web cuando lo solicite"""
    session_id = data.get('session_id')
    if session_id in sessions:
        socketio.emit('offer', {
            'offer': sessions[session_id]['offer'],
            'session_id': session_id
        }, room=request.sid)
    else:
        socketio.emit('error', {'message': 'Sesión no encontrada'}, room=request.sid)

@socketio.on('answer')
def handle_answer(data):
    """Recibir answer del cliente web y enviarlo al Raspberry Pi"""
    session_id = data.get('session_id')
    if session_id in sessions:
        # Enviar answer al Raspberry Pi
        socketio.emit('answer', {
            'answer': data['answer'],
            'session_id': session_id
        }, room=sessions[session_id]['client_id'])

@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    """Retransmitir ICE candidates entre clientes"""
    session_id = data.get('session_id')
    if session_id in sessions:
        # Enviar al otro cliente
        target_client = sessions[session_id]['client_id'] if request.sid != sessions[session_id]['client_id'] else None
        if target_client:
            socketio.emit('ice_candidate', {
                'candidate': data['candidate'],
                'session_id': session_id
            }, room=target_client)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
