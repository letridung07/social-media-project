from flask_socketio import join_room, leave_room, emit
from flask_login import current_user
from flask import request
from app import socketio, db # Assuming socketio and db are initialized in app/__init__.py
from app.models import Conversation, ChatMessage, User, Notification # Import Notification
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

@socketio.on('send_chat_message') # Original event name
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

    # Create notifications for other participants
    for participant in conversation.participants:
        if participant.id != current_user.id:
            notification = Notification(
                recipient_id=participant.id,
                actor_id=current_user.id,
                type='new_chat_message',
                related_post_id=None,  # Explicitly None for chat messages
                related_conversation_id=conversation.id # Link to the conversation
            )
            db.session.add(notification)
            # Emit real-time notification to the specific participant
            socketio.emit('new_notification', {
                'message': f'{current_user.username} sent you a new chat message.',
                'type': 'new_chat_message',
                'actor_username': current_user.username,
                'sender_id': current_user.id,
                'conversation_id': conversation.id
            }, room=str(participant.id))
    db.session.commit() # Commit notifications

    emit_data = {
        'message_id': message.id, # Added message_id
        'conversation_id': conversation.id,
        'sender_id': current_user.id,
        'sender_username': current_user.username,
        'body': message.body,
        'timestamp': message.timestamp.isoformat() + "Z" # Explicitly add Z for UTC
    }
    socketio.emit('new_chat_message', emit_data, room=f'conv_{conversation.id}') # Use socketio.emit for broadcast to room
    print(f"Message from {current_user.username} sent to room conv_{conversation.id}") # Original print

@socketio.on('typing_started')
def handle_typing_started(data):
    conversation_id = data.get('conversation_id')
    if current_user.is_authenticated and conversation_id:
        event_data = {
            'username': current_user.username,
            'user_id': current_user.id,
            'conversation_id': conversation_id
        }
        # It's important that the client-side joins/leaves this 'conv_{conversation_id}' room correctly.
        # skip_sid is used so the user typing doesn't see their own "is typing" notification.
        emit('user_typing', event_data, room=f'conv_{conversation_id}', skip_sid=request.sid)
        print(f"User {current_user.username} started typing in conv {conversation_id}")

@socketio.on('typing_stopped')
def handle_typing_stopped(data):
    conversation_id = data.get('conversation_id')
    if current_user.is_authenticated and conversation_id:
        event_data = {
            'username': current_user.username,
            'user_id': current_user.id,
            'conversation_id': conversation_id
        }
        emit('user_stopped_typing', event_data, room=f'conv_{conversation_id}', skip_sid=request.sid)
        print(f"User {current_user.username} stopped typing in conv {conversation_id}")

@socketio.on('mark_messages_as_read')
def handle_mark_messages_as_read(data):
    message_ids = data.get('message_ids')
    conversation_id = data.get('conversation_id')

    if not current_user.is_authenticated:
        print(f"User is not authenticated. Cannot mark messages as read.")
        # Optionally emit an error back to the sender
        # emit('mark_read_error', {'message': 'Authentication required.'}, room=request.sid)
        return

    if not message_ids or not isinstance(message_ids, list) or not conversation_id:
        print(f"Invalid data for marking messages as read: message_ids={message_ids}, conv_id={conversation_id}")
        # Optionally emit an error back to the sender
        # emit('mark_read_error', {'message': 'Missing message_ids or conversation_id.'}, room=request.sid)
        return

    updated_message_ids = []
    try:
        for msg_id in message_ids:
            if not isinstance(msg_id, int): # Basic type check
                print(f"Invalid message ID type: {msg_id}")
                continue

            message = ChatMessage.query.get(msg_id)
            if message:
                # Ensure the message belongs to the specified conversation for added security,
                # though primarily we check ownership and current read status.
                # This check is more complex if message.conversation_id isn't directly comparable
                # or if conversation_id from client is not just the ID.
                # For now, focusing on sender and current read status.
                if str(message.conversation_id) == str(conversation_id) and \
                   message.sender_id != current_user.id and \
                   not message.is_read:
                    message.is_read = True
                    updated_message_ids.append(msg_id)
            else:
                print(f"Message with id {msg_id} not found.")

        if updated_message_ids:
            db.session.commit()
            payload = {
                'message_ids': updated_message_ids,
                'reader_user_id': current_user.id,
                'conversation_id': conversation_id # Use the validated conversation_id from data
            }
            room_name = f'conv_{conversation_id}'
            emit('messages_read_update', payload, room=room_name)
            print(f"User {current_user.username} marked messages {updated_message_ids} as read in conv {conversation_id}")
        else:
            print(f"No messages updated for user {current_user.username} in conv {conversation_id}. Might be own messages or already read.")

    except Exception as e:
        db.session.rollback()
        print(f"Error in handle_mark_messages_as_read: {e}")
        # Optionally emit a generic error back to the sender
        # emit('mark_read_error', {'message': 'Server error processing request.'}, room=request.sid)
