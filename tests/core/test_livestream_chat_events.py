import unittest
from app import create_app, db, socketio as app_socketio # Import the app's socketio instance
from app.core.models import User, LiveStream, StreamChatMessage
from config import TestingConfig
from datetime import datetime, timezone
from flask_socketio import SocketIOTestClient, emit # Added emit for potential server-side test emits
from flask_login import login_user # To simulate login for socketio context

class LiveStreamChatSocketIOEventsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create users
        self.streamer = User(username='chat_streamer', email='chat_streamer@example.com')
        self.streamer.set_password('password123')
        self.viewer1 = User(username='chat_viewer1', email='chat_viewer1@example.com')
        self.viewer1.set_password('password123')
        self.viewer2 = User(username='chat_viewer2', email='chat_viewer2@example.com')
        self.viewer2.set_password('password123')
        db.session.add_all([self.streamer, self.viewer1, self.viewer2])
        db.session.commit()

        # Create a LiveStream
        self.live_stream = LiveStream(user_id=self.streamer.id, title="Live Chat Test Stream")
        db.session.add(self.live_stream)
        db.session.commit()

        # Initialize SocketIO test client
        # The SocketIOTestClient needs the Flask app and the SocketIO instance from the app.
        self.socketio_test_client = SocketIOTestClient(self.app, app_socketio)

        # It's often useful to have separate clients for different users in tests
        self.client_viewer1 = SocketIOTestClient(self.app, app_socketio)
        self.client_viewer2 = SocketIOTestClient(self.app, app_socketio)


    def tearDown(self):
        # Ensure clients are disconnected if they were connected
        if self.socketio_test_client.is_connected():
            self.socketio_test_client.disconnect()
        if self.client_viewer1.is_connected():
            self.client_viewer1.disconnect()
        if self.client_viewer2.is_connected():
            self.client_viewer2.disconnect()

        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login_user_for_socketio(self, user_email, user_password):
        """
        Log in a user via Flask test client to establish session context
        for subsequent SocketIO connections from that "user".
        This is one way to handle authentication with Flask-SocketIO.
        The SocketIOTestClient itself doesn't handle form logins.
        """
        # Use the standard Flask test client for login
        http_client = self.app.test_client()
        http_client.post('/login', data=dict(
            email=user_email,
            password=user_password
        ), follow_redirects=True)
        return http_client # Return if needed for further HTTP requests in the same session

    def test_join_stream_chat_authenticated(self):
        # Simulate login for viewer1 before connecting with SocketIO client
        # This sets up the Flask session which Flask-SocketIO can use
        with self.app.test_request_context(): # Push request context for login_user
            login_user(self.viewer1)

            # Now connect the SocketIO client, it should pick up current_user
            self.client_viewer1.connect()
            self.assertTrue(self.client_viewer1.is_connected())

            self.client_viewer1.emit('join_stream_chat', {'stream_id': self.live_stream.id})
            received = self.client_viewer1.get_received() # Get all received events

            # Check for acknowledgement
            ack_event = next((msg for msg in received if msg['name'] == 'joined_stream_chat_ack'), None)
            self.assertIsNotNone(ack_event)
            self.assertEqual(ack_event['args'][0]['stream_id'], self.live_stream.id)
            self.assertEqual(ack_event['args'][0]['room'], f'stream_chat_{self.live_stream.id}')

        self.client_viewer1.disconnect()

    def test_join_stream_chat_unauthenticated(self):
        # Connect without logging in user
        self.client_viewer1.connect()
        self.assertTrue(self.client_viewer1.is_connected())

        self.client_viewer1.emit('join_stream_chat', {'stream_id': self.live_stream.id})
        received = self.client_viewer1.get_received()

        error_event = next((msg for msg in received if msg['name'] == 'stream_chat_error'), None)
        self.assertIsNotNone(error_event)
        self.assertEqual(error_event['args'][0]['message'], 'Authentication required.')
        self.client_viewer1.disconnect()

    def test_send_and_receive_stream_chat_message(self):
        # Simulate login for viewer1 and viewer2
        with self.app.test_request_context():
            login_user(self.viewer1)
            self.client_viewer1.connect()
            self.client_viewer1.emit('join_stream_chat', {'stream_id': self.live_stream.id})
            _ = self.client_viewer1.get_received() # Clear ack

        with self.app.test_request_context():
            login_user(self.viewer2)
            self.client_viewer2.connect()
            self.client_viewer2.emit('join_stream_chat', {'stream_id': self.live_stream.id})
            _ = self.client_viewer2.get_received() # Clear ack

        # Viewer1 sends a message
        test_message = "Hello from viewer1 in stream chat!"
        with self.app.test_request_context(): # Need context for current_user when emitting
            login_user(self.viewer1) # Set current_user for the emit context
            self.client_viewer1.emit('send_stream_chat_message', {
                'stream_id': self.live_stream.id,
                'message': test_message
            })

        # Check if message is saved in DB
        saved_msg = StreamChatMessage.query.filter_by(stream_id=self.live_stream.id, user_id=self.viewer1.id).first()
        self.assertIsNotNone(saved_msg)
        self.assertEqual(saved_msg.message, test_message)

        # Check if viewer1 receives the message back (broadcast includes sender)
        received_viewer1 = self.client_viewer1.get_received()
        msg_event_v1 = next((msg for msg in received_viewer1 if msg['name'] == 'new_stream_chat_message'), None)
        self.assertIsNotNone(msg_event_v1)
        self.assertEqual(msg_event_v1['args'][0]['message'], test_message)
        self.assertEqual(msg_event_v1['args'][0]['sender_id'], self.viewer1.id)
        self.assertEqual(msg_event_v1['args'][0]['sender_username'], self.viewer1.username)

        # Check if viewer2 receives the message
        received_viewer2 = self.client_viewer2.get_received()
        msg_event_v2 = next((msg for msg in received_viewer2 if msg['name'] == 'new_stream_chat_message'), None)
        self.assertIsNotNone(msg_event_v2)
        self.assertEqual(msg_event_v2['args'][0]['message'], test_message)
        self.assertEqual(msg_event_v2['args'][0]['sender_id'], self.viewer1.id)
        self.assertEqual(msg_event_v2['args'][0]['sender_username'], self.viewer1.username)

        self.client_viewer1.disconnect()
        self.client_viewer2.disconnect()

    def test_send_stream_chat_message_unauthenticated(self):
        # Connect viewer1 without login
        self.client_viewer1.connect()
        self.client_viewer1.emit('join_stream_chat', {'stream_id': self.live_stream.id}) # Join might fail or not matter here
        _ = self.client_viewer1.get_received() # Clear received

        self.client_viewer1.emit('send_stream_chat_message', {
            'stream_id': self.live_stream.id,
            'message': "Unauthenticated message attempt"
        })
        received = self.client_viewer1.get_received()
        error_event = next((msg for msg in received if msg['name'] == 'stream_chat_error'), None)
        self.assertIsNotNone(error_event)
        self.assertEqual(error_event['args'][0]['message'], 'Authentication required to send message.')

        # Verify message was not saved
        self.assertIsNone(StreamChatMessage.query.filter_by(message="Unauthenticated message attempt").first())
        self.client_viewer1.disconnect()

    def test_leave_stream_chat(self):
        # Login viewer1, connect, join room
        with self.app.test_request_context():
            login_user(self.viewer1)
            self.client_viewer1.connect()
            self.client_viewer1.emit('join_stream_chat', {'stream_id': self.live_stream.id})
            _ = self.client_viewer1.get_received() # Clear ack

        # Emit leave event
        self.client_viewer1.emit('leave_stream_chat', {'stream_id': self.live_stream.id})
        # There's no specific server-side ACK for 'leave_stream_chat' in the current implementation.
        # Verification of leave is typically done by checking if user stops receiving messages for that room,
        # or by inspecting server-side room lists (which is harder with test client alone).
        # For this test, we'll assume the leave_room(room) call in the event handler works if the event is processed.
        # We can check that no further messages are received if another user sends one.

        # Viewer2 joins and sends a message
        with self.app.test_request_context():
            login_user(self.viewer2)
            self.client_viewer2.connect()
            self.client_viewer2.emit('join_stream_chat', {'stream_id': self.live_stream.id})
            _ = self.client_viewer2.get_received()

            self.client_viewer2.emit('send_stream_chat_message', {
                'stream_id': self.live_stream.id,
                'message': "Message after viewer1 left"
            })

        # Viewer1 should not receive this message
        received_viewer1_after_leave = self.client_viewer1.get_received()
        msg_event_v1_after_leave = next((msg for msg in received_viewer1_after_leave if msg['name'] == 'new_stream_chat_message'), None)
        self.assertIsNone(msg_event_v1_after_leave) # Viewer1 should not get it

        self.client_viewer1.disconnect()
        self.client_viewer2.disconnect()

if __name__ == '__main__':
    unittest.main(verbosity=2)
