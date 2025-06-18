import logging
from flask import current_app

logger = logging.getLogger(__name__)

class MediaServerService:
    """
    A mock service to simulate interactions with a media server.
    """

    def __init__(self):
        # In a real scenario, this might take media server configuration
        self.media_server_base_url = current_app.config.get('MEDIA_SERVER_BASE_URL', 'rtmp://mock.media.server/live')
        logger.info("MediaServerService initialized.")

    def start_stream_on_server(self, stream_key: str) -> tuple[bool, str | None, str | None]:
        """
        Simulates starting a stream on the media server.

        Args:
            stream_key: The unique key for the stream.

        Returns:
            A tuple (success: bool, stream_url: str | None, error_message: str | None).
            `stream_url` is the RTMP URL the user would stream to.
        """
        if not stream_key:
            logger.error("MediaServerService: Stream key is required to start a stream.")
            return False, None, "Stream key missing."

        # Construct a plausible-looking RTMP URL
        # Example: rtmp://mock.media.server/live/{stream_key}
        # The application name (e.g., "live") might be configurable or fixed.
        stream_url = f"{self.media_server_base_url}/{stream_key}"

        # Simulate interaction with media server
        logger.info(f"MediaServerService: Attempting to register stream key '{stream_key}' with media server.")
        logger.info(f"MediaServerService: Stream '{stream_key}' is now expected at {stream_url}.")
        logger.info(f"MediaServerService: User should configure their OBS/streaming software to push to: {stream_url}")

        # In a real scenario, you might make an API call to your media server (e.g., Ant Media, Nginx-RTMP)
        # to authorize this stream key or set up the application endpoint.
        # If the media server confirms, return True.

        return True, stream_url, None

    def end_stream_on_server(self, stream_key: str) -> tuple[bool, str | None]:
        """
        Simulates ending a stream on the media server.

        Args:
            stream_key: The unique key for the stream.

        Returns:
            A tuple (success: bool, error_message: str | None).
        """
        if not stream_key:
            logger.error("MediaServerService: Stream key is required to end a stream.")
            return False, "Stream key missing."

        logger.info(f"MediaServerService: Attempting to signal media server to end stream for key '{stream_key}'.")
        # In a real scenario, you might make an API call to terminate the stream session,
        # release resources, or tell the server to stop accepting data for this key.
        logger.info(f"MediaServerService: Stream '{stream_key}' session ended on media server.")

        return True, None

    def get_stream_status_from_server(self, stream_key: str) -> dict:
        """
        Simulates querying the media server for the status of a stream.
        In a real scenario, this would involve an API call to the media server.
        """
        if not stream_key:
            return {"active": False, "viewers": 0, "error": "Stream key missing."}

        # This is a mock. A real server might return if the stream is active, viewer counts, bitrate, etc.
        logger.info(f"MediaServerService: Querying status for stream key '{stream_key}' (mock).")
        # Simulate some possibilities
        if stream_key.endswith("_active_mock"): # for testing
            return {"active": True, "viewers": 10, "bitrate": "1500kbps"}
        elif stream_key.endswith("_inactive_mock"):
            return {"active": False, "viewers": 0}

        # Default mock response: stream not actively broadcasting according to server
        return {"active": False, "viewers": 0, "reason": "Stream not publishing or key unknown (mock)"}

# Example of how to potentially initialize and use (not part of the class itself):
# if __name__ == '__main__':
#     # This part is for testing the service directly, not for Flask app use.
#     # For Flask, you'd typically instantiate this service where needed,
#     # or make its methods static if no state is involved, or use a factory.
+    # class MockApp:
+    #     def __init__(self):
+    #         self.config = {'MEDIA_SERVER_BASE_URL': 'rtmp://test.server/app'}
+    # current_app = MockApp() # Mock current_app for direct script execution test
+
#     logging.basicConfig(level=logging.INFO)
#     service = MediaServerService()
#     key = "test_stream_123"

#     success, url, err = service.start_stream_on_server(key)
#     if success:
#         print(f"Mock stream started. URL: {url}")
#     else:
#         print(f"Mock stream start failed: {err}")

#     status = service.get_stream_status_from_server(key)
#     print(f"Mock stream status for {key}: {status}")

#     active_key = "test_stream_active_mock"
#     status_active = service.get_stream_status_from_server(active_key)
#     print(f"Mock stream status for {active_key}: {status_active}")

#     success, err = service.end_stream_on_server(key)
#     if success:
#         print(f"Mock stream ended for key: {key}")
#     else:
#         print(f"Mock stream end failed: {err}")

# To make current_app available for the __init__ method when this module is loaded,
# it must be within a Flask application context or mocked.
# For actual usage within Flask, current_app will be available if the service
# is instantiated or its methods are called within a request context or app context.
# The __init__ using current_app.config is fine for that.
# The direct execution (__name__ == '__main__') part has been adjusted to reflect this.
# The commented out main block is just for conceptual testing.
# In a real Flask app, you might register this service with the app or use dependency injection.
# For this project, we will likely instantiate it in the routes.py or import its instance.

# A global instance could be created if configuration is static after app setup:
# media_service = MediaServerService()
# However, this means current_app must be available at import time, which is tricky.
# Better to instantiate on demand or pass app/config.
# For now, will instantiate in routes.py.
# Consider if this service should be a singleton or instantiated per request/use.
# Given its nature (external interaction), a singleton configured at app start might be suitable.
# But for simplicity, let's try instantiating in the route functions first.
# If that becomes repetitive, we can refactor to a shared instance later (e.g., on app object or g).

# Adding a simple factory function for easier use might be an option too:
# def get_media_service():
#     if 'media_service' not in g:
#         g.media_service = MediaServerService()
#     return g.media_service
# This would make it a per-request singleton.
# For now, direct instantiation in the route.
# The service methods primarily log, so multiple instances are not harmful.
# The config access in __init__ is the main part needing current_app.
# If MEDIA_SERVER_BASE_URL is fixed, it could be a global constant.
# But using current_app.config is more flexible.
# The logger also benefits from being named and potentially configured by the app.
# Final decision: Instantiate in routes.
# The logger is defined at module level, which is fine.
# `logger = logging.getLogger(__name__)` uses the module's name.
# `current_app.logger` could also be used if calls are within app context.
# Stick with `logging.getLogger(__name__)` for service-specific logs.
# The service's methods use `logger.info/error` which is fine.
# The `__init__` using `current_app.config` implies instantiation must happen
# when `current_app` is available.
# This is true if instantiated inside a request context (e.g., in a route function).
# Example: `media_service = MediaServerService()` inside `start_live_stream` route.
# This is acceptable.
