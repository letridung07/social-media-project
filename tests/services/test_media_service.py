import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from app.services.media_service import MediaServerService
from config import TestingConfig
import logging

class MediaServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        # Disable logging to stdout during these specific tests if too verbose
        # logging.disable(logging.CRITICAL)

    def tearDown(self):
        # logging.disable(logging.NOTSET) # Re-enable logging
        self.app_context.pop()

    def test_media_service_initialization(self):
        """Test MediaServerService initializes correctly."""
        with self.app.app_context(): # Ensure current_app is available
            service = MediaServerService()
            self.assertIsNotNone(service)
            self.assertEqual(service.media_server_base_url, self.app.config.get('MEDIA_SERVER_BASE_URL', 'rtmp://mock.media.server/live'))

    @patch('app.services.media_service.logger') # Mock the logger in media_service module
    def test_start_stream_on_server_success(self, mock_logger):
        """Test successful stream start simulation."""
        with self.app.app_context():
            service = MediaServerService()
            stream_key = "test_stream_key_success"
            success, stream_url, error_msg = service.start_stream_on_server(stream_key)

            self.assertTrue(success)
            self.assertIsNotNone(stream_url)
            self.assertTrue(stream_key in stream_url)
            self.assertIsNone(error_msg)

            # Check if logger was called with expected messages
            self.assertTrue(any("Attempting to register stream key" in call.args[0] for call in mock_logger.info.call_args_list))
            self.assertTrue(any(f"Stream '{stream_key}' is now expected at {stream_url}" in call.args[0] for call in mock_logger.info.call_args_list))

    @patch('app.services.media_service.logger')
    def test_start_stream_on_server_no_key(self, mock_logger):
        """Test stream start simulation with no stream key."""
        with self.app.app_context():
            service = MediaServerService()
            success, stream_url, error_msg = service.start_stream_on_server("") # Empty stream key

            self.assertFalse(success)
            self.assertIsNone(stream_url)
            self.assertEqual(error_msg, "Stream key missing.")
            mock_logger.error.assert_called_with("MediaServerService: Stream key is required to start a stream.")

    @patch('app.services.media_service.logger')
    def test_end_stream_on_server_success(self, mock_logger):
        """Test successful stream end simulation."""
        with self.app.app_context():
            service = MediaServerService()
            stream_key = "test_stream_key_end"
            success, error_msg = service.end_stream_on_server(stream_key)

            self.assertTrue(success)
            self.assertIsNone(error_msg)
            self.assertTrue(any(f"Attempting to signal media server to end stream for key '{stream_key}'" in call.args[0] for call in mock_logger.info.call_args_list))
            self.assertTrue(any(f"Stream '{stream_key}' session ended on media server." in call.args[0] for call in mock_logger.info.call_args_list))

    @patch('app.services.media_service.logger')
    def test_end_stream_on_server_no_key(self, mock_logger):
        """Test stream end simulation with no stream key."""
        with self.app.app_context():
            service = MediaServerService()
            success, error_msg = service.end_stream_on_server("") # Empty stream key

            self.assertFalse(success)
            self.assertEqual(error_msg, "Stream key missing.")
            mock_logger.error.assert_called_with("MediaServerService: Stream key is required to end a stream.")

    @patch('app.services.media_service.logger')
    def test_get_stream_status_from_server(self, mock_logger):
        """Test mock stream status fetching."""
        with self.app.app_context():
            service = MediaServerService()

            # Test with a generic key
            status_generic = service.get_stream_status_from_server("generic_key")
            self.assertFalse(status_generic['active'])
            self.assertEqual(status_generic['viewers'], 0)
            self.assertIn("Stream not publishing or key unknown", status_generic.get('reason', ''))
            mock_logger.info.assert_any_call("MediaServerService: Querying status for stream key 'generic_key' (mock).")

            # Test with a key indicating active mock
            status_active = service.get_stream_status_from_server("test_active_mock")
            self.assertTrue(status_active['active'])
            self.assertEqual(status_active['viewers'], 10)
            self.assertEqual(status_active['bitrate'], "1500kbps")
            mock_logger.info.assert_any_call("MediaServerService: Querying status for stream key 'test_active_mock' (mock).")

            # Test with a key indicating inactive mock
            status_inactive = service.get_stream_status_from_server("test_inactive_mock")
            self.assertFalse(status_inactive['active'])
            self.assertEqual(status_inactive['viewers'], 0)
            mock_logger.info.assert_any_call("MediaServerService: Querying status for stream key 'test_inactive_mock' (mock).")

            # Test with no key
            status_no_key = service.get_stream_status_from_server("")
            self.assertFalse(status_no_key['active'])
            self.assertEqual(status_no_key['viewers'], 0)
            self.assertEqual(status_no_key['error'], "Stream key missing.")
            # No logger call expected by the method itself for empty key before returning

if __name__ == '__main__':
    unittest.main(verbosity=2)
