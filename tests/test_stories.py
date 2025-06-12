import unittest
import os
import shutil
import io
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import User, Story
from config import TestingConfig

class StoryTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create test users
        self.user1 = User(username='testuser1', email='test1@example.com')
        self.user1.set_password('password')
        self.user2 = User(username='testuser2', email='test2@example.com')
        self.user2.set_password('password')
        db.session.add_all([self.user1, self.user2])
        db.session.commit()

        # Ensure test story media folder exists and is empty
        self.story_media_folder = self.app.config['STORY_MEDIA_UPLOAD_FOLDER']
        if os.path.exists(self.story_media_folder):
            shutil.rmtree(self.story_media_folder)
        os.makedirs(self.story_media_folder, exist_ok=True)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

        # Clean up test story media folder
        if os.path.exists(self.story_media_folder):
            shutil.rmtree(self.story_media_folder)

    def login(self, username, password):
        return self.client.post('/login', data=dict(
            email=f'{username}@example.com',  # Assuming email is username@example.com
            password=password
        ), follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_story_model_creation(self):
        story = Story(user_id=self.user1.id, caption="Test caption")
        db.session.add(story)
        db.session.commit()

        self.assertIsNotNone(story.id)
        self.assertIsNotNone(story.timestamp)
        self.assertIsNotNone(story.expires_at)
        # Check if expires_at is roughly 24 hours after timestamp
        time_difference = story.expires_at - story.timestamp
        self.assertTrue(timedelta(hours=23, minutes=59) < time_difference < timedelta(hours=24, minutes=1))

        self.assertEqual(story.author, self.user1)
        self.assertIn(story, self.user1.stories.all())

    def test_create_story_page_load_unauthenticated(self):
        response = self.client.get('/story/create')
        self.assertEqual(response.status_code, 302) # Redirect to login

    def test_create_story_page_load_authenticated(self):
        self.login('testuser1', 'password')
        response = self.client.get('/story/create')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Upload Your Story', response.data)

    def test_stories_page_load_unauthenticated(self):
        response = self.client.get('/stories')
        self.assertEqual(response.status_code, 302) # Redirect to login

    def test_stories_page_load_authenticated(self):
        self.login('testuser1', 'password')
        response = self.client.get('/stories')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Today's Stories", response.data)

    def test_create_story_post(self):
        self.login('testuser1', 'password')

        # Simulate file upload
        data = {
            'caption': 'My Awesome Story',
            'media_file': (io.BytesIO(b"this is a dummy image content"), 'test_story.jpg')
        }

        response = self.client.post('/story/create', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to index (or stories page)
        self.assertIn(b'Your story has been posted!', response.data)

        story = Story.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(story)
        self.assertEqual(story.caption, 'My Awesome Story')
        self.assertIsNotNone(story.image_filename) # Assuming test.jpg is an image
        self.assertIsNone(story.video_filename)

        # Check if file was saved
        saved_file_path = os.path.join(self.story_media_folder, story.image_filename)
        self.assertTrue(os.path.exists(saved_file_path))

    def test_story_expiration_logic(self):
        # user1 creates a story
        story_expired = Story(user_id=self.user1.id, caption="Expired Story")
        # Manually set timestamp and expires_at to be in the past
        story_expired.timestamp = datetime.now(timezone.utc) - timedelta(days=2)
        story_expired.expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        story_active = Story(user_id=self.user1.id, caption="Active Story") # Defaults to now, expires in 24h

        db.session.add_all([story_expired, story_active])
        db.session.commit()

        # user2 follows user1
        self.user2.follow(self.user1)
        db.session.commit()

        self.login('testuser2', 'password')
        response = self.client.get('/stories')
        self.assertEqual(response.status_code, 200)

        self.assertNotIn(b'Expired Story', response.data)
        self.assertIn(b'Active Story', response.data)

        # Test current user's own active story
        own_active_story = Story(user_id=self.user2.id, caption="My Own Active Story")
        db.session.add(own_active_story)
        db.session.commit()

        response_after_own_story = self.client.get('/stories')
        self.assertIn(b'My Own Active Story', response_after_own_story.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
