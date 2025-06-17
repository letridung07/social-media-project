import unittest
import json
from app import create_app, db
from app.core.models import User, Application, AccessToken
from config import TestingConfig
from datetime import datetime, timedelta, timezone

class APIAuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # Create a user who will own an application
        self.app_owner = User(username='api_owner', email='api_owner@example.com')
        self.app_owner.set_password('ownerpass')
        db.session.add(self.app_owner)
        db.session.commit()

        # Create an OAuth application
        self.application = Application(
            name='Test API Client',
            description='An application for testing API auth',
            redirect_uris='http://localhost/callback', # Dummy URI
            owner_user_id=self.app_owner.id
        )
        # Store plain text secret for tests, then hash it for storage
        self.plain_client_secret = 'testsecret123'
        self.application.set_client_secret(self.plain_client_secret)
        db.session.add(self.application)
        db.session.commit()

        # Create another regular user for some tests
        self.regular_user = User(username='api_user', email='api_user@example.com')
        self.regular_user.set_password('userpass')
        db.session.add(self.regular_user)
        db.session.commit()


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _get_oauth_token(self, client_id, client_secret):
        return self.app.post('/api/v1/oauth/token', data=dict(
            grant_type='client_credentials',
            client_id=client_id,
            client_secret=client_secret
        ))

    # --- OAuth Token Endpoint Tests ---
    def test_get_oauth_token_success(self):
        response = self._get_oauth_token(self.application.client_id, self.plain_client_secret)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('access_token', data)
        self.assertEqual(data['token_type'], 'bearer')
        self.assertGreater(data['expires_in'], 0)

        # Verify token exists in DB and is linked to app_owner
        token_obj = AccessToken.query.filter_by(token=data['access_token']).first()
        self.assertIsNotNone(token_obj)
        self.assertEqual(token_obj.user_id, self.app_owner.id)
        self.assertEqual(token_obj.application_id, self.application.id)

    def test_get_oauth_token_invalid_client_id(self):
        response = self._get_oauth_token('invalidclientid', self.plain_client_secret)
        self.assertEqual(response.status_code, 401) # InvalidClient
        data = response.get_json()
        self.assertEqual(data['error'], 'InvalidClient')

    def test_get_oauth_token_invalid_client_secret(self):
        response = self._get_oauth_token(self.application.client_id, 'wrongsecret')
        self.assertEqual(response.status_code, 401) # InvalidClient
        data = response.get_json()
        self.assertEqual(data['error'], 'InvalidClient')

    def test_get_oauth_token_missing_params(self):
        response = self.app.post('/api/v1/oauth/token', data=dict(grant_type='client_credentials'))
        self.assertEqual(response.status_code, 400) # InvalidRequest
        data = response.get_json()
        self.assertEqual(data['error'], 'InvalidRequest')
        self.assertIn('Missing grant_type, client_id, or client_secret', data['message'])

    def test_get_oauth_token_unsupported_grant_type(self):
        response = self.app.post('/api/v1/oauth/token', data=dict(
            grant_type='password', # Not supported
            client_id=self.application.client_id,
            client_secret=self.plain_client_secret
        ))
        self.assertEqual(response.status_code, 400) # UnsupportedGrantType
        data = response.get_json()
        self.assertEqual(data['error'], 'UnsupportedGrantType')


    # --- @token_required Decorator Tests ---
    def test_access_protected_api_no_token(self):
        # Example: /api/v1/users/<user_id> - needs a user ID, let's use regular_user.id
        response = self.app.get(f'/api/v1/users/{self.regular_user.id}')
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data['error'], 'unauthorized')
        self.assertIn('Missing or invalid authorization token', data['error_description'])

    def test_access_protected_api_invalid_token(self):
        headers = {'Authorization': 'Bearer invalidtoken123'}
        response = self.app.get(f'/api/v1/users/{self.regular_user.id}', headers=headers)
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data['error'], 'unauthorized')
        self.assertIn('Invalid or expired token', data['error_description'])

    def test_access_protected_api_expired_token(self):
        # Generate a token that expires quickly
        expired_token = AccessToken(
            user_id=self.app_owner.id,
            application_id=self.application.id,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1) # Expired 1 hour ago
        )
        db.session.add(expired_token)
        db.session.commit()

        headers = {'Authorization': f'Bearer {expired_token.token}'}
        response = self.app.get(f'/api/v1/users/{self.regular_user.id}', headers=headers)
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data['error'], 'unauthorized')
        self.assertIn('Invalid or expired token', data['error_description'])

        # Check if the expired token was deleted by validate_access_token
        self.assertIsNone(AccessToken.query.get(expired_token.id))


    def test_access_protected_api_valid_token(self):
        # Get a valid token first
        token_response = self._get_oauth_token(self.application.client_id, self.plain_client_secret)
        token = token_response.get_json()['access_token']

        headers = {'Authorization': f'Bearer {token}'}
        response = self.app.get(f'/api/v1/users/{self.regular_user.id}', headers=headers)
        self.assertEqual(response.status_code, 200) # Assuming regular_user profile is public
        data = response.get_json()
        self.assertEqual(data['username'], self.regular_user.username)

if __name__ == '__main__':
    unittest.main()
