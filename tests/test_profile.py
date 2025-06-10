import unittest
import io # For simulating file uploads
from app import create_app, db
from app.models import User
from config import TestingConfig
from app.utils import save_picture # For potential mocking or direct call
import os

# Ensure the images directory exists for save_picture utility, even for tests
if not os.path.exists(os.path.join(os.path.dirname(__file__), '../app/static/images')):
    os.makedirs(os.path.join(os.path.dirname(__file__), '../app/static/images'))


class ProfileTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # Create test users
        self.user1 = User(username='user1', email='user1@example.com')
        self.user1.set_password('password123')
        self.user1.bio = "User1's original bio."

        self.user2 = User(username='user2', email='user2@example.com')
        self.user2.set_password('password456')
        self.user2.bio = "User2's bio."

        db.session.add_all([self.user1, self.user2])
        db.session.commit()

    def tearDown(self):
        # Clean up created files for profile pictures
        # This is a simplified cleanup; a more robust solution might involve a dedicated test upload folder
        image_folder = os.path.join(self.app_instance.root_path, 'static/images')
        for item in os.listdir(image_folder):
            if item != "default_profile_pic.png": # Keep the default
                try:
                    os.remove(os.path.join(image_folder, item))
                except Exception as e:
                    print(f"Error removing test file {item}: {e}")

        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # Helper method for login
    def _login(self, email, password):
        return self.app.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.app.get('/logout', follow_redirects=True)

    # --- Profile Viewing Tests ---
    def test_profile_page_loads_for_existing_user(self):
        self._login('user1@example.com', 'password123')
        response = self.app.get(f'/user/{self.user1.username}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(bytes(self.user1.username, 'utf-8'), response.data)
        self.assertIn(bytes(self.user1.bio.replace("'", "&#39;"), 'utf-8'), response.data) # Check for HTML escaped version
        self.assertIn(b'Edit Profile', response.data) # User1 viewing own profile

    def test_profile_page_404_for_nonexistent_user(self):
        self._login('user1@example.com', 'password123')
        response = self.app.get('/user/nonexistentuser')
        self.assertEqual(response.status_code, 404)

    def test_view_another_users_profile(self):
        self._login('user1@example.com', 'password123') # user1 logs in
        response = self.app.get(f'/user/{self.user2.username}') # views user2's profile
        self.assertEqual(response.status_code, 200)
        self.assertIn(bytes(self.user2.username, 'utf-8'), response.data)
        self.assertNotIn(b'Edit Profile', response.data) # User1 should not see edit link on User2's profile

    # --- Profile Editing Tests ---
    def test_edit_profile_page_loads_for_self(self):
        self._login('user1@example.com', 'password123')
        response = self.app.get('/edit_profile')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Edit Profile', response.data)
        self.assertIn(b'Bio', response.data) # Check for form field
        self.assertIn(bytes(self.user1.bio.replace("'", "&#39;"), 'utf-8'), response.data) # Check if current bio is pre-filled (escaped in textarea)

    def test_edit_profile_unauthorized_redirect(self):
        response = self.app.get('/edit_profile', follow_redirects=False) # Check redirect before it happens
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/login' in response.location) # Check it redirects to login

        response_followed = self.app.get('/edit_profile', follow_redirects=True)
        self.assertEqual(response_followed.status_code, 200) # Page after redirect
        self.assertIn(b'Sign In', response_followed.data) # Should be login page

    def test_update_bio_successful(self):
        self._login('user1@example.com', 'password123')
        new_bio = "User1's updated bio."
        response = self.app.post('/edit_profile', data=dict(
            bio=new_bio
        ), follow_redirects=True)

        self.assertEqual(response.status_code, 200) # Redirects to profile page
        self.assertIn(bytes(self.user1.username + "'s Profile", 'utf-8'), response.data) # Check it's the profile page
        self.assertIn(bytes(new_bio.replace("'", "&#39;"), 'utf-8'), response.data) # New bio should be on profile page (escaped)

        updated_user = User.query.get(self.user1.id)
        self.assertEqual(updated_user.bio, new_bio)

    def test_update_profile_picture_successful(self):
        self._login('user1@example.com', 'password123')

        # Create a minimal valid PNG (1x1 transparent)
        # base64: iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=
        import base64
        min_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        min_png_bytes = base64.b64decode(min_png_b64)
        dummy_file = io.BytesIO(min_png_bytes)

        data = {
            'bio': 'Bio during picture update.', # Bio is part of the form
            'profile_picture': (dummy_file, 'test_pic.png') # Use .png extension
        }

        response = self.app.post('/edit_profile', data=data, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200) # Should redirect to profile page
        self.assertIn(bytes(self.user1.username + "'s Profile", 'utf-8'), response.data)

        updated_user = User.query.get(self.user1.id)
        self.assertNotEqual(updated_user.profile_picture_url, 'default_profile_pic.png')
        self.assertTrue(updated_user.profile_picture_url.endswith('.png'))
        self.assertFalse(updated_user.profile_picture_url.startswith('test_pic')) # Name should be randomized

        # Check if the file was actually created (and it's not the default one)
        # This assumes save_picture places it in 'app/static/images' relative to app.root_path
        expected_pic_path = os.path.join(self.app_instance.root_path, 'static/images', updated_user.profile_picture_url)
        self.assertTrue(os.path.exists(expected_pic_path))

    # The current /edit_profile route always pertains to current_user.
    # So, a direct test for "editing another user's profile via URL manipulation" isn't applicable
    # in the same way as if the URL contained the username to be edited.
    # The protection is that you can only GET/POST to /edit_profile for yourself.
    # test_view_another_users_profile already checks that the "Edit Profile" link isn't there.

if __name__ == '__main__':
    unittest.main()
