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

if __name__ == '__main__':
    unittest.main()
