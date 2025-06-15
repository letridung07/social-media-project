from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager # Import LoginManager
from flask_socketio import SocketIO
from flask_mail import Mail # Import Mail
from flask_migrate import Migrate # Import Migrate
from flask_caching import Cache # Import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
# from bootstrap_flask import Bootstrap # Import Bootstrap
from config import Config
# from app.scheduler import init_scheduler # Import the scheduler initializer MOVED

db = SQLAlchemy()
cache = Cache() # Initialize Cache
csrf = CSRFProtect()
# bootstrap = Bootstrap() # Initialize Bootstrap
login_manager = LoginManager() # Initialize LoginManager
socketio = SocketIO()
mail = Mail() # Create Mail instance
migrate = Migrate() # Create Migrate instance

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour", "20 per minute"],
    storage_uri="memory://" # For simplicity in this environment; consider Redis in production
)

login_manager.login_view = 'main.login' # Corrected login view
login_manager.login_message_category = 'info'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app) # Initialize LoginManager with the app
    socketio.init_app(app)
    mail.init_app(app) # Initialize Mail with the app
    migrate.init_app(app, db) # Initialize Migrate with the app and db
    cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'}) # Initialize Cache with the app
    limiter.init_app(app)
    # bootstrap.init_app(app) # Initialize Bootstrap with the app

    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from app.admin_routes import admin_bp # Import admin blueprint
    app.register_blueprint(admin_bp) # Register admin blueprint

    # Register API blueprint
    from app.api_routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1') # Example prefix

    # If you have authentication routes, import and register them here
    # from app.auth import auth as auth_blueprint # We will create this soon
    # app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from app.utils import inject_unread_notification_count, inject_search_form, linkify_mentions # Import inject_search_form and linkify_mentions
    @app.context_processor
    def _inject_unread_notification_count():
        return inject_unread_notification_count()

    @app.context_processor
    def _inject_search_form():
        return inject_search_form()

    # Ensure models are imported so SQLAlchemy and Flask-Migrate are aware of them
    from app import models # noqa

    # Initialize the scheduler
    if not app.config.get('TESTING', False): # Optionally disable scheduler during tests
        from app.scheduler import init_scheduler # MOVED HERE
        with app.app_context(): # Ensure app context for scheduler init if it needs it
            init_scheduler(app)

    # Remove db.create_all() when using Flask-Migrate
    # with app.app_context():
    #     db.create_all() # Create database tables if they don't exist

    # Register custom Jinja2 filters
    app.jinja_env.filters['linkify_mentions'] = linkify_mentions

    from app import events # noqa

    @app.after_request
    def add_security_headers(response):
        csp_policy = (
            "default-src 'self';"
            " img-src 'self' data: https:;"  # Allow images from self, data URIs, and any HTTPS source
            " style-src 'self' 'unsafe-inline' https://stackpath.bootstrapcdn.com https://cdn.jsdelivr.net https://fonts.googleapis.com;" # Common CDNs for styles
            " script-src 'self' https://code.jquery.com https://cdnjs.cloudflare.com https://stackpath.bootstrapcdn.com https://cdn.jsdelivr.net;" # Common CDNs for scripts
            " font-src 'self' https://fonts.gstatic.com data:;" # Allow fonts from self, Google, and data URIs (for some icon fonts)
            " object-src 'none';"
            " frame-ancestors 'self';"
            f" connect-src {connect_src};"  # Dynamically set connect-src
            " base-uri 'self';"
            " form-action 'self';"
        )
        response.headers['Content-Security-Policy'] = csp_policy
        # Add other security headers here if needed in the future, e.g., X-Content-Type-Options
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN' # Though frame-ancestors in CSP is more modern
        response.headers['X-XSS-Protection'] = '1; mode=block' # Older browser XSS protection
        return response

    return app


@login_manager.user_loader
def load_user(user_id):
    # Since the user_id is just the primary key of our user table,
    # use it in the query for the user directly.
    from app.models import User # Import User model here to avoid circular imports
    return User.query.get(int(user_id))
