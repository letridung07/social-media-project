# tests/test_posts.py
import unittest
import os
import io # For creating mock files
from flask import current_app
from app import create_app, db
from app.models import User, Post
from config import TestingConfig # Using TestingConfig for tests
from werkzeug.datastructures import FileStorage # For creating mock FileStorage object
from datetime import datetime, timedelta

class PostModelCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create a test user
        self.user1 = User(username='john', email='john@example.com')
        self.user1.set_password('cat')
        db.session.add(self.user1)
        db.session.commit()

        # Path for post images - ensure it's cleaned up
        self.post_images_path = os.path.join(current_app.root_path, current_app.config['POST_IMAGES_UPLOAD_FOLDER'])


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

        # Clean up post_images directory
        if os.path.exists(self.post_images_path):
            for f in os.listdir(self.post_images_path):
                os.remove(os.path.join(self.post_images_path, f))
            if not os.listdir(self.post_images_path): # Only remove if empty after deleting files
                 os.rmdir(self.post_images_path)
            elif os.path.isdir(self.post_images_path) and not os.listdir(self.post_images_path): # Check again if it became empty
                 os.rmdir(self.post_images_path)


    def _login(self, email, password):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_create_text_only_post(self): # Explicitly for text-only
        self._login('john@example.com', 'cat')
        response = self.client.post('/create_post', data={'body': 'This is a text-only post!'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        post = Post.query.filter_by(body='This is a text-only post!').first()
        self.assertIsNotNone(post)
        self.assertIsNone(post.image_filename) # Ensure no image

        # Check if the post appears on the index page (where redirect goes)
        self.assertIn(b'This is a text-only post!', response.data)
        self.assertNotIn(b'<img src=', response.data) # No image tag

        # Check profile page as well
        response_profile = self.client.get(f'/user/{self.user1.username}')
        self.assertIn(b'This is a text-only post!', response_profile.data)
        self.assertNotIn(b'<img src=', response_profile.data)
        self._logout()

    def test_create_post_with_image(self):
        self._login('john@example.com', 'cat')

        # Create a mock image file
        mock_image_data = io.BytesIO(b"dummy image data for a fake png")
        mock_file = FileStorage(stream=mock_image_data, filename="test_image.png", content_type="image/png")

        post_body_text = "This is a post with an image!"
        response = self.client.post('/create_post', data={
            'body': post_body_text,
            'image_file': mock_file
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your post is now live!', response.data)

        post = Post.query.filter_by(body=post_body_text).first()
        self.assertIsNotNone(post)
        self.assertIsNotNone(post.image_filename) # Check filename is stored

        # Verify image file exists
        expected_image_path = os.path.join(self.post_images_path, post.image_filename)
        self.assertTrue(os.path.exists(expected_image_path))

        # Verify image is displayed on index page (where redirect goes)
        self.assertIn(f'<img src="/static/post_images/{post.image_filename}"'.encode(), response.data)
        self.assertIn(post_body_text.encode(), response.data)

        self._logout()

    def test_create_post_with_invalid_file_type(self):
        self._login('john@example.com', 'cat')

        # Ensure post_images_path exists for listdir, or create it if it might not
        if not os.path.exists(self.post_images_path):
            os.makedirs(self.post_images_path)

        mock_invalid_file_data = io.BytesIO(b"this is not an image")
        mock_file = FileStorage(stream=mock_invalid_file_data, filename="test.txt", content_type="text/plain")

        response = self.client.post('/create_post', data={
            'body': 'Trying to upload a text file.',
            'image_file': mock_file
        }, content_type='multipart/form-data', follow_redirects=True) # Test with follow_redirects=False first if issues with form error display

        self.assertEqual(response.status_code, 200)
        # Assuming FileAllowed validator stops processing before route attempts to save file,
        # and re-renders the 'create_post.html' page with the form error.
        # The create_post.html template needs to display form.image_file.errors for this to be visible.
        # For now, we'll check for the flash message that the route *would* produce if an error happened during save_post_image
        # OR we check that the post wasn't created.
        # The FileAllowed validator error should be displayed by the form rendering logic.
        # If create_post.html doesn't render form.image_file.errors, this specific assertIn might fail.
        # However, the core logic is that the post should not be created with an invalid file.
        self.assertIn(b'Images only!', response.data) # This expects the error to be in the response data

        post = Post.query.filter_by(body='Trying to upload a text file.').first()
        self.assertIsNone(post) # Post should not be created

        # Check that no files were saved to post_images
        self.assertEqual(len(os.listdir(self.post_images_path)), 0, "A file was saved despite invalid type")

        self._logout()

    def test_view_posts_on_profile_and_index(self):
        # Create posts for user1
        p1 = Post(body='Post 1 by John', author=self.user1, timestamp=datetime.utcnow() + timedelta(seconds=1))
        p2 = Post(body='Post 2 by John', author=self.user1, timestamp=datetime.utcnow() + timedelta(seconds=2))
        db.session.add_all([p1, p2])

        # Create another user and their post
        user2 = User(username='susan', email='susan@example.com')
        user2.set_password('dog')
        db.session.add(user2)
        db.session.commit() # Commit user2 first
        p3 = Post(body='Post by Susan', author=user2, timestamp=datetime.utcnow() + timedelta(seconds=3))
        db.session.add(p3)
        db.session.commit()

        # Test John's profile page
        response_john_profile = self.client.get(f'/user/{self.user1.username}')
        self.assertIn(b'Post 1 by John', response_john_profile.data)
        self.assertIn(b'Post 2 by John', response_john_profile.data)
        self.assertNotIn(b'Post by Susan', response_john_profile.data)

        # Test Susan's profile page
        response_susan_profile = self.client.get(f'/user/{user2.username}')
        self.assertIn(b'Post by Susan', response_susan_profile.data)
        self.assertNotIn(b'Post 1 by John', response_susan_profile.data)

        # Test index page (should show all posts)
        # Login to see create post link, though posts are visible without login
        self._login('john@example.com', 'cat')
        response_index = self.client.get('/')
        self.assertIn(b'Post 1 by John', response_index.data)
        self.assertIn(b'Post 2 by John', response_index.data)
        self.assertNotIn(b'Post by Susan', response_index.data) # John is not following Susan
        self.assertIn(b'john', response_index.data) # Author username
        # self.assertIn(b'susan', response_index.data) # Susan's username should not be on John's feed if not followed
        self._logout()

    def test_create_post_requires_login(self):
        response = self.client.get('/create_post', follow_redirects=True)
        # Should redirect to login page
        self.assertTrue(response.request.path.startswith('/login')) # Check redirection path

        response_post = self.client.post('/create_post', data={
            'body': 'Trying to post without login'
        }, follow_redirects=True)
        self.assertTrue(response_post.request.path.startswith('/login'))

        post = Post.query.filter_by(body='Trying to post without login').first()
        self.assertIsNone(post)

if __name__ == '__main__':
    unittest.main(verbosity=2)
