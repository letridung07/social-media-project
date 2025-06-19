from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_mail import Mail
from flask_migrate import Migrate
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_babel import Babel, lazy_gettext as _l, refresh # Standard import
from flask import g, session, request
# from bootstrap_flask import Bootstrap
from config import Config
# from app.scheduler import init_scheduler

db = SQLAlchemy()
# babel = Babel() # Standard global instance - Will be initialized in create_app
cache = Cache()
csrf = CSRFProtect()
login_manager = LoginManager()
socketio = SocketIO()
mail = Mail()
migrate = Migrate()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per hour", "20 per minute"],
    storage_uri="memory://"
)

login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if 'LANGUAGES' not in app.config:
        app.config['LANGUAGES'] = {'en': 'English', 'es': 'Español'}

    # Define get_locale before babel is initialized
    def get_locale():
        from app.core.models import User
        # Logic for get_locale, e.g.:
        # if hasattr(g, 'user') and g.user is not None and hasattr(g.user, 'locale') and g.user.locale:
        #     if g.user.locale in app.config['LANGUAGES']:
        #         return g.user.locale
        if 'language' in session and session['language'] in app.config['LANGUAGES']:
            return session['language']
        if request and request.accept_languages:
            best_match = request.accept_languages.best_match(list(app.config['LANGUAGES'].keys()))
            if best_match:
                return best_match
        default_lang = 'en'
        if app.config['LANGUAGES']:
            if 'en' in app.config['LANGUAGES']:
                default_lang = 'en'
            else:
                default_lang = list(app.config['LANGUAGES'].keys())[0]
        return default_lang

    db.init_app(app)
    babel = Babel(app, locale_selector=get_locale) # Pass selector here
    csrf.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'})
    limiter.init_app(app)
    # bootstrap.init_app(app)

    from app.core.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp)

    from app.api.routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    # get_locale is now defined above and passed to Babel constructor

    from app.utils.helpers import inject_unread_notification_count, inject_search_form, linkify_mentions
    @app.context_processor
    def _inject_unread_notification_count():
        return inject_unread_notification_count()

    @app.context_processor
    def _inject_search_form():
        return inject_search_form()

    from app.core import models # noqa

    if not app.config.get('TESTING', False):
        from app.core.scheduler import init_scheduler
        with app.app_context():
            init_scheduler(app)

    app.jinja_env.filters['linkify_mentions'] = linkify_mentions
    from app.core import events # noqa

    @app.after_request
    def add_security_headers(response):
        connect_src_list = ["'self'"]
        if app.debug:
            connect_src_list.append("ws://localhost:*/")
            connect_src_list.append("ws://127.0.0.1:*/")
        connect_src_value = " ".join(connect_src_list)
        csp_policy = (
            "default-src 'self';"
            " img-src 'self' data: https:;"
            " style-src 'self' 'unsafe-inline' https://stackpath.bootstrapcdn.com https://cdn.jsdelivr.net https://fonts.googleapis.com;"
            " script-src 'self' 'unsafe-inline' https://code.jquery.com https://cdnjs.cloudflare.com https://stackpath.bootstrapcdn.com https://cdn.jsdelivr.net;"
            " font-src 'self' https://fonts.gstatic.com data:;"
            " object-src 'none';"
            " frame-ancestors 'self';"
            f" connect-src {connect_src_value};"
            " base-uri 'self';"
            " form-action 'self';"
        )
        response.headers['Content-Security-Policy'] = csp_policy
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response

    return app


@login_manager.user_loader
def load_user(user_id):
    from app.core.models import User
    return User.query.get(int(user_id))
