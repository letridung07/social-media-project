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
# from flask_babel import Babel, lazy_gettext as _l, refresh # Removed direct import of localeselector
from flask import g, session, request
# from bootstrap_flask import Bootstrap # Import Bootstrap
from config import Config
# from app.scheduler import init_scheduler # Import the scheduler initializer MOVED

db = SQLAlchemy()
# babel = Babel() # Initialize Babel globally
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

    # Add language configuration if not already in Config
    if 'LANGUAGES' not in app.config:
        app.config['LANGUAGES'] = {'en': 'English', 'es': 'Español'}

    db.init_app(app)
    # babel.init_app(app) # Initialize the global babel instance with the app
    csrf.init_app(app)
    login_manager.init_app(app) # Initialize LoginManager with the app
    socketio.init_app(app)
    mail.init_app(app) # Initialize Mail with the app
    migrate.init_app(app, db) # Initialize Migrate with the app and db
    cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'}) # Initialize Cache with the app
    limiter.init_app(app)
    # bootstrap.init_app(app) # Initialize Bootstrap with the app

    from app.core.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from app.admin.routes import admin_bp # Import admin blueprint
    app.register_blueprint(admin_bp) # Register admin blueprint

    # Register API blueprint
    from app.api.routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1') # Example prefix

    # If you have authentication routes, import and register them here
    # from app.auth import auth as auth_blueprint # We will create this soon
    # app.register_blueprint(auth_blueprint, url_prefix='/auth')

    # # Babel locale selector
    # @babel.localeselector # Use the decorator from the global, initialized babel instance
    # def get_locale():
    #     # For User model to be available for g.user.locale
    #     from app.core.models import User # Import here to avoid circular import if User model uses _l
    #
    #     # 1. Try to get language from user profile (if user is logged in and has locale set)
    #     # For now, this part is commented out as User.locale is an optional enhancement.
    #     # if hasattr(g, 'user') and g.user is not None and g.user.is_authenticated and hasattr(g.user, 'locale') and g.user.locale:
    #     #     if g.user.locale in app.config['LANGUAGES']:
    #     #         return g.user.locale
    #
    #     # 2. Try to get language from session
    #     if 'language' in session and session['language'] in app.config['LANGUAGES']:
    #         return session['language']
    #
    #     # 3. Use browser's accept_languages
    #     if request and request.accept_languages: # Ensure request context is available
    #         best_match = request.accept_languages.best_match(list(app.config['LANGUAGES'].keys()))
    #         if best_match:
    #             return best_match
    #
    #     # 4. Default to 'en' or first language in config
    #     default_lang = 'en'
    #     if app.config['LANGUAGES']:
    #         if 'en' in app.config['LANGUAGES']:
    #             default_lang = 'en'
    #         else:
    #             default_lang = list(app.config['LANGUAGES'].keys())[0]
    #     return default_lang

    from app.utils.helpers import inject_unread_notification_count, inject_search_form, linkify_mentions # Import inject_search_form and linkify_mentions
    @app.context_processor
    def _inject_unread_notification_count():
        return inject_unread_notification_count()

    @app.context_processor
    def _inject_search_form():
        return inject_search_form()

    # Ensure models are imported so SQLAlchemy and Flask-Migrate are aware of them
    from app.core import models # noqa

    # Initialize the scheduler
    if not app.config.get('TESTING', False): # Optionally disable scheduler during tests
        from app.core.scheduler import init_scheduler # MOVED HERE
        with app.app_context(): # Ensure app context for scheduler init if it needs it
            init_scheduler(app)

    # Remove db.create_all() when using Flask-Migrate
    # with app.app_context():
    #     db.create_all() # Create database tables if they don't exist

    # Register custom Jinja2 filters
    app.jinja_env.filters['linkify_mentions'] = linkify_mentions

    from app.core import events # noqa

    @app.after_request
    def add_security_headers(response):
        # Define connect_src default list
        connect_src_list = ["'self'"]
        # Example: Allow LiveReload/WebSocket in debug mode
        if app.debug:
            connect_src_list.append("ws://localhost:*/")
            connect_src_list.append("ws://127.0.0.1:*/")

        # Add other dynamic sources if needed, e.g., Stripe
        # connect_src_list.append("https://api.stripe.com")

        connect_src_value = " ".join(connect_src_list)

        csp_policy = (
            "default-src 'self';"
            " img-src 'self' data: https:;"  # Allow images from self, data URIs, and any HTTPS source
            " style-src 'self' 'unsafe-inline' https://stackpath.bootstrapcdn.com https://cdn.jsdelivr.net https://fonts.googleapis.com;" # Common CDNs for styles
            " script-src 'self' 'unsafe-inline' https://code.jquery.com https://cdnjs.cloudflare.com https://stackpath.bootstrapcdn.com https://cdn.jsdelivr.net;" # Common CDNs for scripts. 'unsafe-inline' might be needed for some libs or inline JS.
            " font-src 'self' https://fonts.gstatic.com data:;" # Allow fonts from self, Google, and data URIs (for some icon fonts)
            " object-src 'none';"
            " frame-ancestors 'self';"
            f" connect-src {connect_src_value};"  # Use the defined connect_src_value
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
    from app.core.models import User # Import User model here to avoid circular imports
    return User.query.get(int(user_id))
