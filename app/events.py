from flask_socketio import join_room, leave_room, emit
from flask_login import current_user
from flask import request, current_app # Import current_app
from app import socketio, db # Assuming socketio and db are initialized in app/__init__.py
from app.models import Conversation, ChatMessage, User, Notification, MessageReadStatus, LiveStream # Import LiveStream
from datetime import datetime, timezone

poll_room_viewers = {}

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
        'timestamp': message.timestamp.isoformat() + "Z", # Explicitly add Z for UTC
        'read_at': message.read_at # Should be None initially
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
    conversation_id = data.get('conversation_id')
    message_ids = data.get('message_ids')

    if not current_user.is_authenticated:
        emit('mark_read_error', {'message': 'Authentication required.'}, room=request.sid)
        print("User not authenticated for mark_messages_as_read")
        return

    if not conversation_id or not message_ids or not isinstance(message_ids, list):
        emit('mark_read_error', {'message': 'Invalid data: conversation_id and message_ids (list) are required.'}, room=request.sid)
        print(f"Invalid data for mark_messages_as_read: conv_id={conversation_id}, message_ids={message_ids}")
        return

    processed_message_ids_for_notification = []

    for message_id in message_ids:
        if not isinstance(message_id, int):
            print(f"Skipping invalid message_id type: {message_id}")
            continue

        # Check if MessageReadStatus already exists
        existing_status = MessageReadStatus.query.filter_by(
            user_id=current_user.id,
            message_id=message_id
        ).first()

        if existing_status:
            print(f"Message {message_id} already marked as read by user {current_user.id}")
            continue

        message = ChatMessage.query.get(message_id)
        if not message:
            print(f"ChatMessage with id {message_id} not found.")
            continue

        # Ensure message is part of the given conversation
        if str(message.conversation_id) != str(conversation_id):
            print(f"Message {message_id} does not belong to conversation {conversation_id}.")
            continue

        # Create and save new MessageReadStatus
        new_status = MessageReadStatus(
            message_id=message_id,
            user_id=current_user.id
            # read_at is set by default
        )
        db.session.add(new_status)
        print(f"Created MessageReadStatus for message {message_id}, user {current_user.id}")

        # If it's an incoming message being marked as read by the current user
        if message.sender_id != current_user.id:
            processed_message_ids_for_notification.append(message_id)
            # Update ChatMessage.read_at if it's the first read for this message by anyone (or recipient in 1-1)
            if message.read_at is None:
                message.read_at = new_status.read_at # Use the same timestamp as MessageReadStatus
                print(f"Updated ChatMessage {message_id} read_at to {message.read_at}")

    if not processed_message_ids_for_notification and not db.session.new: # Check if any new MessageReadStatus were added
        # No new read statuses were created, and no messages qualified for notification.
        # This can happen if all messages were already read or were sent by the current user.
        print(f"No messages processed or needed notification for user {current_user.id} in conversation {conversation_id}.")
        # We still need to commit if message.read_at was updated for messages not in processed_message_ids_for_notification
        # (e.g. if a message was already marked read by this user via MessageReadStatus, but ChatMessage.read_at was still null)
        # However, the current logic updates message.read_at only for *newly* created MessageReadStatus for incoming messages.
        # So, if processed_message_ids_for_notification is empty, it means no *incoming* messages were newly marked read.
        # If db.session.new is also empty, it means no MessageReadStatus objects were created at all (e.g. all messages already read by this user).
        # If db.session.dirty might contain message.read_at changes, we should commit.
        # For simplicity here, we commit if anything changed (new MRS or dirty CM).
        if db.session.new or db.session.dirty:
            db.session.commit()
        return


    db.session.commit()
    print(f"Committed read statuses for user {current_user.id}, conversation {conversation_id}")

    # Emit messages_read_update if there were any incoming messages marked as read
    if processed_message_ids_for_notification:
        update_payload = {
            'conversation_id': conversation_id,
            'message_ids': processed_message_ids_for_notification,
            'reader_user_id': current_user.id,
            # 'read_at': # We could send the specific read_at time, but client might not need it for this event.
                         # The ChatMessage.read_at will be updated and can be fetched if needed.
                         # MessageReadStatus.read_at is also available.
        }

        # Emit to the conversation room (for all participants, including other devices of the current user)
        conversation_room = f'conv_{conversation_id}'
        socketio.emit('messages_read_update', update_payload, room=conversation_room)
        print(f"Emitted messages_read_update to {conversation_room} for messages {processed_message_ids_for_notification}")

        # Emit to the original sender's room if they are online
        # This requires finding the sender for each message, but since we only notify for messages
        # where sender_id != current_user.id, we need to get those senders.
        # For simplicity, if multiple messages from different senders are marked read in one go,
        # this will emit one event per sender. A more optimized way might be to group them.
        # However, the current payload is a list of message_ids, so it's okay to send it to each sender.

        # Find unique sender IDs for the messages that were processed
        sender_ids_to_notify = set()
        for msg_id in processed_message_ids_for_notification:
            msg = ChatMessage.query.get(msg_id) # Fetch again, or pass message objects around
            if msg and msg.sender_id != current_user.id:
                sender_ids_to_notify.add(msg.sender_id)

        for sender_id in sender_ids_to_notify:
            sender_room = str(sender_id)
            # Avoid sending to self if somehow sender_id is current_user.id (should not happen with current logic)
            if sender_room != str(current_user.id):
                 socketio.emit('messages_read_update', update_payload, room=sender_room)
                 print(f"Emitted messages_read_update to sender {sender_room} for messages {processed_message_ids_for_notification}")

# -------------------- WebRTC Signaling Events for Live Streaming --------------------

@socketio.on('join_stream_room')
def handle_join_stream_room(data):
    stream_username = data.get('stream_username')
    if not stream_username:
        emit('stream_error', {'message': 'stream_username missing'}, room=request.sid)
        return

    stream_user = User.query.filter_by(username=stream_username).first()
    if not stream_user:
        emit('stream_error', {'message': f'User {stream_username} not found.'}, room=request.sid)
        return

    stream_room = f"stream_{stream_username}"
    join_room(stream_room)
    print(f"User SID {request.sid} (User: {current_user.username if current_user.is_authenticated else 'Anonymous'}) joined room {stream_room}")
    emit('joined_stream_room_ack', {'room': stream_room, 'message': f'Successfully joined stream room for {stream_username}.'}, room=request.sid)

    # Notify broadcaster that a viewer has joined, if broadcaster is not the one joining
    if current_user.is_authenticated and current_user.username != stream_username:
        # For SFU, broadcaster needs to know about the new viewer to potentially initiate signaling from server-side if needed,
        # or just for awareness.
        if stream_user: # stream_user was fetched earlier in the original event
            socketio.emit('viewer_joined_sfu', {
                'viewer_sid': request.sid,
                'viewer_username': current_user.username,
                'stream_username': stream_username
            }, room=str(stream_user.id)) # Send to broadcaster's personal room (user.id)
            print(f"Notified broadcaster {stream_username} (SFU) that viewer {current_user.username} joined.")


@socketio.on('leave_stream_room')
def handle_leave_stream_room(data):
    stream_username = data.get('stream_username')
    if not stream_username:
        # Log error, but may not need to emit back if client is disconnecting
        print(f"Error: stream_username missing in leave_stream_room from SID {request.sid}")
        return

    stream_room = f"stream_{stream_username}"
    leave_room(stream_room)
    print(f"User SID {request.sid} (User: {current_user.username if current_user.is_authenticated else 'Anonymous'}) left room {stream_room}")
    emit('left_stream_room_ack', {'room': stream_room, 'message': f'Successfully left stream room for {stream_username}.'}, room=request.sid)

    # Notify broadcaster that a viewer has left
    if current_user.is_authenticated: # Ensure current_user is valid before accessing username
        stream_user = User.query.filter_by(username=stream_username).first()
        if stream_user and current_user.username != stream_username:
            # For SFU, notify broadcaster about viewer departure.
            socketio.emit('viewer_left_sfu', {
                'viewer_sid': request.sid,
                'viewer_username': current_user.username,
                'stream_username': stream_username
            }, room=str(stream_user.id)) # Send to broadcaster's personal room
            print(f"Notified broadcaster {stream_username} (SFU) that viewer {current_user.username} left.")

@socketio.on('sfu_relay_message')
def sfu_relay_message(data):
    """Relays SFU messages (offer, answer, candidate, etc.) between clients."""
    if not current_user.is_authenticated:
        emit('stream_error', {'message': 'Authentication required to relay SFU message.'}, room=request.sid)
        return

    message_type = data.get('type')
    payload = data.get('payload')
    stream_username = data.get('stream_username') # Context for the stream
    target_sid = data.get('target_sid') # Specific client SID to send to
    recipient_username = data.get('recipient_username') # Specific username to send to if SID unknown

    from_username = current_user.username
    from_sid = request.sid

    if not all([message_type, payload, stream_username]):
        emit('stream_error', {'message': 'Missing type, payload, or stream_username for SFU relay.'}, room=request.sid)
        return

    event_data = {
        'type': message_type,
        'payload': payload,
        'from_sid': from_sid,
        'from_username': from_username,
        'stream_username': stream_username
    }

    if target_sid:
        socketio.emit('sfu_message_direct', event_data, room=target_sid)
        print(f"SFU Relay: {from_username} (SID: {from_sid}) sent '{message_type}' to SID {target_sid} for stream {stream_username}")
    elif recipient_username:
        recipient_user = User.query.filter_by(username=recipient_username).first()
        if recipient_user:
            socketio.emit('sfu_message_user', event_data, room=str(recipient_user.id))
            print(f"SFU Relay: {from_username} (SID: {from_sid}) sent '{message_type}' to user {recipient_username} (Room: {recipient_user.id}) for stream {stream_username}")
        else:
            emit('stream_error', {'message': f'Recipient user {recipient_username} not found.'}, room=request.sid)
            print(f"SFU Relay: Recipient user {recipient_username} not found for message from {from_username}")
    else:
        # Fallback: broadcast to stream room (less ideal for targeted Janus messages, but might be used for general announcements or ICE candidates)
        stream_room = f"stream_{stream_username}"
        socketio.emit('sfu_message_room', event_data, room=stream_room, skip_sid=request.sid)
        print(f"SFU Relay: {from_username} (SID: {from_sid}) sent '{message_type}' to room {stream_room} for stream {stream_username}")

# @socketio.on('webrtc_offer')
# def handle_webrtc_offer(data):
#     """Broadcaster sends their SDP offer to be relayed to viewers."""
#     if not current_user.is_authenticated:
#         emit('stream_error', {'message': 'Authentication required to send offer.'}, room=request.sid)
#         return
#
#     offer_sdp = data.get('offer_sdp')
#     stream_username = data.get('stream_username') # Broadcaster's username
#
#     if not offer_sdp or not stream_username:
#         emit('stream_error', {'message': 'Missing offer_sdp or stream_username.'}, room=request.sid)
#         return
#
#     if current_user.username != stream_username:
#         emit('stream_error', {'message': 'User mismatch. Cannot send offer for another user.'}, room=request.sid)
#         return
#
#     stream_room = f"stream_{stream_username}"
#     # Emit to all SIDs in the room *except* the sender (broadcaster)
#     emit('webrtc_offer_received',
#          {'offer_sdp': offer_sdp, 'from_username': current_user.username},
#          room=stream_room,
#          skip_sid=request.sid)
#     print(f"Broadcaster {current_user.username} sent WebRTC offer to room {stream_room}")
#
#
# @socketio.on('webrtc_answer')
# def handle_webrtc_answer(data):
#     """Viewer sends their SDP answer back to the broadcaster."""
#     if not current_user.is_authenticated:
#         emit('stream_error', {'message': 'Authentication required to send answer.'}, room=request.sid)
#         return
#
#     answer_sdp = data.get('answer_sdp')
#     stream_username = data.get('stream_username') # Broadcaster's username (target of this answer)
#
#     if not answer_sdp or not stream_username:
#         emit('stream_error', {'message': 'Missing answer_sdp or stream_username.'}, room=request.sid)
#         return
#
#     broadcaster = User.query.filter_by(username=stream_username).first()
#     if not broadcaster:
#         emit('stream_error', {'message': f'Broadcaster {stream_username} not found.'}, room=request.sid)
#         return
#
#     # Emit the answer specifically to the broadcaster's personal room (their user ID)
#     # The broadcaster's client-side JS will handle this.
#     emit('webrtc_answer_received',
#          {'answer_sdp': answer_sdp, 'from_username': current_user.username, 'viewer_sid': request.sid},
#          room=str(broadcaster.id)) # Target broadcaster's user room
#     print(f"Viewer {current_user.username} (SID: {request.sid}) sent WebRTC answer to broadcaster {stream_username} (Room: {broadcaster.id})")
#
#
# @socketio.on('webrtc_ice_candidate')
# def handle_webrtc_ice_candidate(data):
#     """Used by both broadcaster and viewers to exchange ICE candidates."""
#     if not current_user.is_authenticated:
#         emit('stream_error', {'message': 'Authentication required to send ICE candidate.'}, room=request.sid)
#         return
#
#     candidate = data.get('candidate')
#     stream_username = data.get('stream_username') # The context of the stream this candidate belongs to
#     # target_username = data.get('target_username') # Optional: if sending to a specific user
#
#     if not candidate or not stream_username:
#         emit('stream_error', {'message': 'Missing candidate or stream_username.'}, room=request.sid)
#         return
#
#     stream_room = f"stream_{stream_username}"
#
#     # Relay the candidate to others in the stream room
#     # The client side will decide if the candidate is for them based on the WebRTC connection state
#     # or if more specific targeting is added via target_username / target_sid.
#     emit('webrtc_ice_candidate_received',
#          {'candidate': candidate, 'from_username': current_user.username},
#          room=stream_room,
#          skip_sid=request.sid)
#     print(f"User {current_user.username} sent ICE candidate to room {stream_room}: {candidate.get('candidate', '')[:30]}...")
#
# @socketio.on('stream_ended_webrtc')
# def handle_stream_ended_webrtc(data):
#     stream_username = data.get('stream_username')
#     if not stream_username:
#         print(f"Error: stream_username missing in stream_ended_webrtc from SID {request.sid}")
#         return
#
#     if not current_user.is_authenticated or current_user.username != stream_username:
#         # Only the broadcaster can declare their stream ended.
#         # Or, if an admin function, it would need different checks.
#         emit('stream_error', {'message': 'Unauthorized to end this stream.'}, room=request.sid)
#         print(f"Unauthorized attempt to end stream {stream_username} by SID {request.sid} (User: {current_user.username if current_user.is_authenticated else 'Anonymous'})")
#         return
#
#     stream_room = f"stream_{stream_username}"
#     # Notify all viewers in the room that the stream specifically ended by broadcaster command
#     emit('stream_really_ended', {'message': f'Stream by {stream_username} has ended.'}, room=stream_room, skip_sid=request.sid) # skip_sid to not notify self
#
#     # Optionally, update the backend status of the stream
#     # stream_obj = LiveStream.query.filter_by(user_id=current_user.id).first()
#     # if stream_obj and stream_obj.is_live:
#     #     stream_obj.is_live = False
#     #     db.session.commit()
#     #     print(f"Stream {stream_username} marked as not live in DB.")
#     # This backend update is currently handled by the form submission in manage_stream route.
#     # If client-side "Stop WebRTC Broadcast" should also make it not live on backend without form submission,
#     # then the above lines should be un-commented and DB session handling considered.
#
#     print(f"WebRTC stream ended by broadcaster {stream_username}. Viewers in room {stream_room} notified.")

@socketio.on('start_stream_recording_sfu')
def start_stream_recording_sfu(data):
    stream_username = data.get('stream_username')
    if not current_user.is_authenticated or current_user.username != stream_username:
        emit('stream_error', {'message': 'Authentication required or user mismatch.'}, room=request.sid)
        return

    live_stream = LiveStream.query.filter_by(user_id=current_user.id, is_live=True).first()
    if live_stream and live_stream.enable_recording:
        janus_server_url = current_app.config.get('JANUS_SERVER_URL', 'http://janusmy.conf.meetecho.com/janus') # Example default
        print(f"TODO: Janus API Call: Start recording for {stream_username} on {janus_server_url}. Stream ID: {live_stream.id}")
        # Actual requests.post(...) or Janus client call would go here.
        # On success, Janus might return a recording ID. Store if necessary.
        # Example: live_stream.janus_recording_id = ... ; db.session.commit()
        socketio.emit('recording_status_update', {'status': 'started', 'stream_id': live_stream.id, 'message': 'Recording started (simulated).'}, room=str(current_user.id))
    elif live_stream and not live_stream.enable_recording:
        print(f"Recording not enabled for stream by {stream_username}")
        socketio.emit('recording_status_update', {'status': 'disabled', 'stream_id': live_stream.id, 'message': 'Recording is not enabled for this stream.'}, room=str(current_user.id))
    else:
        print(f"No live stream found for {stream_username} to start recording or recording not enabled.")
        socketio.emit('recording_status_update', {'status': 'error', 'message': 'Live stream not found or recording not enabled.'}, room=str(current_user.id))

@socketio.on('stop_stream_recording_sfu')
def stop_stream_recording_sfu(data):
    stream_username = data.get('stream_username')
    if not current_user.is_authenticated or current_user.username != stream_username:
        emit('stream_error', {'message': 'Authentication required or user mismatch.'}, room=request.sid)
        return

    # Broadcaster is stopping the recording. We might find the stream by user_id.
    # It might still be live, or they might be stopping recording after the stream itself ended.
    live_stream = LiveStream.query.filter_by(user_id=current_user.id).order_by(LiveStream.created_at.desc()).first()

    if live_stream: # Check if any stream record exists for this user
        # Assuming we only stop if it was (potentially) being recorded or recording was enabled.
        # A more robust check might involve a specific 'is_recording' flag on the LiveStream model,
        # or checking if live_stream.janus_recording_id exists.
        # For now, we'll proceed if enable_recording was true, implying an attempt might have been made.
        if live_stream.enable_recording:
            janus_server_url = current_app.config.get('JANUS_SERVER_URL', 'http://janusmy.conf.meetecho.com/janus')
            print(f"TODO: Janus API Call: Stop recording for {stream_username} on {janus_server_url}. Stream ID: {live_stream.id}")
            # Actual requests.post(...) or Janus client call would go here.
            # Janus might send a webhook later with the final filename, or API call provides it.
            # For now, we assume filename is updated via another mechanism (e.g., webhook handler route).
            # Example: live_stream.recording_filename = "some_filename_from_janus.mjr"; db.session.commit();
            socketio.emit('recording_status_update', {'status': 'stopped', 'stream_id': live_stream.id, 'message': 'Recording stopped (simulated).'}, room=str(current_user.id))
            # Placeholder: if filename were available here:
            # live_stream.recording_filename = "simulated_recording.mp4"
            # db.session.commit()
        else:
            print(f"Recording was not enabled for stream by {stream_username}, so no stop action taken.")
            socketio.emit('recording_status_update', {'status': 'not_started', 'stream_id': live_stream.id, 'message': 'Recording was not enabled/started.'}, room=str(current_user.id))
    else:
        print(f"No stream record found for user {stream_username} to stop recording.")
        socketio.emit('recording_status_update', {'status': 'error', 'message': 'Stream record not found.'}, room=str(current_user.id))

# -------------------- Poll Room Events --------------------

@socketio.on('join_poll_room')
def handle_join_poll_room(data):
    if not isinstance(data, dict) or 'poll_id' not in data:
        current_app.logger.warning(f"Invalid data received for join_poll_room from SID {request.sid}: {data}")
        # emit('poll_room_error', {'message': 'Invalid poll_id provided.'}, room=request.sid) # Optional error to client
        return

    poll_id = data.get('poll_id')
    # Basic validation for poll_id format could be added here if necessary
    # For example, if poll_id is expected to be an integer or a specific string pattern.

    room_name = f'poll_{poll_id}'
    join_room(room_name)

    viewers_set = poll_room_viewers.setdefault(room_name, set())
    viewers_set.add(request.sid)
    viewer_count = len(viewers_set)

    socketio.emit('poll_viewer_update', {
        'poll_id': poll_id,
        'viewer_count': viewer_count
    }, room=room_name)

    user_info = f"SID {request.sid}"
    if current_user.is_authenticated:
        user_info = f"User {current_user.username} (SID {request.sid})"

    current_app.logger.info(f"{user_info} joined {room_name}, viewer count: {viewer_count}")
    # emit('joined_poll_room_ack', {'room': room_name, 'status': 'success', 'viewer_count': viewer_count}, room=request.sid) # Optional ack

@socketio.on('leave_poll_room')
def handle_leave_poll_room(data):
    if not isinstance(data, dict) or 'poll_id' not in data:
        current_app.logger.warning(f"Invalid data received for leave_poll_room from SID {request.sid}: {data}")
        return

    poll_id = data.get('poll_id')
    room_name = f'poll_{poll_id}'

    # It's good practice to leave the SocketIO room regardless of viewer tracking state
    leave_room(room_name)

    if room_name in poll_room_viewers:
        viewers_set = poll_room_viewers[room_name]
        viewers_set.discard(request.sid)
        viewer_count = len(viewers_set)

        if not viewers_set: # If set is empty
            del poll_room_viewers[room_name]
            current_app.logger.info(f"Room {room_name} is now empty and removed from tracking.")

        socketio.emit('poll_viewer_update', {
            'poll_id': poll_id,
            'viewer_count': viewer_count
        }, room=room_name)

        user_info = f"SID {request.sid}"
        if current_user.is_authenticated:
            user_info = f"User {current_user.username} (SID {request.sid})"

        current_app.logger.info(f"{user_info} left {room_name}, viewer count: {viewer_count}")
        # emit('left_poll_room_ack', {'room': room_name, 'status': 'success', 'viewer_count': viewer_count}, room=request.sid) # Optional ack
    else:
        current_app.logger.warning(f"Attempted to leave {room_name} by SID {request.sid}, but room was not in viewer tracking.")
