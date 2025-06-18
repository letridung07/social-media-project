import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'app/static/images' # For profile pictures
    POST_IMAGES_UPLOAD_FOLDER = 'app/static/post_images' # New config for post images
    VIDEO_UPLOAD_FOLDER = 'app/static/videos' # New config for post videos
    MEDIA_ITEMS_UPLOAD_FOLDER = 'app/static/media_items' # For post albums/galleries
    UPLOAD_FOLDER_GROUP_IMAGES = 'app/static/group_images' # For group images
    STORY_MEDIA_UPLOAD_FOLDER = os.path.join('app', 'static', 'story_media') # For story media
    AUDIO_UPLOAD_FOLDER_NAME = 'audio_uploads' # Name of the folder under static for audio
    MEDIA_UPLOAD_BASE_DIR = 'static' # Base directory for user-uploaded media (e.g. 'static' or 'uploads')

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB limit

    # Flask-Mail configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME or 'noreply@example.com')

    # Janus and TURN server configurations
    JANUS_SERVER_URL = os.environ.get('JANUS_SERVER_URL') or 'http://localhost:8088/janus' # Example placeholder
    TURN_SERVER_URL = os.environ.get('TURN_SERVER_URL') or 'turn:yourturnserver.example.com:3478' # Example placeholder
    TURN_SERVER_USERNAME = os.environ.get('TURN_SERVER_USERNAME') or 'turn_username' # Example placeholder
    TURN_SERVER_CREDENTIAL = os.environ.get('TURN_SERVER_CREDENTIAL') or 'turn_password' # Example placeholder

    # Stripe Configuration
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY') or 'your_stripe_publishable_key'
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY') or 'your_stripe_secret_key'
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET') or 'your_stripe_webhook_secret'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Moderation Thresholds & Settings
    MODERATION_THRESHOLD_FLAG = float(os.environ.get('MODERATION_THRESHOLD_FLAG', 0.7))
    MODERATION_THRESHOLD_SEVERE_BLOCK = float(os.environ.get('MODERATION_THRESHOLD_SEVERE_BLOCK', 0.9))
    MODERATION_THRESHOLD_GENERAL_BLOCK = float(os.environ.get('MODERATION_THRESHOLD_GENERAL_BLOCK', 0.95))
    # For MODERATION_CATEGORIES_AUTO_BLOCK, provide a comma-separated string in env var
    _auto_block_categories_str = os.environ.get('MODERATION_CATEGORIES_AUTO_BLOCK', 'SEVERE_TOXICITY,HATE_SPEECH')
    MODERATION_CATEGORIES_AUTO_BLOCK = [category.strip() for category in _auto_block_categories_str.split(',')]
    MODERATION_ENABLED = os.environ.get('MODERATION_ENABLED', 'True').lower() == 'true'


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use in-memory SQLite for tests
    WTF_CSRF_ENABLED = False # Disable CSRF forms protection in testing
    SERVER_NAME = 'localhost.test' # Added for url_for to work in tests
    APPLICATION_ROOT = '/'
    PREFERRED_URL_SCHEME = 'http'
    MEDIA_ITEMS_UPLOAD_FOLDER = 'app/static/media_items_test' # For test media items
    VIDEO_UPLOAD_FOLDER = 'app/static/videos_test' # For test video uploads
    UPLOAD_FOLDER_GROUP_IMAGES = 'app/static/group_images_test' # For test group images
    STORY_MEDIA_UPLOAD_FOLDER = os.path.join('app', 'static', 'story_media_test') # For test story media
    AUDIO_UPLOAD_FOLDER_NAME = 'audio_uploads_test'
    # LOGIN_DISABLED = True # Useful if you want to bypass login in some tests
