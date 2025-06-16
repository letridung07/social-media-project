import unittest
from app import create_app, db
from app.models import User
from app.forms import TOTPSetupForm, Verify2FAForm, Disable2FAForm, ConfirmPasswordAndTOTPForm
from unittest.mock import patch, MagicMock
import pyotp
import json
from passlib.hash import sha256_crypt # For checking backup codes
from flask import session, url_for, current_app
import secrets

class TwoFATestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create a test user
        self.user = User(username='testuser', email='test@example.com', otp_enabled=False)
        self.user.set_password('password123')
        db.session.add(self.user)
        db.session.commit()

        # Login the user for tests that require an authenticated session
        with self.client: # Use context manager for session consistency
            self.client.post(url_for('main.login'), data={
                'email': 'test@example.com',
                'password': 'password123'
            }, follow_redirects=True)

    def tearDown(self):
        with self.client: # Use context manager for session consistency
             self.client.get(url_for('main.logout')) # Logout to clear session
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_01_2fa_setup_get_page(self):
        # Assumes user is logged in from setUp
        response = self.client.get(url_for('main.setup_2fa'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Setup Two-Factor Authentication', response.data)
        self.assertIn(b'QR Code', response.data)
        self.assertIn(b'Secret Key', response.data)
        self.assertIn(b'Backup Codes', response.data)
        self.assertTrue(session.get('otp_secret_temp') is not None)
        self.assertTrue(session.get('backup_codes_temp') is not None)

    @patch('pyotp.TOTP')
    def test_02_2fa_setup_post_enable_2fa_correct_code(self, mock_totp):
        # Mock the TOTP verification
        mock_totp_instance = mock_totp.return_value
        mock_totp_instance.verify.return_value = True

        temp_secret = pyotp.random_base32()
        temp_backup_codes = [secrets.token_hex(8) for _ in range(10)]

        with self.client: # Ensure session is active
            # Manually set session variables as if GET request happened
            with self.client.session_transaction() as sess:
                sess['otp_secret_temp'] = temp_secret
                sess['backup_codes_temp'] = temp_backup_codes

            mock_totp.return_value.secret = temp_secret # Ensure the mocked TOTP uses our temp secret

            response = self.client.post(url_for('main.setup_2fa'), data={
                'totp_code': '123456' # Validated by mock
            }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Two-factor authentication enabled successfully!', response.data)

        user = User.query.get(self.user.id)
        self.assertTrue(user.otp_enabled)
        self.assertEqual(user.otp_secret, temp_secret)
        self.assertIsNotNone(user.otp_backup_codes)

        hashed_codes_stored = json.loads(user.otp_backup_codes)
        self.assertEqual(len(hashed_codes_stored), 10)
        # Cannot directly verify unhashed codes against stored hashed ones without hashing them here too
        # but we trust they were hashed correctly.

        # Check session variables are cleared
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('otp_secret_temp'))
            self.assertIsNone(sess.get('backup_codes_temp'))

    @patch('pyotp.TOTP')
    def test_03_2fa_setup_post_enable_2fa_incorrect_code(self, mock_totp):
        mock_totp_instance = mock_totp.return_value
        mock_totp_instance.verify.return_value = False # Simulate incorrect code

        temp_secret = pyotp.random_base32()
        temp_backup_codes = [secrets.token_hex(8) for _ in range(10)]

        with self.client:
            with self.client.session_transaction() as sess:
                sess['otp_secret_temp'] = temp_secret
                sess['backup_codes_temp'] = temp_backup_codes

            mock_totp.return_value.secret = temp_secret

            response = self.client.post(url_for('main.setup_2fa'), data={'totp_code': '654321'}, follow_redirects=True)

        self.assertEqual(response.status_code, 200) # Re-renders setup page
        self.assertIn(b'Invalid authenticator code. Please try again.', response.data)
        user = User.query.get(self.user.id)
        self.assertFalse(user.otp_enabled)
        self.assertIsNone(user.otp_secret) # Not saved on failure

        # Session variables should persist for retry
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('otp_secret_temp'), temp_secret)

    def test_04_login_without_2fa(self):
        # Ensure user has 2FA disabled
        self.user.otp_enabled = False
        db.session.commit()

        with self.client:
            self.client.get(url_for('main.logout')) # Ensure logged out
            response = self.client.post(url_for('main.login'), data={
                'email': 'test@example.com',
                'password': 'password123'
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Logout', response.data) # Check for logout link, indicating successful login
            self.assertNotIn(b'Verify Two-Factor Authentication', response.data) # Should not go to 2FA page

    def test_05_login_with_2fa_enabled_redirects_to_verify(self):
        # Enable 2FA for the user first (simplified setup for this test)
        self.user.otp_enabled = True
        self.user.otp_secret = pyotp.random_base32() # Needs a secret to pass login check
        db.session.commit()

        with self.client:
            self.client.get(url_for('main.logout'))
            response = self.client.post(url_for('main.login'), data={
                'email': 'test@example.com',
                'password': 'password123'
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Verify Two-Factor Authentication', response.data) # Check we are on 2FA verify page
            with self.client.session_transaction() as sess:
                self.assertEqual(sess.get('user_id_for_2fa'), self.user.id)

    @patch('pyotp.TOTP')
    def test_06_2fa_verify_correct_totp_code(self, mock_totp):
        # Enable 2FA for user and set secret
        secret = pyotp.random_base32()
        self.user.otp_enabled = True
        self.user.otp_secret = secret
        db.session.commit()

        mock_totp_instance = mock_totp.return_value
        mock_totp_instance.verify.return_value = True # Simulate correct code

        with self.client:
            # Simulate the first part of login
            with self.client.session_transaction() as sess:
                sess['user_id_for_2fa'] = self.user.id
                sess['remember_me_for_2fa'] = False

            mock_totp.return_value.secret = secret # Ensure mock uses the correct secret

            response = self.client.post(url_for('main.verify_2fa'), data={'code': '123456'}, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Successfully logged in.', response.data)
        self.assertIn(b'Logout', response.data) # Check for logout link
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('user_id_for_2fa')) # Session var should be cleared

    def test_07_2fa_verify_correct_backup_code(self):
        secret = pyotp.random_base32()
        unhashed_backup_codes = [secrets.token_hex(8) for _ in range(3)]
        hashed_backup_codes = [sha256_crypt.hash(code) for code in unhashed_backup_codes]

        self.user.otp_enabled = True
        self.user.otp_secret = secret
        self.user.otp_backup_codes = json.dumps(hashed_backup_codes)
        db.session.commit()

        with self.client:
            with self.client.session_transaction() as sess:
                sess['user_id_for_2fa'] = self.user.id

            # Use the first unhashed backup code for login
            response = self.client.post(url_for('main.verify_2fa'), data={'code': unhashed_backup_codes[0]}, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Successfully logged in.', response.data)
        self.assertIn(b'Backup code used.', response.data) # Flash message for backup code usage

        user_reloaded = User.query.get(self.user.id)
        remaining_codes_stored = json.loads(user_reloaded.otp_backup_codes)
        self.assertEqual(len(remaining_codes_stored), len(unhashed_backup_codes) - 1)
        # Verify that the used code is no longer among the stored hashed codes
        self.assertFalse(sha256_crypt.verify(unhashed_backup_codes[0], remaining_codes_stored[0])) # This is not a good check
                                                                                                   # Better to check if the hash of used code is not in remaining_codes_stored

        used_code_was_removed = True
        for h_code in remaining_codes_stored:
            if sha256_crypt.verify(unhashed_backup_codes[0], h_code):
                used_code_was_removed = False
                break
        self.assertTrue(used_code_was_removed, "Used backup code was not removed from storage.")


    @patch('pyotp.TOTP')
    def test_08_2fa_verify_incorrect_code(self, mock_totp):
        self.user.otp_enabled = True
        self.user.otp_secret = pyotp.random_base32()
        self.user.otp_backup_codes = json.dumps([sha256_crypt.hash(secrets.token_hex(8))]) # Add one backup code
        db.session.commit()

        mock_totp_instance = mock_totp.return_value
        mock_totp_instance.verify.return_value = False # Simulate incorrect TOTP

        with self.client:
            with self.client.session_transaction() as sess:
                sess['user_id_for_2fa'] = self.user.id

            response = self.client.post(url_for('main.verify_2fa'), data={'code': '000000'}, follow_redirects=True) # Incorrect code

        self.assertEqual(response.status_code, 200) # Re-renders verify page
        self.assertIn(b'Invalid verification code.', response.data)
        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get('user_id_for_2fa')) # Session var should persist

    @patch('pyotp.TOTP')
    def test_09_disable_2fa_correct_credentials(self, mock_totp):
        # Enable 2FA first
        secret = pyotp.random_base32()
        self.user.otp_enabled = True
        self.user.otp_secret = secret
        self.user.otp_backup_codes = json.dumps([sha256_crypt.hash(secrets.token_hex(8))])
        db.session.commit()

        mock_totp_instance = mock_totp.return_value
        mock_totp_instance.verify.return_value = True # Simulate correct TOTP for disabling

        with self.client: # User is already logged in from setUp
            response = self.client.post(url_for('main.disable_2fa'), data={
                'password': 'password123',
                'totp_code': '123456' # Validated by mock
            }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Two-factor authentication has been disabled.', response.data)

        user_reloaded = User.query.get(self.user.id)
        self.assertFalse(user_reloaded.otp_enabled)
        self.assertIsNone(user_reloaded.otp_secret)
        self.assertIsNone(user_reloaded.otp_backup_codes)

    def test_10_disable_2fa_incorrect_password(self):
        self.user.otp_enabled = True
        self.user.otp_secret = pyotp.random_base32()
        db.session.commit()
        with self.client:
            response = self.client.post(url_for('main.disable_2fa'), data={
                'password': 'wrongpassword',
                'totp_code': '123456'
            }, follow_redirects=True)
        self.assertIn(b'Incorrect password.', response.data)
        self.assertTrue(User.query.get(self.user.id).otp_enabled) # Should still be enabled

    @patch('pyotp.TOTP')
    def test_11_disable_2fa_incorrect_totp(self, mock_totp):
        self.user.otp_enabled = True
        self.user.otp_secret = pyotp.random_base32()
        db.session.commit()
        mock_totp_instance = mock_totp.return_value
        mock_totp_instance.verify.return_value = False # Simulate incorrect TOTP
        with self.client:
            response = self.client.post(url_for('main.disable_2fa'), data={
                'password': 'password123',
                'totp_code': '000000'
            }, follow_redirects=True)
        self.assertIn(b'Invalid authenticator code.', response.data)
        self.assertTrue(User.query.get(self.user.id).otp_enabled)

    def test_12_access_2fa_setup_when_already_enabled(self):
        self.user.otp_enabled = True
        db.session.commit()
        with self.client:
            response = self.client.get(url_for('main.setup_2fa'), follow_redirects=True)
        self.assertIn(b'Two-factor authentication is already enabled.', response.data)
        # Should redirect to profile or a manage page
        self.assertTrue(response.request.path.startswith(url_for('main.profile', username=self.user.username)))

    def test_13_access_2fa_verify_without_session(self):
        # No user_id_for_2fa in session
        with self.client:
            self.client.get(url_for('main.logout')) # Ensure logged out and session cleared
            with self.client.session_transaction() as sess:
                sess.pop('user_id_for_2fa', None) # Explicitly clear
            response = self.client.get(url_for('main.verify_2fa'), follow_redirects=True)
        self.assertIn(b'2FA process not initiated. Please login first.', response.data)
        self.assertTrue(response.request.path.startswith(url_for('main.login')))

if __name__ == '__main__':
    unittest.main(verbosity=2)
