import unittest
from app import create_app, db
from app.models import User
from config import TestingConfig # Import TestingConfig

class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig) # Pass TestingConfig to create_app
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # Helper to register a user quickly
        self.test_user_username = 'testuser'
        self.test_user_email = 'test@example.com'
        self.test_user_password = 'password123'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _register_user(self, username, email, password, confirm_password=None):
        if confirm_password is None:
            confirm_password = password
        return self.app.post('/register', data=dict(
            username=username,
            email=email,
            password=password,
            confirm_password=confirm_password
        ), follow_redirects=True)

    def _login_user(self, email, password):
        return self.app.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout_user(self):
        return self.app.get('/logout', follow_redirects=True)

    # --- Registration Tests ---
    def test_successful_registration(self):
        response = self._register_user(self.test_user_username, self.test_user_email, self.test_user_password)
        self.assertEqual(response.status_code, 200) # Should redirect to login, then login shows 200
        self.assertIn(b'Sign In', response.data) # Check if redirected to the actual login page content
        self.assertIn(b'Congratulations, you are now a registered user!', response.data) # Check for flash message

        user = User.query.filter_by(email=self.test_user_email).first()
        self.assertIsNotNone(user)
        self.assertEqual(user.username, self.test_user_username)
        self.assertTrue(user.check_password(self.test_user_password))
        # Check for flash message (more complex, can be done by checking for specific HTML)
        # For simplicity, we'll check if the redirect target (login page) loads
        # response_login_page = self.app.get('/login')
        # self.assertIn(b'Congratulations, you are now a registered user!', response_login_page.data) # This requires flash message to be rendered on login page after redirect

    def test_registration_page_loads(self):
        response = self.app.get('/register')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Register', response.data)

    def test_registration_existing_username(self):
        self._register_user(self.test_user_username, 'another@example.com', self.test_user_password) # First user
        initial_user_count = User.query.count()

        response = self._register_user(self.test_user_username, self.test_user_email, 'anotherpassword')
        self.assertEqual(response.status_code, 200) # Stays on registration page
        self.assertIn(b'That username is taken.', response.data)
        self.assertEqual(User.query.count(), initial_user_count)

    def test_registration_existing_email(self):
        self._register_user('anotheruser', self.test_user_email, self.test_user_password) # First user
        initial_user_count = User.query.count()

        response = self._register_user(self.test_user_username, self.test_user_email, 'anotherpassword')
        self.assertEqual(response.status_code, 200) # Stays on registration page
        self.assertIn(b'That email is already in use.', response.data)
        self.assertEqual(User.query.count(), initial_user_count)

    def test_registration_mismatched_passwords(self):
        response = self._register_user(self.test_user_username, self.test_user_email, self.test_user_password, 'wrongpassword')
        self.assertEqual(response.status_code, 200) # Stays on registration page
        self.assertIn(b'Field must be equal to password.', response.data) # Default WTForms error
        self.assertIsNone(User.query.filter_by(email=self.test_user_email).first())

    # --- Login and Logout Tests ---
    def test_login_page_loads(self):
        response = self.app.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sign In', response.data) # From login.html

    def test_successful_login_logout(self):
        # Register user first
        self._register_user(self.test_user_username, self.test_user_email, self.test_user_password)

        # Login
        login_response = self._login_user(self.test_user_email, self.test_user_password)
        self.assertEqual(login_response.status_code, 200) # Redirects to index
        self.assertIn(b'Welcome to My Flask App!', login_response.data) # Check for index page content
        self.assertIn(bytes(f'Hello, {self.test_user_username}!', 'utf-8'), login_response.data)

        # Access a protected-ish route (profile page of the logged-in user)
        profile_response = self.app.get(f'/user/{self.test_user_username}')
        self.assertEqual(profile_response.status_code, 200)
        self.assertIn(bytes(f"{self.test_user_username}'s Profile", 'utf-8'), profile_response.data)
        self.assertIn(b'My Profile', profile_response.data) # Check for nav link only visible when logged in

        # Logout
        logout_response = self._logout_user()
        self.assertEqual(logout_response.status_code, 200) # Redirects to index
        self.assertIn(b'Welcome to My Flask App!', logout_response.data) # Check for index page content
        self.assertIn(b'Login', logout_response.data) # Nav link changes to Login
        self.assertNotIn(b'My Profile', logout_response.data)


        # Try to access profile page again (should still be public, but nav changes)
        profile_response_after_logout = self.app.get(f'/user/{self.test_user_username}')
        self.assertEqual(profile_response_after_logout.status_code, 200)
        self.assertIn(b'Login', profile_response_after_logout.data) # Nav link should be Login
        self.assertNotIn(b'My Profile', profile_response_after_logout.data)


    def test_login_incorrect_password(self):
        self._register_user(self.test_user_username, self.test_user_email, self.test_user_password)

        response = self._login_user(self.test_user_email, 'wrongpassword')
        self.assertEqual(response.status_code, 200) # Stays on login page
        self.assertIn(b'Login Unsuccessful. Please check email and password', response.data)
        self.assertIn(b'Sign In', response.data) # Still on login page

    def test_login_nonexistent_user(self):
        response = self._login_user('nonexistent@example.com', 'anypassword')
        self.assertEqual(response.status_code, 200) # Stays on login page
        self.assertIn(b'Login Unsuccessful. Please check email and password', response.data)
        self.assertIn(b'Sign In', response.data) # Still on login page

if __name__ == '__main__':
    unittest.main()
