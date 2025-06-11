import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'app/static/images' # For profile pictures
    POST_IMAGES_UPLOAD_FOLDER = 'app/static/post_images' # New config for post images
    VIDEO_UPLOAD_FOLDER = 'app/static/videos' # New config for post videos
    UPLOAD_FOLDER_GROUP_IMAGES = 'app/static/group_images' # For group images

    # Flask-Mail configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME or 'noreply@example.com')

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use in-memory SQLite for tests
    WTF_CSRF_ENABLED = False # Disable CSRF forms protection in testing
    VIDEO_UPLOAD_FOLDER = 'app/static/videos_test' # For test video uploads
    UPLOAD_FOLDER_GROUP_IMAGES = 'app/static/group_images_test' # For test group images
    # LOGIN_DISABLED = True # Useful if you want to bypass login in some tests
