from flask_socketio import join_room, leave_room, emit
from flask_login import current_user
from flask import request
from app import socketio, db # Assuming socketio and db are initialized in app/__init__.py
from app.models import Conversation, ChatMessage, User
from datetime import datetime, timezone

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(str(current_user.id))
        print(f"User {current_user.username} connected and joined room {current_user.id}")

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(str(current_user.id))
        print(f"User {current_user.username} disconnected and left room {current_user.id}")

@socketio.on('join_notification_room') # For tests to explicitly join user's own notification room
def handle_join_notification_room():
    if current_user.is_authenticated:
        join_room(str(current_user.id))
        print(f"User {current_user.username} MANUALLY joined notification room {str(current_user.id)}")
        # emit('joined_notification_room_ack', {'room': str(current_user.id)}, room=request.sid) # Optional ack
    else:
        print(f"User {current_user.username} failed to MANUALLY join notification room: not authenticated.")

@socketio.on('test_broadcast_to_room')
def handle_test_broadcast(data):
    room_to_broadcast = data.get('room')
    if room_to_broadcast and current_user.is_authenticated:
        # For this test, assume current_user should be in this room str(current_user.id)
        # Or verify if user is in room: if room_to_broadcast in rooms():
        test_message = {'message': f'Test broadcast received in room {room_to_broadcast} for {current_user.username}'}
        print(f"Broadcasting test_echo_to_room: {test_message} to room {room_to_broadcast}")
        socketio.emit('test_echo_to_room', test_message, room=room_to_broadcast)
    else:
        print(f"Could not execute test_broadcast_to_room due to missing room: {room_to_broadcast} or auth: {current_user.is_authenticated}")


@socketio.on('join_chat_room')
def handle_join_chat_room(data):
    room_id = data.get('conversation_id')
    if room_id and current_user.is_authenticated:
        conv = Conversation.query.get(int(room_id)) # Ensure room_id is int
        if conv and current_user in conv.participants:
            join_room(f'conv_{room_id}')
            print(f"User {current_user.username} joined chat room conv_{room_id}")
        else:
            print(f"User {current_user.username} failed to join room conv_{room_id}. Not participant or conv not found.")

@socketio.on('leave_chat_room')
def handle_leave_chat_room(data):
    room_id = data.get('conversation_id')
    if room_id and current_user.is_authenticated:
        leave_room(f'conv_{room_id}')
        print(f"User {current_user.username} left chat room conv_{room_id}")

@socketio.on('send_chat_message')
def handle_send_chat_message(data):
    conversation_id = data.get('conversation_id')
    message_body = data.get('body')

    if not str(conversation_id).isdigit() or not message_body or not current_user.is_authenticated:
        emit('chat_error', {'message': 'Invalid data or authentication issue.'}, room=request.sid)
        return

    conversation = Conversation.query.get(int(conversation_id))
    if not conversation or current_user not in conversation.participants:
        emit('chat_error', {'message': 'Conversation not found or you are not a participant.'}, room=request.sid)
        return

    message = ChatMessage(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        body=message_body,
        timestamp=datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow()
    )
    db.session.add(message)

    conversation.last_updated = message.timestamp
    db.session.commit()

    emit_data = {
        'conversation_id': conversation.id,
        'sender_id': current_user.id,
        'sender_username': current_user.username,
        'body': message.body,
        'timestamp': message.timestamp.isoformat() + "Z" # Explicitly add Z for UTC
    }
    socketio.emit('new_chat_message', emit_data, room=f'conv_{conversation.id}') # Use socketio.emit for broadcast to room
    print(f"Message from {current_user.username} sent to room conv_{conversation.id}")
