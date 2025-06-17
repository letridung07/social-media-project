import unittest
from flask import url_for # Added for redirect checks
from app import create_app, db
from app.core.models import User
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
        self.assertIn(bytes(f'Hi, {self.test_user_username}!', 'utf-8'), login_response.data) # Updated
        self.assertNotIn(b'Welcome to My Flask App!', login_response.data)
        self.assertNotIn(bytes(f'Hello, {self.test_user_username}!', 'utf-8'), login_response.data)

        # Access a protected-ish route (profile page of the logged-in user)
        profile_response = self.app.get(f'/user/{self.test_user_username}')
        self.assertEqual(profile_response.status_code, 200)
        self.assertIn(bytes(f"{self.test_user_username}'s Profile", 'utf-8'), profile_response.data)
        self.assertIn(b'My Profile', profile_response.data) # Check for nav link only visible when logged in

        # Logout
        logout_response = self._logout_user()
        self.assertEqual(logout_response.status_code, 200) # Redirects to index
        self.assertIn(b'Hi, Guest!', logout_response.data) # Updated
        self.assertNotIn(b'Welcome to My Flask App!', logout_response.data)
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

    # --- Password Reset Flow Tests ---
    def test_forgot_password_request_success(self):
        # Register a user
        self._register_user(self.test_user_username, self.test_user_email, self.test_user_password)

        response = self.app.post('/forgot_password', data=dict(
            email=self.test_user_email
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to login
        self.assertIn(b'Sign In', response.data) # Back on login page
        # Check for one of the possible success messages based on app's behavior
        self.assertTrue(
            b'An email has been sent with instructions to reset your password.' in response.data or
            b'If an account with that email exists, instructions to reset your password have been sent.' in response.data
        )

    def test_forgot_password_request_nonexistent_email(self):
        response = self.app.post('/forgot_password', data=dict(
            email='nonexistent@example.com'
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to login
        self.assertIn(b'Sign In', response.data) # Back on login page
        # Should show the generic message for security (doesn't reveal if email exists)
        self.assertIn(b'If an account with that email exists, instructions to reset your password have been sent.', response.data)

    def test_reset_password_with_valid_token(self):
        # Register user
        self._register_user(self.test_user_username, self.test_user_email, self.test_user_password)
        user = User.query.filter_by(email=self.test_user_email).first()
        self.assertIsNotNone(user)

        token = user.get_reset_password_token()
        self.assertIsNotNone(token)

        # GET the reset password page
        response_get = self.app.get(f'/reset_password/{token}')
        self.assertEqual(response_get.status_code, 200)
        self.assertIn(b'Reset Password', response_get.data) # Check for page title or specific form elements

        # POST new password
        new_password = 'newpassword123'
        response_post = self.app.post(f'/reset_password/{token}', data=dict(
            password=new_password,
            confirm_password=new_password
        ), follow_redirects=True)
        self.assertEqual(response_post.status_code, 200) # Redirects to login
        self.assertIn(b'Your password has been updated!', response_post.data)
        self.assertIn(b'Sign In', response_post.data)

        # Attempt login with new password
        login_response_new_pw = self._login_user(self.test_user_email, new_password)
        self.assertEqual(login_response_new_pw.status_code, 200)
        self.assertIn(bytes(f'Hi, {self.test_user_username}!', 'utf-8'), login_response_new_pw.data)

        # Attempt login with old password (should fail)
        self._logout_user() # Logout first
        login_response_old_pw = self._login_user(self.test_user_email, self.test_user_password)
        self.assertEqual(login_response_old_pw.status_code, 200) # Stays on login page
        self.assertIn(b'Login Unsuccessful. Please check email and password', login_response_old_pw.data)

    def test_reset_password_with_invalid_token(self):
        new_password = 'newpassword123'
        # POST to reset password with an invalid token
        response_post = self.app.post('/reset_password/invalidtoken123', data=dict(
            password=new_password,
            confirm_password=new_password
        ), follow_redirects=True)
        self.assertEqual(response_post.status_code, 200) # Redirects to forgot_password
        self.assertIn(b'That is an invalid or expired token.', response_post.data)
        self.assertIn(b'Forgot Password', response_post.data) # Check if on forgot password page

    def test_reset_password_with_expired_token(self):
        import time # Ensure time is imported at top of file or here
        # Register user
        self._register_user(self.test_user_username, self.test_user_email, self.test_user_password)
        user = User.query.filter_by(email=self.test_user_email).first()
        self.assertIsNotNone(user)

        # Generate token with short expiry (1 second)
        token = user.get_reset_password_token(expires_sec=1)
        self.assertIsNotNone(token)

        # Wait for token to expire
        time.sleep(2)

        new_password = 'newpassword123'
        # POST new password with expired token
        response_post = self.app.post(f'/reset_password/{token}', data=dict(
            password=new_password,
            confirm_password=new_password
        ), follow_redirects=True)
        self.assertEqual(response_post.status_code, 200) # Redirects to forgot_password
        self.assertIn(b'That is an invalid or expired token.', response_post.data)
        self.assertIn(b'Forgot Password', response_post.data) # Check if on forgot password page

    # --- Admin Authorization Tests ---
    def test_admin_route_access_as_non_admin(self):
        self._register_user(self.test_user_username, self.test_user_email, self.test_user_password)
        self._login_user(self.test_user_email, self.test_user_password)

        response = self.app.get('/admin/virtual_goods', follow_redirects=True)
        # Non-admins are often redirected to index or a generic error page.
        # The flash message is key. Status code might be 200 if redirected to a page that exists.
        self.assertIn(b'You do not have permission to access this page.', response.data)
        # Check that we are NOT on an admin page (e.g., check for content NOT present, or if redirected to index)
        self.assertNotIn(b'Admin Dashboard - Virtual Goods', response.data)
        # Check if redirected to index or a known non-admin page
        # This depends on how @admin_required decorator handles unauthorized access.
        # Assuming it redirects to index and flashes a message.
        self.assertTrue(b'Welcome to Your App' in response.data or b'Hi, testuser!' in response.data)


    def test_admin_route_access_as_admin(self):
        # Register user
        self._register_user(self.test_user_username, "admin@example.com", self.test_user_password)

        # Promote user to admin
        admin_user = User.query.filter_by(email="admin@example.com").first()
        self.assertIsNotNone(admin_user)
        admin_user.is_admin = True
        db.session.commit()

        # Login as admin
        self._login_user("admin@example.com", self.test_user_password)

        response = self.app.get('/admin/virtual_goods', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Dashboard - Virtual Goods', response.data) # Check for admin-specific content

    def test_admin_route_access_as_anonymous(self):
        response = self.app.get('/admin/virtual_goods', follow_redirects=False) # Don't follow, check redirect location
        self.assertEqual(response.status_code, 302) # Expect redirect to login
        self.assertTrue(response.location.endswith(url_for('main.login', next='/admin/virtual_goods')))

        # Optionally, follow redirect and check login page content
        response_followed = self.app.get('/admin/virtual_goods', follow_redirects=True)
        self.assertEqual(response_followed.status_code, 200) # Login page loads
        self.assertIn(b'Sign In', response_followed.data)
        self.assertIn(b'You must be logged in to access this page.', response_followed.data)


    # --- Access to Protected Routes by Anonymous User ---
    def test_protected_route_access_as_anonymous(self):
        response = self.app.get('/edit_profile', follow_redirects=False) # Accessing a @login_required route
        self.assertEqual(response.status_code, 302) # Expect redirect
        # Check if the redirect location is the login page
        # The 'next' parameter should point back to '/edit_profile'
        self.assertTrue(response.location.endswith(url_for('main.login', next='/edit_profile')))

        # Follow redirect to ensure login page is rendered with flash message
        response_followed = self.app.get('/edit_profile', follow_redirects=True)
        self.assertEqual(response_followed.status_code, 200) # Login page should load
        self.assertIn(b'Sign In', response_followed.data) # Check for login page content
        self.assertIn(b'You must be logged in to access this page.', response_followed.data)


if __name__ == '__main__':
    unittest.main()
