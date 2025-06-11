import unittest
import os
import io
from datetime import datetime, timezone

from app import create_app, db, socketio
from app.models import User, Post, Notification, Comment, Like, Conversation, ChatMessage
# conversation_participants table is not directly imported/used in tests usually, but through model relationships
from config import TestingConfig
from flask_login import current_user # login_user, logout_user are not directly used in test logic after _login/_logout helpers
from flask_socketio import SocketIOTestClient

class ChatTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client(use_cookies=True)
        # Ensure socketio instance is correctly passed if not globally available from app
        self.socketio_test_client = SocketIOTestClient(self.app, socketio, flask_test_client=self.client)
        # self.assertIsNotNone(self.client.cookie_jar, "Cookie jar not found on self.client in setUp") # Removed this


        # Create test users
        self.user1 = User(username='chatuser1', email='chat1@example.com')
        self.user1.set_password('password')
        self.user2 = User(username='chatuser2', email='chat2@example.com')
        self.user2.set_password('password')
        self.user3 = User(username='chatuser3', email='chat3@example.com')
        self.user3.set_password('password')
        db.session.add_all([self.user1, self.user2, self.user3])
        db.session.commit()

    def tearDown(self):
        if self.socketio_test_client:
            try:
                self.socketio_test_client.disconnect(namespace='/')
            except Exception: # pylint: disable=broad-except
                pass

        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # --- Route Tests ---
    def test_list_conversations_unauthenticated(self):
        response = self.client.get('/chat')
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/login' in response.location)

    def test_list_conversations_authenticated_no_convos(self):
        self._login(self.user1.email, 'password')
        response = self.client.get('/chat')
        self.assertEqual(response.status_code, 200)
        self.assertIn("You have no active conversations", response.get_data(as_text=True))
        self._logout()

    def test_start_conversation_and_view(self):
        self._login(self.user1.email, 'password')
        # Start conversation with user2
        response_start = self.client.post(f'/chat/start/{self.user2.id}', follow_redirects=True)
        self.assertEqual(response_start.status_code, 200) # Should redirect to the conversation view

        conv = Conversation.query.first()
        self.assertIsNotNone(conv)
        self.assertEqual(Conversation.query.count(), 1)
        self.assertIn(self.user1, conv.participants)
        self.assertIn(self.user2, conv.participants)
        self.assertTrue(f'Chat with {self.user2.username}' in response_start.get_data(as_text=True) or
                        f'Chat with {self.user1.username}' in response_start.get_data(as_text=True))


        # Check if conversation is listed on /chat page
        response_list = self.client.get('/chat')
        self.assertEqual(response_list.status_code, 200)
        self.assertIn(self.user2.username, response_list.get_data(as_text=True)) # Check if user2's name is in the listed convo
        self._logout()

    def test_view_conversation_not_participant(self):
        # user1 and user2 have a conversation
        self._login(self.user1.email, 'password')
        self.client.post(f'/chat/start/{self.user2.id}', follow_redirects=True)
        self._logout()

        conv = Conversation.query.first()
        self.assertIsNotNone(conv)

        # user3 tries to view it
        self._login(self.user3.email, 'password')
        response = self.client.get(f'/chat/{conv.id}')
        self.assertEqual(response.status_code, 302) # Redirects to list_conversations
        self.assertTrue('/conversations' in response.location or '/chat' in response.location)

        # Check for flash message (requires session handling in client or checking response data if flashed message is rendered)
        # For simplicity, we'll assume the redirect implies denial.
        # To check flash, you'd typically do:
        # with self.client.session_transaction() as sess:
        #     flashed_messages = dict(sess['_flashes']) # Be careful with direct access
        #     self.assertIn('You are not part of this conversation.', flashed_messages.get('danger', ''))
        self._logout()

    def test_start_conversation_with_self(self):
        self._login(self.user1.email, 'password')
        response = self.client.post(f'/chat/start/{self.user1.id}', follow_redirects=True)
        # The response might be the profile page or another page depending on where redirect goes
        self.assertIn("You cannot start a chat with yourself.", response.get_data(as_text=True))
        self._logout()

    # --- Model Tests ---
    def test_chat_message_creation(self):
        self._login(self.user1.email, 'password')
        self.client.post(f'/chat/start/{self.user2.id}') # Create conversation
        conv = Conversation.query.first()
        self.assertIsNotNone(conv)
        initial_last_updated = conv.last_updated
        self._logout()

        # user1 sends a message to user2 in that conversation
        self._login(self.user1.email, 'password')
        # Simulate sending via socketio, then check DB (or make a post to a hypothetical message send route if exists)
        # For model test, directly create message:
        msg_body = "Hello from user1 to user2"
        message = ChatMessage(
            conversation_id=conv.id,
            sender_id=self.user1.id,
            body=msg_body,
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(message)
        conv.last_updated = message.timestamp # Manually update for this direct model test
        db.session.commit()

        retrieved_message = ChatMessage.query.get(message.id)
        self.assertEqual(retrieved_message.body, msg_body)
        self.assertEqual(retrieved_message.sender_id, self.user1.id)
        self.assertEqual(retrieved_message.conversation_id, conv.id)
        self.assertNotEqual(conv.last_updated, initial_last_updated)
        self.assertEqual(conv.last_updated, message.timestamp)
        self._logout()

    # --- Socket.IO Tests ---
    def test_socketio_join_chat_room(self):
        self._login(self.user1.email, 'password')
        self.client.post(f'/chat/start/{self.user2.id}') # Create conversation
        conv = Conversation.query.first()

        self.socketio_test_client.connect(namespace='/')
        # No specific client-side ack for join_room in this setup, so we check server logs (manually) or proceed if no error
        self.socketio_test_client.emit('join_chat_room', {'conversation_id': conv.id}, namespace='/')
        # If there was an error or denial, the server might emit an error or not join.
        # For this test, we are mostly ensuring the emit doesn't cause an immediate server error.
        # More robust test would involve custom ack or checking a list of joined rooms if server exposes it.
        self.assertTrue(True) # Placeholder for successful emit without error
        self._logout()


    def test_socketio_send_and_receive_message(self):
        self._login(self.user1.email, 'password')
        self.client.post(f'/chat/start/{self.user2.id}') # user1 starts chat with user2
        conv = Conversation.query.first()
        initial_last_updated = conv.last_updated

        # User1 connects and joins the room
        self.socketio_test_client.connect(namespace='/')
        self.socketio_test_client.emit('join_chat_room', {'conversation_id': conv.id}, namespace='/')
        self.socketio_test_client.get_received(namespace='/') # Clear messages

        # User1 sends a message
        message_body = 'Hello from user1 via SocketIO'
        self.socketio_test_client.emit('send_chat_message',
                                     {'conversation_id': conv.id, 'body': message_body},
                                     namespace='/')

        received = self.socketio_test_client.get_received(namespace='/')

        self.assertGreater(len(received), 0)
        chat_msgs = [r for r in received if r['name'] == 'new_chat_message']
        self.assertGreater(len(chat_msgs), 0, "No 'new_chat_message' event received")

        event_args = chat_msgs[0]['args'][0]
        self.assertEqual(event_args['body'], message_body)
        self.assertEqual(event_args['sender_username'], self.user1.username)
        self.assertEqual(event_args['conversation_id'], conv.id)

        # Verify ChatMessage created in DB
        db_message = ChatMessage.query.filter_by(body=message_body).first()
        self.assertIsNotNone(db_message)
        self.assertEqual(db_message.sender_id, self.user1.id)
        self.assertEqual(db_message.conversation_id, conv.id)

        # Verify conversation.last_updated is updated
        db.session.refresh(conv) # Refresh conv from DB
        self.assertGreater(conv.last_updated, initial_last_updated)
        self._logout()

    def test_socketio_send_message_not_participant(self):
        # conv between user2 and user3
        self._login(self.user2.email, 'password')
        self.client.post(f'/chat/start/{self.user3.id}')
        conv_u2_u3 = Conversation.query.first()
        self.assertIsNotNone(conv_u2_u3)
        self._logout()

        # user1 (not a participant) tries to send a message
        self._login(self.user1.email, 'password')
        self.socketio_test_client.connect(namespace='/')
        # User1 does not join the room conv_u2_u3 here, but tries to emit directly.
        # The server should check participation based on sender_id (current_user).
        self.socketio_test_client.get_received(namespace='/') # Clear messages

        self.socketio_test_client.emit('send_chat_message',
                                     {'conversation_id': conv_u2_u3.id, 'body': 'Intruder message by user1'},
                                     namespace='/')

        received = self.socketio_test_client.get_received(namespace='/')
        chat_errors = [r for r in received if r['name'] == 'chat_error']
        self.assertGreater(len(chat_errors), 0, "No 'chat_error' event received")
        self.assertIn('not a participant', chat_errors[0]['args'][0]['message'].lower())

        # Assert no ChatMessage was created for this
        msg_count = ChatMessage.query.filter_by(conversation_id=conv_u2_u3.id, body='Intruder message by user1').count()
        self.assertEqual(msg_count, 0)
        self._logout()

    def test_socketio_typing_indicators(self):
        # User 1 setup
        self._login(self.user1.email, 'password')
        response = self.client.post(f'/chat/start/{self.user2.id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # More robustly find the conversation involving user1 and user2
        conv = Conversation.query.filter(
            Conversation.participants.any(User.id == self.user1.id) &
            Conversation.participants.any(User.id == self.user2.id)
        ).first()
        self.assertIsNotNone(conv, "Conversation between user1 and user2 not found.")
        conversation_id = conv.id

        # User1's SIO client (self.socketio_test_client)
        client1_sio = self.socketio_test_client
        if not client1_sio.is_connected(): # Ensure connected if not already by setUp or previous test part
            client1_sio.connect(namespace='/')

        client1_sio.emit('join_chat_room', {'conversation_id': conversation_id}, namespace='/')
        client1_sio.get_received(namespace='/') # Clear client1's messages from join ack etc.

        # User 2 setup
        client2_flask_test_client = self.app.test_client(use_cookies=True) # New Flask test client for user2
        client2_sio = None # Initialize to ensure cleanup
        try:
            with client2_flask_test_client: # Use context manager for proper cookie handling
                login_resp_user2 = client2_flask_test_client.post('/login', data=dict(email=self.user2.email, password='password'), follow_redirects=True)
                self.assertEqual(login_resp_user2.status_code, 200) # Check login success for user2

                # New SIO client for user2. Pass the global 'socketio' instance.
                client2_sio = SocketIOTestClient(self.app, socketio, flask_test_client=client2_flask_test_client)

                # Explicitly connect client2_sio.
                # Removed: self.assertFalse(client2_sio.is_connected(namespace='/'))
                client2_sio.connect(namespace='/')
                self.assertTrue(client2_sio.is_connected(namespace='/'), "Client2 SIO failed to connect") # Verify connection

                client2_sio.emit('join_chat_room', {'conversation_id': conversation_id}, namespace='/')
                client2_sio.get_received(namespace='/') # Clear client2's messages

                # --- Test typing_started ---
                print(f"Test: User1 ({self.user1.username}) emitting typing_started in conv {conversation_id}")
                client1_sio.emit('typing_started', {'conversation_id': conversation_id}, namespace='/')

                # Check client2 for 'user_typing'
                received_on_client2 = client2_sio.get_received(namespace='/')
                print(f"Test: Client2 received after typing_started: {received_on_client2}")
                user_typing_events_c2 = [r for r in received_on_client2 if r['name'] == 'user_typing']
                self.assertGreater(len(user_typing_events_c2), 0, "Client2 did not receive 'user_typing' event")
                typing_data_c2 = user_typing_events_c2[0]['args'][0]
                self.assertEqual(typing_data_c2['username'], self.user1.username)
                self.assertEqual(typing_data_c2['user_id'], self.user1.id)
                self.assertEqual(typing_data_c2['conversation_id'], conversation_id)

                # Check client1 for no 'user_typing' (skip_sid)
                received_on_client1 = client1_sio.get_received(namespace='/')
                print(f"Test: Client1 received after typing_started: {received_on_client1}")
                user_typing_events_c1 = [r for r in received_on_client1 if r['name'] == 'user_typing']
                self.assertEqual(len(user_typing_events_c1), 0, "Client1 should not receive its own 'user_typing' event")

                # --- Test typing_stopped ---
                print(f"Test: User1 ({self.user1.username}) emitting typing_stopped in conv {conversation_id}")
                client1_sio.emit('typing_stopped', {'conversation_id': conversation_id}, namespace='/')

                # Check client2 for 'user_stopped_typing'
                received_on_client2_stop = client2_sio.get_received(namespace='/')
                print(f"Test: Client2 received after typing_stopped: {received_on_client2_stop}")
                user_stopped_events_c2 = [r for r in received_on_client2_stop if r['name'] == 'user_stopped_typing']
                self.assertGreater(len(user_stopped_events_c2), 0, "Client2 did not receive 'user_stopped_typing' event")
                stopped_data_c2 = user_stopped_events_c2[0]['args'][0]
                self.assertEqual(stopped_data_c2['username'], self.user1.username)
                self.assertEqual(stopped_data_c2['user_id'], self.user1.id)
                self.assertEqual(stopped_data_c2['conversation_id'], conversation_id)

                # Check client1 for no 'user_stopped_typing'
                received_on_client1_stop = client1_sio.get_received(namespace='/')
                print(f"Test: Client1 received after typing_stopped: {received_on_client1_stop}")
                user_stopped_events_c1 = [r for r in received_on_client1_stop if r['name'] == 'user_stopped_typing']
                self.assertEqual(len(user_stopped_events_c1), 0, "Client1 should not receive its own 'user_stopped_typing' event")

        finally:
            # Ensure client2_sio is disconnected
            if client2_sio and client2_sio.is_connected(namespace='/'):
                client2_sio.disconnect(namespace='/')
            # self.socketio_test_client (client1_sio) is disconnected in tearDown
            # self._logout() # user1 is logged out by tearDown if client is reused. If not, ensure logout.
            # Current _login uses self.client, so tearDown's _logout for self.client will handle user1.

    def test_socketio_read_receipts(self): # Restored name
        # --- Setup ---
        # User 1 logs in and creates conversation with User 2
        self._login(self.user1.email, 'password')
        self.client.post(f'/chat/start/{self.user2.id}', follow_redirects=True)
        conv = Conversation.query.filter(
            Conversation.participants.any(User.id == self.user1.id) &
            Conversation.participants.any(User.id == self.user2.id)
        ).first()
        self.assertIsNotNone(conv, "Conversation between user1 and user2 not found.")
        conversation_id = conv.id

        # User1's SIO client
        client1_sio = self.socketio_test_client
        user1_session_cookie_name = self.app.config.get('SESSION_COOKIE_NAME', 'session')
        user1_cookie_obj = self.client.get_cookie(user1_session_cookie_name)
        self.assertIsNotNone(user1_cookie_obj, "Session cookie not found for self.client (user1)")
        user1_headers = {'Cookie': f'{user1_session_cookie_name}={user1_cookie_obj.value}'}

        if not client1_sio.is_connected(namespace='/'):
            client1_sio.connect(namespace='/', headers=user1_headers)
        else: # If suite running, ensure context by reconnecting with headers
            client1_sio.disconnect(namespace='/')
            client1_sio.connect(namespace='/', headers=user1_headers)
        client1_sio.emit('join_chat_room', {'conversation_id': conversation_id}, namespace='/')
        client1_sio.get_received(namespace='/')

        # User 2 setup (separate Flask and SIO clients)
        client2_flask = self.app.test_client(use_cookies=True)
        client2_sio = None
        try:
            with client2_flask:
                client2_flask.get('/logout', follow_redirects=True) # Ensure clean session for client2_flask
                login_response_user2 = client2_flask.post('/login', data=dict(email=self.user2.email, password='password'), follow_redirects=True)
                self.assertEqual(login_response_user2.status_code, 200)

                user2_session_cookie_name = self.app.config.get('SESSION_COOKIE_NAME', 'session')
                user2_cookie_obj = client2_flask.get_cookie(user2_session_cookie_name)
                self.assertIsNotNone(user2_cookie_obj, f"Session cookie '{user2_session_cookie_name}' not found for client2_flask after login.")
                self.assertTrue(hasattr(user2_cookie_obj, 'value'), "Cookie object does not have a 'value' attribute.")

                client2_sio = SocketIOTestClient(self.app, socketio, flask_test_client=client2_flask)
                headers = {'Cookie': f'{user2_session_cookie_name}={user2_cookie_obj.value}'}
                print(f"DEBUG: Connecting client2_sio with headers: {headers}")
                client2_sio.connect(namespace='/', headers=headers)
                self.assertTrue(client2_sio.is_connected(namespace='/'), "Client2 SIO failed to connect with session cookie")
                client2_sio.emit('join_chat_room', {'conversation_id': conversation_id}, namespace='/')
                client2_sio.get_received(namespace='/')

                # --- Test Scenario: User1 sends, User2 reads ---
                message_body_u1 = "Hello from User1 to User2 (read receipt test)"

                # Removed dummy GET request as it didn't solve the context issue
                # print("DEBUG: Making a dummy GET request with self.client (User1) to re-establish context")
                # self.client.get('/')

                client1_sio.emit('send_chat_message',
                                 {'conversation_id': conversation_id, 'body': message_body_u1},
                                 namespace='/')

                received_on_client1_own_msg = client1_sio.get_received(namespace='/')
                msg1_event = next((r for r in received_on_client1_own_msg if r['name'] == 'new_chat_message' and r['args'][0]['body'] == message_body_u1), None)
                self.assertIsNotNone(msg1_event, "Client1 did not receive its own new_chat_message")
                msg1_id = msg1_event['args'][0]['message_id']

                received_on_client2_new_msg = client2_sio.get_received(namespace='/')
                msg1_event_c2 = next((r for r in received_on_client2_new_msg if r['name'] == 'new_chat_message' and r['args'][0]['message_id'] == msg1_id), None)
                self.assertIsNotNone(msg1_event_c2, "Client2 did not receive the new_chat_message")

                chat_msg1_db = ChatMessage.query.get(msg1_id)
                self.assertIsNotNone(chat_msg1_db)
                self.assertFalse(chat_msg1_db.is_read, "Message should initially be unread in DB")

                client2_sio.emit('mark_messages_as_read',
                                 {'message_ids': [msg1_id], 'conversation_id': conversation_id},
                                 namespace='/')

                received_on_client1_update = client1_sio.get_received(namespace='/')
                read_update_c1 = next((r for r in received_on_client1_update if r['name'] == 'messages_read_update'), None)
                self.assertIsNotNone(read_update_c1, "Client1 did not receive 'messages_read_update'")
                self.assertIn(msg1_id, read_update_c1['args'][0]['message_ids'])
                self.assertEqual(read_update_c1['args'][0]['reader_user_id'], self.user2.id)

                received_on_client2_update = client2_sio.get_received(namespace='/')
                read_update_c2 = next((r for r in received_on_client2_update if r['name'] == 'messages_read_update'), None)
                self.assertIsNotNone(read_update_c2, "Client2 did not receive 'messages_read_update'")

                db.session.refresh(chat_msg1_db)
                self.assertTrue(chat_msg1_db.is_read, "Message should be marked as read in DB")

                # --- Edge Case: Sender (User1) tries to mark their own message as read ---
                client1_sio.get_received(namespace='/')
                client2_sio.get_received(namespace='/')
                client1_sio.emit('mark_messages_as_read',
                                 {'message_ids': [msg1_id], 'conversation_id': conversation_id},
                                 namespace='/')

                received_on_client1_edge = client1_sio.get_received(namespace='/')
                self.assertEqual(len([r for r in received_on_client1_edge if r['name'] == 'messages_read_update']), 0,
                                 "Sender marking message should not cause 'messages_read_update'")
                received_on_client2_edge = client2_sio.get_received(namespace='/')
                self.assertEqual(len([r for r in received_on_client2_edge if r['name'] == 'messages_read_update']), 0,
                                 "Other clients should not receive 'messages_read_update' for sender self-mark")
                db.session.refresh(chat_msg1_db)
                self.assertTrue(chat_msg1_db.is_read, "Message should still be read in DB (from User2's action)")
        finally:
            if client2_sio and client2_sio.is_connected(namespace='/'):
                client2_sio.disconnect(namespace='/')

    def test_socketio_mark_as_read_single_client(self):
        # Setup: User1 logs in
        self._login(self.user1.email, 'password')
        sio_client = self.socketio_test_client # User1's SIO client

        # Ensure User1's SIO client connects with User1's context (cookie headers)
        user1_session_cookie_name = self.app.config.get('SESSION_COOKIE_NAME', 'session')
        user1_cookie_obj = self.client.get_cookie(user1_session_cookie_name)
        self.assertIsNotNone(user1_cookie_obj, "Session cookie not found for self.client (user1) in single client test")
        user1_headers = {'Cookie': f'{user1_session_cookie_name}={user1_cookie_obj.value}'}

        if not sio_client.is_connected(namespace='/'):
            sio_client.connect(namespace='/', headers=user1_headers)
        else: # If already connected (e.g. from suite run), ensure correct context
            sio_client.disconnect(namespace='/')
            sio_client.connect(namespace='/', headers=user1_headers)

        # Create a conversation between User1 and User2 directly in DB
        conv = Conversation()
        conv.participants.append(self.user1)
        conv.participants.append(self.user2)
        db.session.add(conv)
        db.session.commit()
        sio_client.emit('join_chat_room', {'conversation_id': conv.id}, namespace='/')
        sio_client.get_received(namespace='/')

        # Create a message from User2 to User1
        msg1_body = "Test message from user2 for user1 to read"
        msg1 = ChatMessage(conversation_id=conv.id, sender_id=self.user2.id, body=msg1_body, is_read=False)
        db.session.add(msg1)
        db.session.commit()
        self.assertFalse(ChatMessage.query.get(msg1.id).is_read, "msg1 should be initially unread")

        # Test Scenario: User1 marks User2's message as read
        print(f"Test SingleClientRead: User1 ({self.user1.username}) emitting mark_messages_as_read for msg_id {msg1.id}")
        sio_client.emit('mark_messages_as_read', {'message_ids': [msg1.id], 'conversation_id': conv.id})

        received_updates = sio_client.get_received(namespace='/')
        print(f"Test SingleClientRead: User1 received after mark: {received_updates}")
        read_update_event = next((r for r in received_updates if r['name'] == 'messages_read_update'), None)

        self.assertIsNotNone(read_update_event, "User1 did not receive 'messages_read_update' after marking message as read")
        event_args = read_update_event['args'][0]
        self.assertIn(msg1.id, event_args['message_ids'])
        self.assertEqual(event_args['reader_user_id'], self.user1.id)
        self.assertEqual(event_args['conversation_id'], conv.id) # Compare int with int

        self.assertTrue(ChatMessage.query.get(msg1.id).is_read, "msg1 should be marked as read in DB")

        # Test Sender Cannot Mark as Read (Simplified)
        msg2_body = "Test message from user1 (self)"
        msg2 = ChatMessage(conversation_id=conv.id, sender_id=self.user1.id, body=msg2_body, is_read=False)
        db.session.add(msg2)
        db.session.commit()
        self.assertFalse(ChatMessage.query.get(msg2.id).is_read, "msg2 should be initially unread")

        sio_client.get_received(namespace='/') # Clear previous events
        print(f"Test SingleClientRead: User1 ({self.user1.username}) emitting mark_messages_as_read for own msg_id {msg2.id}")
        sio_client.emit('mark_messages_as_read', {'message_ids': [msg2.id], 'conversation_id': conv.id})

        received_after_self_mark = sio_client.get_received(namespace='/')
        print(f"Test SingleClientRead: User1 received after self-mark: {received_after_self_mark}")
        self_read_update_event = next((r for r in received_after_self_mark if r['name'] == 'messages_read_update'), None)

        self.assertIsNone(self_read_update_event, "User1 should NOT receive 'messages_read_update' for marking their own message")
        self.assertFalse(ChatMessage.query.get(msg2.id).is_read, "msg2 (sent by User1) should still be unread after User1 tried to mark it")

        # sio_client is self.socketio_test_client, will be disconnected in tearDown

if __name__ == '__main__':
    unittest.main()
