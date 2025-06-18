import unittest
import json
from app import create_app, db, socketio
from app.core.models import User, Application, AccessToken, LiveStream, StreamChatMessage
from app.services.media_service import MediaServerService # For mocking or direct checks
from config import TestingConfig
from datetime import datetime, timedelta, timezone
from unittest.mock import patch # For mocking MediaServerService if needed

class APILiveStreamsTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # User who will own an OAuth application (can also be a streamer)
        self.app_owner_user = User(username='stream_app_owner', email='stream_app_owner@example.com')
        self.app_owner_user.set_password('ownerpass')
        db.session.add(self.app_owner_user)

        # Another user, who will be a streamer
        self.streamer_user = User(username='streamer_one', email='streamer1@example.com')
        self.streamer_user.set_password('streamerpass')
        db.session.add(self.streamer_user)

        # A third user, for viewer actions or other tests
        self.viewer_user = User(username='viewer_one', email='viewer1@example.com')
        self.viewer_user.set_password('viewerpass')
        db.session.add(self.viewer_user)
        db.session.commit()

        # OAuth application (can be owned by app_owner_user or even streamer_user)
        self.application = Application(
            name='Stream Test Client',
            owner_user_id=self.app_owner_user.id
        )
        self.plain_client_secret = 'streamtestsecret'
        self.application.set_client_secret(self.plain_client_secret)
        db.session.add(self.application)
        db.session.commit()

        # Get a token for the streamer_user (for actions requiring user context)
        # For client_credentials, token is for app_owner. If stream API needs user-specific token,
        # we might need a different grant or a way to associate token with streamer_user.
        # The current @token_required sets g.current_user based on token's user_id.
        # For simplicity, let's assume client_credentials token (tied to app_owner) is used for now,
        # and API routes correctly use g.current_user which would be app_owner_user.
        # If stream creation etc. should be by streamer_one, then streamer_one needs a token.
        # Let's generate a token for streamer_user directly for these tests.
        self.streamer_token = AccessToken(
            user_id=self.streamer_user.id,
            application_id=self.application.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes="stream:manage" # Example scope
        )
        db.session.add(self.streamer_token)

        self.viewer_token = AccessToken(
            user_id=self.viewer_user.id,
            application_id=self.application.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes="stream:view" # Example scope
        )
        db.session.add(self.viewer_token)
        db.session.commit()


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _get_headers(self, token_string):
        return {'Authorization': f'Bearer {token_string}'}

    # --- LiveStream API Endpoint Tests ---

    def test_create_live_stream_success(self):
        headers = self._get_headers(self.streamer_token.token)
        response = self.app.post('/api/v1/streams', headers=headers, json={
            'title': 'My Awesome Coding Stream',
            'description': 'Coding a Flask app live!'
        })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn('id', data)
        self.assertEqual(data['title'], 'My Awesome Coding Stream')
        self.assertEqual(data['user_id'], self.streamer_user.id)
        self.assertEqual(data['status'], 'upcoming')

        stream = LiveStream.query.get(data['id'])
        self.assertIsNotNone(stream)
        self.assertEqual(stream.user_id, self.streamer_user.id)

    def test_create_live_stream_no_auth(self):
        response = self.app.post('/api/v1/streams', json={
            'title': 'No Auth Stream',
            'description': 'Trying to create without token'
        })
        self.assertEqual(response.status_code, 401)

    def test_create_live_stream_missing_title(self):
        headers = self._get_headers(self.streamer_token.token)
        response = self.app.post('/api/v1/streams', headers=headers, json={
            'description': 'Stream with no title'
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data['error'], 'ValidationError')
        self.assertIn('Title is required', data['message'])

    def test_get_live_stream_success(self):
        # First, create a stream
        stream = LiveStream(user_id=self.streamer_user.id, title="Gettable Stream")
        db.session.add(stream)
        db.session.commit()

        headers = self._get_headers(self.viewer_token.token) # Viewer can get stream info
        response = self.app.get(f'/api/v1/streams/{stream.id}', headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['id'], stream.id)
        self.assertEqual(data['title'], "Gettable Stream")
        self.assertIsNone(data['stream_key']) # Viewer should not see stream key

    def test_get_live_stream_as_owner_sees_key_if_live(self):
        stream = LiveStream(user_id=self.streamer_user.id, title="Owner Key Test", status="live", stream_key="ownerkey123")
        db.session.add(stream)
        db.session.commit()

        headers = self._get_headers(self.streamer_token.token) # Owner viewing
        response = self.app.get(f'/api/v1/streams/{stream.id}', headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['stream_key'], "ownerkey123")


    def test_get_live_stream_not_found(self):
        headers = self._get_headers(self.viewer_token.token)
        response = self.app.get('/api/v1/streams/9999', headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_update_live_stream_success(self):
        stream = LiveStream(user_id=self.streamer_user.id, title="Original Title")
        db.session.add(stream)
        db.session.commit()

        headers = self._get_headers(self.streamer_token.token)
        response = self.app.put(f'/api/v1/streams/{stream.id}', headers=headers, json={
            'title': 'Updated Title',
            'description': 'Updated Description'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['title'], 'Updated Title')
        self.assertEqual(data['description'], 'Updated Description')

        db.session.refresh(stream)
        self.assertEqual(stream.title, 'Updated Title')

    def test_update_live_stream_unauthorized_user(self):
        stream = LiveStream(user_id=self.streamer_user.id, title="Stream to update")
        db.session.add(stream)
        db.session.commit()

        viewer_headers = self._get_headers(self.viewer_token.token) # Viewer tries to update
        response = self.app.put(f'/api/v1/streams/{stream.id}', headers=viewer_headers, json={'title': 'Malicious Update'})
        self.assertEqual(response.status_code, 403)

    def test_delete_live_stream_success(self):
        stream = LiveStream(user_id=self.streamer_user.id, title="Stream to delete")
        db.session.add(stream)
        db.session.commit()
        stream_id = stream.id

        headers = self._get_headers(self.streamer_token.token)
        response = self.app.delete(f'/api/v1/streams/{stream_id}', headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['message'], 'Live stream deleted successfully')

        self.assertIsNone(LiveStream.query.get(stream_id))

    def test_delete_live_stream_unauthorized_user(self):
        stream = LiveStream(user_id=self.streamer_user.id, title="Protected Stream")
        db.session.add(stream)
        db.session.commit()

        viewer_headers = self._get_headers(self.viewer_token.token)
        response = self.app.delete(f'/api/v1/streams/{stream.id}', headers=viewer_headers)
        self.assertEqual(response.status_code, 403)

    @patch.object(MediaServerService, 'start_stream_on_server')
    def test_start_live_stream_success(self, mock_start_stream):
        # Mock the media server service to return success
        mock_start_stream.return_value = (True, 'rtmp://mock.server/live/testkey', None)

        stream = LiveStream(user_id=self.streamer_user.id, title="Stream to Start", status="upcoming")
        db.session.add(stream)
        db.session.commit()

        headers = self._get_headers(self.streamer_token.token)
        response = self.app.post(f'/api/v1/streams/{stream.id}/start', headers=headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'live')
        self.assertIsNotNone(data['stream_key'])
        self.assertEqual(data['media_server_url'], 'rtmp://mock.server/live/testkey')

        db.session.refresh(stream)
        self.assertEqual(stream.status, 'live')
        self.assertIsNotNone(stream.stream_key)
        self.assertIsNotNone(stream.start_time)
        self.assertEqual(stream.media_server_url, 'rtmp://mock.server/live/testkey')
        mock_start_stream.assert_called_once_with(stream.stream_key)

    def test_start_live_stream_already_live(self):
        stream = LiveStream(user_id=self.streamer_user.id, title="Already Live Stream", status="live")
        db.session.add(stream)
        db.session.commit()

        headers = self._get_headers(self.streamer_token.token)
        response = self.app.post(f'/api/v1/streams/{stream.id}/start', headers=headers)
        self.assertEqual(response.status_code, 409) # Conflict

    @patch.object(MediaServerService, 'end_stream_on_server')
    def test_end_live_stream_success(self, mock_end_stream):
        mock_end_stream.return_value = (True, None) # Simulate successful media server stop

        stream = LiveStream(user_id=self.streamer_user.id, title="Stream to End", status="live", stream_key="livekey123")
        db.session.add(stream)
        db.session.commit()

        headers = self._get_headers(self.streamer_token.token)
        response = self.app.post(f'/api/v1/streams/{stream.id}/end', headers=headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'ended')

        db.session.refresh(stream)
        self.assertEqual(stream.status, 'ended')
        self.assertIsNotNone(stream.end_time)
        mock_end_stream.assert_called_once_with("livekey123")

    def test_end_live_stream_not_live(self):
        stream = LiveStream(user_id=self.streamer_user.id, title="Not Live Stream", status="upcoming")
        db.session.add(stream)
        db.session.commit()

        headers = self._get_headers(self.streamer_token.token)
        response = self.app.post(f'/api/v1/streams/{stream.id}/end', headers=headers)
        self.assertEqual(response.status_code, 409) # Conflict

if __name__ == '__main__':
    unittest.main(verbosity=2)
