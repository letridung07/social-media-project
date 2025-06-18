import unittest
from app import create_app, db
from app.core.models import User, LiveStream, StreamChatMessage
from config import TestingConfig
from datetime import datetime, timedelta, timezone

class LiveStreamModelCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create test users
        self.user1 = User(username='streamer1', email='streamer1@example.com')
        self.user1.set_password('password123')
        self.user2 = User(username='viewer1', email='viewer1@example.com')
        self.user2.set_password('password456')
        db.session.add_all([self.user1, self.user2])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_create_livestream(self):
        """Test creating a LiveStream instance."""
        now = datetime.now(timezone.utc)
        stream = LiveStream(
            user_id=self.user1.id,
            title="My First Live Stream",
            description="A test stream about coding.",
            status="upcoming",
            created_at=now,
            start_time=now + timedelta(hours=1)
        )
        db.session.add(stream)
        db.session.commit()

        retrieved_stream = LiveStream.query.filter_by(title="My First Live Stream").first()
        self.assertIsNotNone(retrieved_stream)
        self.assertEqual(retrieved_stream.user_id, self.user1.id)
        self.assertEqual(retrieved_stream.description, "A test stream about coding.")
        self.assertEqual(retrieved_stream.status, "upcoming")
        self.assertEqual(retrieved_stream.created_at, now)
        self.assertEqual(retrieved_stream.start_time, now + timedelta(hours=1))
        self.assertIsNone(retrieved_stream.end_time)
        self.assertIsNone(retrieved_stream.stream_key) # Key not generated until start
        self.assertIsNone(retrieved_stream.media_server_url)

    def test_livestream_default_values(self):
        """Test default values for LiveStream."""
        stream = LiveStream(user_id=self.user1.id, title="Defaults Test")
        db.session.add(stream)
        db.session.commit()

        self.assertEqual(stream.status, "upcoming") # Default status
        self.assertIsNotNone(stream.created_at) # Should be set by default lambda
        self.assertIsNotNone(stream.start_time) # Should be set by default lambda (or very close to created_at)
        # Check if start_time is close to created_at (within a small delta)
        self.assertTrue(abs((stream.start_time - stream.created_at).total_seconds()) < 2)


    def test_livestream_relationships(self):
        """Test relationships for LiveStream."""
        stream = LiveStream(user_id=self.user1.id, title="Relationship Test Stream")
        db.session.add(stream)
        db.session.commit()

        self.assertEqual(stream.user, self.user1)
        self.assertIn(stream, self.user1.live_streams)

    def test_livestream_status_transitions(self):
        """Test changing status of a LiveStream."""
        stream = LiveStream(user_id=self.user1.id, title="Status Transition Test")
        db.session.add(stream)
        db.session.commit()

        self.assertEqual(stream.status, "upcoming")

        stream.status = "live"
        stream.stream_key = "testkey123"
        stream.media_server_url = "rtmp://example.com/live/testkey123"
        stream.start_time = datetime.now(timezone.utc)
        db.session.commit()
        self.assertEqual(stream.status, "live")
        self.assertEqual(stream.stream_key, "testkey123")

        stream.status = "ended"
        stream.end_time = datetime.now(timezone.utc)
        db.session.commit()
        self.assertEqual(stream.status, "ended")
        self.assertIsNotNone(stream.end_time)

    def test_livestream_stream_key_uniqueness(self):
        """Test stream_key uniqueness constraint."""
        stream1 = LiveStream(user_id=self.user1.id, title="Unique Key Test 1", stream_key="unique_key_abc")
        db.session.add(stream1)
        db.session.commit()

        stream2 = LiveStream(user_id=self.user2.id, title="Unique Key Test 2", stream_key="unique_key_abc")
        db.session.add(stream2)
        with self.assertRaises(Exception) as context: # Catches IntegrityError from SQLAlchemy
            db.session.commit()
        self.assertTrue('UNIQUE constraint failed' in str(context.exception) or 'Duplicate entry' in str(context.exception)) # SQLite vs MySQL
        db.session.rollback() # Rollback the failed transaction

    def test_create_stream_chat_message(self):
        """Test creating a StreamChatMessage instance."""
        stream = LiveStream(user_id=self.user1.id, title="Chat Message Test Stream")
        db.session.add(stream)
        db.session.commit()

        chat_msg_time = datetime.now(timezone.utc)
        message = StreamChatMessage(
            stream_id=stream.id,
            user_id=self.user2.id,
            message="Hello from viewer1!",
            timestamp=chat_msg_time
        )
        db.session.add(message)
        db.session.commit()

        retrieved_message = StreamChatMessage.query.filter_by(message="Hello from viewer1!").first()
        self.assertIsNotNone(retrieved_message)
        self.assertEqual(retrieved_message.stream_id, stream.id)
        self.assertEqual(retrieved_message.user_id, self.user2.id)
        self.assertEqual(retrieved_message.timestamp, chat_msg_time)

    def test_streamchatmessage_default_timestamp(self):
        """Test default timestamp for StreamChatMessage."""
        stream = LiveStream(user_id=self.user1.id, title="Chat Default Timestamp")
        db.session.add(stream)
        db.session.commit()

        message = StreamChatMessage(stream_id=stream.id, user_id=self.user2.id, message="Testing default time")
        db.session.add(message)
        db.session.commit()
        self.assertIsNotNone(message.timestamp)

    def test_streamchatmessage_relationships(self):
        """Test relationships for StreamChatMessage."""
        stream = LiveStream(user_id=self.user1.id, title="Chat Relationship Test")
        db.session.add(stream)
        db.session.commit()

        message = StreamChatMessage(stream_id=stream.id, user_id=self.user2.id, message="Test msg")
        db.session.add(message)
        db.session.commit()

        self.assertEqual(message.stream, stream)
        self.assertEqual(message.user, self.user2)
        self.assertIn(message, stream.chat_messages) # Assumes backref is 'chat_messages'
        self.assertIn(message, self.user2.stream_chat_messages) # Assumes backref is 'stream_chat_messages'

if __name__ == '__main__':
    unittest.main(verbosity=2)
