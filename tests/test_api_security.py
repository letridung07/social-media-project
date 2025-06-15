import unittest
import json
import time
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models import User, Application, AccessToken, Post, FriendList, PRIVACY_PUBLIC, PRIVACY_CUSTOM_LIST
from app.oauth2 import generate_access_token, ACCESS_TOKEN_EXPIRES_IN_SECONDS
from config import TestingConfig

class APISecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        self.test_user = User(username='apiuser', email='api@example.com')
        self.test_user.set_password('apipassword')
        db.session.add(self.test_user)
        db.session.commit()

        self.test_application = Application(
            name='Test API Client',
            owner_user_id=self.test_user.id,
            redirect_uris='http://localhost/callback'
        )
        self.test_application.set_client_secret("testappsecret") # Set a client secret
        db.session.add(self.test_application)
        db.session.commit()

        # Generate a token for this user and app.
        self.access_token_string = generate_access_token(self.test_user, self.test_application)
        self.auth_headers = {'Authorization': f'Bearer {self.access_token_string}'}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # --- Token Authentication Tests ---
    def test_get_user_no_token(self):
        response = self.app.get(f'/api/v1/users/{self.test_user.id}')
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(data.get('error'), 'unauthorized')

    def test_get_user_invalid_token(self):
        response = self.app.get(f'/api/v1/users/{self.test_user.id}', headers={'Authorization': 'Bearer invalidtoken'})
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(data.get('error'), 'unauthorized')
        self.assertIn('Invalid or expired token', data.get('error_description', ''))


    def test_get_user_expired_token(self):
        # Create an expired token manually
        expired_token_value = "expiredtoken123"
        expired_token_entry = AccessToken(
            token=expired_token_value,
            user_id=self.test_user.id,
            application_id=self.test_application.id,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=(ACCESS_TOKEN_EXPIRES_IN_SECONDS + 3600)),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=3600) # Expired 1 hour ago
        )
        db.session.add(expired_token_entry)
        db.session.commit()

        response = self.app.get(f'/api/v1/users/{self.test_user.id}', headers={'Authorization': f'Bearer {expired_token_value}'})
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(data.get('error'), 'unauthorized')
        self.assertIn('Invalid or expired token', data.get('error_description', ''))


    def test_get_user_valid_token(self):
        response = self.app.get(f'/api/v1/users/{self.test_user.id}', headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(data.get('username'), self.test_user.username)

    # --- API Input Validation Tests (for POST /api/v1/posts) ---
    def test_create_post_missing_body(self):
        response = self.app.post('/api/v1/posts', headers=self.auth_headers,
                                 data=json.dumps({'privacy_level': PRIVACY_PUBLIC}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('Post body cannot be empty', data.get('message', '').lower())

    def test_create_post_body_too_long(self):
        long_body = "a" * 5001
        response = self.app.post('/api/v1/posts', headers=self.auth_headers,
                                 data=json.dumps({'body': long_body, 'privacy_level': PRIVACY_PUBLIC}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('exceeds maximum length', data.get('message', '').lower())

    def test_create_post_invalid_privacy(self):
        response = self.app.post('/api/v1/posts', headers=self.auth_headers,
                                 data=json.dumps({'body': 'Test post', 'privacy_level': 'SUPER_SECRET_INVALID'}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('invalid privacy_level', data.get('message', '').lower())

    def test_create_post_custom_privacy_missing_list_id(self):
        response = self.app.post('/api/v1/posts', headers=self.auth_headers,
                                 data=json.dumps({'body': 'Test post', 'privacy_level': PRIVACY_CUSTOM_LIST}),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('custom_friend_list_id is required', data.get('message', '').lower())

    def test_create_post_custom_privacy_invalid_list_id(self):
        response = self.app.post('/api/v1/posts', headers=self.auth_headers,
                                 data=json.dumps({'body': 'Test post',
                                                  'privacy_level': PRIVACY_CUSTOM_LIST,
                                                  'custom_friend_list_id': 99999}), # Non-existent list
                                 content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('invalid custom_friend_list_id', data.get('message', '').lower())


    # --- Rate Limiting Tests ---
    def test_rate_limit_get_user(self):
        # Default limit for API routes is "100 per hour, 20 per minute"
        # Test the 20 per minute limit
        for i in range(20): # First 20 requests
            response = self.app.get(f'/api/v1/users/{self.test_user.id}', headers=self.auth_headers)
            self.assertEqual(response.status_code, 200, f"Request {i+1} failed, expected 200")

        # 21st request should be rate limited
        response = self.app.get(f'/api/v1/users/{self.test_user.id}', headers=self.auth_headers)
        self.assertEqual(response.status_code, 429, "21st request did not return 429")
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('Rate limit exceeded', data.get('error', ''))


    def test_rate_limit_oauth_token(self):
        # Specific limit for /api/v1/oauth/token is "60/hour;5/minute"
        # Test the 5 per minute limit
        form_data = {
            'grant_type': 'client_credentials',
            'client_id': self.test_application.client_id,
            'client_secret': 'testappsecret' # The plain text secret set during setup
        }
        for i in range(5): # First 5 requests
            response = self.app.post('/api/v1/oauth/token', data=form_data)
            self.assertEqual(response.status_code, 200, f"Request {i+1} for oauth_token failed, expected 200. Message: {response.data.decode('utf-8')}")

        # 6th request should be rate limited
        response = self.app.post('/api/v1/oauth/token', data=form_data)
        self.assertEqual(response.status_code, 429, "6th request for oauth_token did not return 429")
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn('Rate limit exceeded', data.get('error', ''))

if __name__ == '__main__':
    unittest.main()
