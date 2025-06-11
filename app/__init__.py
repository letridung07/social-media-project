from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager # Import LoginManager
from flask_socketio import SocketIO
from config import Config

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager() # Initialize LoginManager
socketio = SocketIO()
login_manager.login_view = 'main.login' # Corrected login view
login_manager.login_message_category = 'info'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app) # Initialize LoginManager with the app
    socketio.init_app(app)

    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # If you have authentication routes, import and register them here
    # from app.auth import auth as auth_blueprint # We will create this soon
    # app.register_blueprint(auth_blueprint, url_prefix='/auth')

    with app.app_context():
        db.create_all() # Create database tables if they don't exist

    from app import events # noqa
    return app


@login_manager.user_loader
def load_user(user_id):
    # Since the user_id is just the primary key of our user table,
    # use it in the query for the user directly.
    from app.models import User # Import User model here to avoid circular imports
    return User.query.get(int(user_id))
