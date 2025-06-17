import unittest
import os
import shutil
import io
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import User, Story
from config import TestingConfig
from flask import url_for # For route tests
from werkzeug.datastructures import FileStorage # For mock file upload in route tests

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

    def test_story_creation_scheduled(self):
        now = datetime.now(timezone.utc)
        schedule_time = now + timedelta(days=1)
        # User1 is used from setUp
        story = Story(caption="Scheduled story", author=self.user1,
                      scheduled_for=schedule_time, is_published=False, image_filename="schedule_test.jpg")
        db.session.add(story)
        db.session.commit()

        retrieved_story = Story.query.filter_by(caption="Scheduled story").first()
        self.assertIsNotNone(retrieved_story)
        self.assertEqual(retrieved_story.scheduled_for, schedule_time)
        self.assertFalse(retrieved_story.is_published)
        self.assertIsNone(retrieved_story.expires_at) # expires_at should not be set if scheduled

    def test_story_creation_published_immediately(self):
        # User1 is used from setUp
        story = Story(caption="Immediate story", author=self.user1, is_published=True, image_filename="immediate_test.jpg")
        # __init__ should set expires_at based on current time + 24h if is_published=True
        db.session.add(story)
        db.session.commit()

        retrieved_story = Story.query.filter_by(caption="Immediate story").first()
        self.assertIsNotNone(retrieved_story)
        self.assertIsNone(retrieved_story.scheduled_for)
        self.assertTrue(retrieved_story.is_published)
        self.assertIsNotNone(retrieved_story.expires_at)
        # Check if expires_at is roughly 24 hours from creation (within a small delta)
        # Need to fetch the timestamp from the object itself as it's set by default=utcnow
        expected_expires_at = retrieved_story.timestamp + timedelta(hours=24)
        self.assertAlmostEqual(retrieved_story.expires_at, expected_expires_at, delta=timedelta(seconds=10)) # Increased delta for potential DB save/retrieve delays

    def test_story_is_published_defaults_to_false_and_expires_at_is_none(self):
        # User1 is used from setUp
        # The Story model's is_published field defaults to False.
        # The __init__ method should not set expires_at if is_published is False.
        story = Story(caption="Default published state story", author=self.user1, image_filename="default_pub_test.jpg")
        db.session.add(story)
        db.session.commit()
        retrieved_story = Story.query.filter_by(caption="Default published state story").first()
        self.assertIsNotNone(retrieved_story)
        self.assertFalse(retrieved_story.is_published)
        self.assertIsNone(retrieved_story.expires_at)

    # --- Route Tests for Story Scheduling ---
    def test_route_create_story_scheduled(self):
        self.login('testuser1', 'password')
        schedule_dt = datetime.now(timezone.utc) + timedelta(days=2)
        schedule_dt_str = schedule_dt.strftime('%Y-%m-%d %H:%M')

        mock_media_data = io.BytesIO(b"dummy story media content for schedule")
        mock_media_file = FileStorage(stream=mock_media_data, filename="scheduled_story.jpg", content_type="image/jpeg")

        response = self.client.post(url_for('main.create_story'), data={
            'caption': 'This is a scheduled test story via route.',
            'schedule_time': schedule_dt_str,
            'media_file': mock_media_file,
            'privacy_level': 'PUBLIC'
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your story has been scheduled', response.data)

        story = Story.query.filter_by(caption='This is a scheduled test story via route.').first()
        self.assertIsNotNone(story)
        self.assertFalse(story.is_published)
        self.assertIsNotNone(story.scheduled_for)
        self.assertIsNone(story.expires_at) # expires_at should not be set for scheduled stories
        form_dt_naive = datetime.strptime(schedule_dt_str, '%Y-%m-%d %H:%M')
        self.assertAlmostEqual(story.scheduled_for, form_dt_naive, delta=timedelta(seconds=1))
        self.logout()

    def test_route_create_story_immediate(self):
        self.login('testuser1', 'password')
        mock_media_data = io.BytesIO(b"dummy story media content immediate")
        mock_media_file = FileStorage(stream=mock_media_data, filename="immediate_story.jpg", content_type="image/jpeg")

        response = self.client.post(url_for('main.create_story'), data={
            'caption': 'This is an immediate test story via route.',
            'media_file': mock_media_file,
            'privacy_level': 'PUBLIC'
            # No schedule_time provided
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your story has been posted!', response.data)

        story = Story.query.filter_by(caption='This is an immediate test story via route.').first()
        self.assertIsNotNone(story)
        self.assertTrue(story.is_published)
        self.assertIsNone(story.scheduled_for)
        self.assertIsNotNone(story.expires_at) # Should be set by __init__
        expected_expires_at = story.timestamp + timedelta(hours=24)
        self.assertAlmostEqual(story.expires_at, expected_expires_at, delta=timedelta(seconds=10))
        self.logout()

    def test_route_create_story_schedule_time_in_past(self):
        self.login('testuser1', 'password')
        past_schedule_dt = datetime.now(timezone.utc) - timedelta(days=1)
        past_schedule_dt_str = past_schedule_dt.strftime('%Y-%m-%d %H:%M')

        mock_media_data = io.BytesIO(b"dummy story media content past")
        mock_media_file = FileStorage(stream=mock_media_data, filename="past_schedule_story.jpg", content_type="image/jpeg")

        response = self.client.post(url_for('main.create_story'), data={
            'caption': 'Test story with past schedule time.',
            'schedule_time': past_schedule_dt_str,
            'media_file': mock_media_file,
            'privacy_level': 'PUBLIC'
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200) # Form validation error should re-render the page
        self.assertIn(b'Scheduled time must be in the future.', response.data)

        story = Story.query.filter_by(caption='Test story with past schedule time.').first()
        self.assertIsNone(story)
        self.logout()


if __name__ == '__main__':
    unittest.main(verbosity=2)
