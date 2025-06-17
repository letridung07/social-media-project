import unittest
import os
import io
from flask import current_app, get_flashed_messages
from app import create_app, db
from app.core.models import User, AudioPost
from config import TestingConfig
from werkzeug.datastructures import FileStorage
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

class AudioPostTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create test users
        self.user1 = User(username='audiouser1', email='audio1@example.com')
        self.user1.set_password('password')
        self.user2 = User(username='audiouser2', email='audio2@example.com')
        self.user2.set_password('password')
        db.session.add_all([self.user1, self.user2])
        db.session.commit()

        # Setup test upload folder
        # Ensure TestingConfig.AUDIO_UPLOAD_FOLDER is set, e.g., 'app/static/audio_test_uploads'
        # The actual folder name for URL generation is AUDIO_UPLOAD_FOLDER_NAME
        self.audio_upload_folder_name = current_app.config.get('AUDIO_UPLOAD_FOLDER_NAME', 'audio_test_uploads')
        base_static_dir = current_app.config.get('MEDIA_UPLOAD_BASE_DIR', 'static')
        self.audio_upload_path = os.path.join(current_app.root_path, base_static_dir, self.audio_upload_folder_name)

        os.makedirs(self.audio_upload_path, exist_ok=True)

        # Mock get_audio_duration
        self.mock_get_duration = patch('app.utils.helpers.get_audio_duration', MagicMock(return_value=180))
        self.mocked_get_duration = self.mock_get_duration.start()

    def tearDown(self):
        self.mock_get_duration.stop()
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

        # Clean up test audio upload directory
        if os.path.exists(self.audio_upload_path):
            for f in os.listdir(self.audio_upload_path):
                try:
                    os.remove(os.path.join(self.audio_upload_path, f))
                except OSError:
                    pass
            if not os.listdir(self.audio_upload_path): # Only remove if empty
                try:
                    os.rmdir(self.audio_upload_path)
                except OSError:
                     current_app.logger.warning(f"Could not remove test audio dir {self.audio_upload_path}")


    def _login(self, email, password):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def _create_db_audio_post(self, title, description, user, audio_filename="test.mp3", duration=180, timestamp=None):
        """Helper to create an audio post directly in the DB for test setup."""
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Create a dummy file in the test upload path for consistency if needed for deletion tests
        dummy_file_path = os.path.join(self.audio_upload_path, audio_filename)
        with open(dummy_file_path, 'wb') as f:
            f.write(b"dummy audio content for " + audio_filename.encode())

        audio_post = AudioPost(title=title, description=description, uploader=user,
                               audio_filename=audio_filename, duration=duration, timestamp=timestamp)
        db.session.add(audio_post)
        db.session.commit()
        return audio_post

    def test_upload_audio_post(self):
        # Success Case (Logged In)
        self._login('audio1@example.com', 'password')
        audio_data = io.BytesIO(b"dummy mp3 data")
        mock_audio_file = FileStorage(stream=audio_data, filename='test_upload.mp3', content_type='audio/mpeg')

        response = self.client.post('/audio/upload', data={
            'title': 'My Test Audio',
            'description': 'A description of my test audio.',
            'audio_file': mock_audio_file
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        # Check for flash message using get_flashed_messages
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
        self.assertTrue(any('Audio post uploaded successfully!' in message[1] for message in flashes))

        audio_post = AudioPost.query.filter_by(title='My Test Audio').first()
        self.assertIsNotNone(audio_post)
        self.assertEqual(audio_post.uploader, self.user1)
        self.assertEqual(audio_post.description, 'A description of my test audio.')
        self.assertTrue(audio_post.audio_filename.endswith('.mp3'))
        self.assertEqual(audio_post.duration, 180) # From mocked get_audio_duration
        self.assertTrue(os.path.exists(os.path.join(self.audio_upload_path, audio_post.audio_filename)))
        self.assertTrue(f'/audio/{audio_post.id}' in response.request.path) # Check redirection
        self._logout()

        # Not Logged In
        response_not_logged_in = self.client.post('/audio/upload', data={'title': 'Guest Audio'}, follow_redirects=True)
        self.assertTrue(response_not_logged_in.request.path.startswith('/login'))

        # Invalid Data (Missing Title)
        self._login('audio1@example.com', 'password')
        audio_data_no_title = io.BytesIO(b"more dummy data")
        mock_audio_no_title = FileStorage(stream=audio_data_no_title, filename='no_title.mp3', content_type='audio/mpeg')
        response_invalid_title = self.client.post('/audio/upload', data={
            'title': '', 'description': 'Valid desc.', 'audio_file': mock_audio_no_title
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response_invalid_title.status_code, 200) # Re-renders form
        self.assertIn(b'This field is required.', response_invalid_title.data)
        self.assertIsNone(AudioPost.query.filter_by(description='Valid desc.').first())

        # Invalid Data (Missing File)
        response_invalid_file = self.client.post('/audio/upload', data={
            'title': 'Valid Title No File', 'description': 'Desc here'
            # Missing audio_file
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response_invalid_file.status_code, 200)
        self.assertIn(b'This field is required.', response_invalid_file.data) # Error for audio_file

        # Invalid File Type
        txt_data = io.BytesIO(b"not audio")
        mock_txt_file = FileStorage(stream=txt_data, filename='test.txt', content_type='text/plain')
        response_invalid_type = self.client.post('/audio/upload', data={
            'title': 'Text File Upload', 'audio_file': mock_txt_file
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response_invalid_type.status_code, 200)
        self.assertIn(b'Audio files only!', response_invalid_type.data)
        self._logout()

    def test_view_audio_post(self):
        audio = self._create_db_audio_post('View Test Audio', 'Audio body here.', self.user1, audio_filename="view.mp3")

        response = self.client.get(f'/audio/{audio.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'View Test Audio', response.data)
        self.assertIn(b'Audio body here.', response.data)
        self.assertIn(self.user1.username.encode(), response.data)
        self.assertIn(b'180', response.data) # Duration
        self.assertIn(b'<audio controls', response.data)
        expected_src = f'src="/static/{self.audio_upload_folder_name}/view.mp3"'
        self.assertIn(expected_src.encode(), response.data)

        response_404 = self.client.get('/audio/99999')
        self.assertEqual(response_404.status_code, 404)

    def test_edit_audio_post_metadata(self):
        audio = self._create_db_audio_post('Original Audio Title', 'Original audio description.', self.user1)
        original_filename = audio.audio_filename
        original_duration = audio.duration

        # Success Case (Uploader Logged In - metadata only)
        self._login('audio1@example.com', 'password')
        response_edit = self.client.post(f'/audio/{audio.id}/edit', data={
            'title': 'Updated Audio Title',
            'description': 'Updated audio description.'
            # No audio_file, testing metadata edit
        }, follow_redirects=True)
        self.assertEqual(response_edit.status_code, 200)
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
        self.assertTrue(any('Audio post updated successfully!' in message[1] for message in flashes))

        updated_audio = AudioPost.query.get(audio.id)
        self.assertEqual(updated_audio.title, 'Updated Audio Title')
        self.assertEqual(updated_audio.description, 'Updated audio description.')
        self.assertEqual(updated_audio.audio_filename, original_filename) # Filename unchanged
        self.assertEqual(updated_audio.duration, original_duration) # Duration unchanged
        self.assertTrue(f'/audio/{audio.id}' in response_edit.request.path)
        self._logout()

        # Unauthorized (Different User)
        self._login('audio2@example.com', 'password')
        response_unauth = self.client.post(f'/audio/{audio.id}/edit', data={'title': 'Hack Attempt'}, follow_redirects=True)
        self.assertEqual(response_unauth.status_code, 403)
        db.session.refresh(updated_audio) # Re-fetch from DB
        self.assertEqual(updated_audio.title, 'Updated Audio Title') # Should not have changed
        self._logout()

        # Unauthorized (Not Logged In)
        response_guest = self.client.post(f'/audio/{audio.id}/edit', data={'title': 'Guest Edit'}, follow_redirects=True)
        self.assertTrue(response_guest.request.path.startswith('/login'))

    def test_delete_audio_post(self):
        audio_to_delete = self._create_db_audio_post('Audio For Deletion', 'Delete me.', self.user1, audio_filename="delete_me.mp3")
        audio_id = audio_to_delete.id
        audio_filename_on_disk = audio_to_delete.audio_filename
        # Ensure the dummy file exists for deletion test
        self.assertTrue(os.path.exists(os.path.join(self.audio_upload_path, audio_filename_on_disk)))

        # Unauthorized (Different User)
        self._login('audio2@example.com', 'password')
        response_unauth_del = self.client.post(f'/audio/{audio_id}/delete', follow_redirects=True)
        self.assertEqual(response_unauth_del.status_code, 403)
        self.assertIsNotNone(AudioPost.query.get(audio_id))
        self.assertTrue(os.path.exists(os.path.join(self.audio_upload_path, audio_filename_on_disk))) # File still there
        self._logout()

        # Success Case (Uploader Logged In)
        self._login('audio1@example.com', 'password')
        response_del = self.client.post(f'/audio/{audio_id}/delete', follow_redirects=True)
        self.assertEqual(response_del.status_code, 200)
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
        self.assertTrue(any('Audio post deleted successfully!' in message[1] for message in flashes))

        self.assertIsNone(AudioPost.query.get(audio_id))
        self.assertFalse(os.path.exists(os.path.join(self.audio_upload_path, audio_filename_on_disk))) # File deleted
        self.assertTrue('/audio/list' in response_del.request.path)
        self._logout()

    def test_list_all_audio_posts(self):
        self._create_db_audio_post('Audio Alpha', 'Content A', self.user1, timestamp=datetime.utcnow() - timedelta(days=1))
        self._create_db_audio_post('Audio Beta', 'Content B', self.user2, timestamp=datetime.utcnow())

        response = self.client.get('/audio/list')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Audio Alpha', response.data)
        self.assertIn(b'Audio Beta', response.data)
        self.assertIn(self.user1.username.encode(), response.data)
        self.assertIn(self.user2.username.encode(), response.data)

        # Test Pagination
        for i in range(12): # Create 12 more, total 14
            self._create_db_audio_post(f'Paged Audio {i}', f'Body {i}', self.user1, audio_filename=f'paged_audio_{i}.mp3')

        response_page1 = self.client.get('/audio/list')
        self.assertIn(b'Paged Audio 11', response_page1.data) # Newest of the 12
        self.assertNotIn(b'Audio Alpha', response_page1.data) # Assuming 10 per page, this old one is on page 2
        self.assertIn(b'Next', response_page1.data)

        response_page2 = self.client.get('/audio/list?page=2')
        self.assertNotIn(b'Paged Audio 11', response_page2.data)
        self.assertIn(b'Audio Alpha', response_page2.data)
        self.assertIn(b'Previous', response_page2.data)

    def test_list_user_audio_posts(self):
        self._create_db_audio_post('User1 Audio 1', 'U1A1', self.user1, audio_filename="u1a1.mp3", timestamp=datetime.utcnow() - timedelta(seconds=10))
        self._create_db_audio_post('User1 Audio 2', 'U1A2', self.user1, audio_filename="u1a2.mp3")
        self._create_db_audio_post('User2 Audio 1', 'U2A1', self.user2, audio_filename="u2a1.mp3")

        response = self.client.get(f'/user/{self.user1.username}/audio')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User1 Audio 1', response.data)
        self.assertIn(b'User1 Audio 2', response.data)
        self.assertIn(f'Audio Posts by {self.user1.username}'.encode(), response.data)
        self.assertNotIn(b'User2 Audio 1', response.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
