from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager # Import LoginManager
from flask_socketio import SocketIO
from flask_mail import Mail # Import Mail
from flask_migrate import Migrate # Import Migrate
from flask_caching import Cache # Import Cache
from bootstrap_flask import Bootstrap # Import Bootstrap
from config import Config

db = SQLAlchemy()
cache = Cache() # Initialize Cache
csrf = CSRFProtect()
bootstrap = Bootstrap() # Initialize Bootstrap
login_manager = LoginManager() # Initialize LoginManager
socketio = SocketIO()
mail = Mail() # Create Mail instance
migrate = Migrate() # Create Migrate instance
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
    bootstrap.init_app(app) # Initialize Bootstrap with the app

    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from app.admin_routes import admin_bp # Import admin blueprint
    app.register_blueprint(admin_bp) # Register admin blueprint

    # If you have authentication routes, import and register them here
    # from app.auth import auth as auth_blueprint # We will create this soon
    # app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from app.utils import inject_unread_notification_count, inject_search_form # Import inject_search_form
    @app.context_processor
    def _inject_unread_notification_count():
        return inject_unread_notification_count()

    @app.context_processor
    def _inject_search_form():
        return inject_search_form()

    # Ensure models are imported so SQLAlchemy and Flask-Migrate are aware of them
    from app import models # noqa

    # Remove db.create_all() when using Flask-Migrate
    # with app.app_context():
    #     db.create_all() # Create database tables if they don't exist

    from app import events # noqa
    return app


@login_manager.user_loader
def load_user(user_id):
    # Since the user_id is just the primary key of our user table,
    # use it in the query for the user directly.
    from app.models import User # Import User model here to avoid circular imports
    return User.query.get(int(user_id))
