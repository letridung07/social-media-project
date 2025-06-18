import logging
from logging.config import fileConfig
import os # Retain this import as it's used by ini_path later

from flask import Flask # Added Flask
from config import Config # Added Config
from flask import current_app

from alembic import context

# Ensure models are imported before metadata is accessed.
from app.core import models  # noqa
# Import the db object directly from the app package
from app import db as application_db # noqa

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.

# Create a minimal Flask app for context to get DB URI
# This ensures that any environment variables or complex setup in Config are respected
flask_app = Flask(__name__)
flask_app.config.from_object(Config)
db_url = flask_app.config['SQLALCHEMY_DATABASE_URI']

config = context.config

# Set database URL in Alembic config BEFORE fileConfig is called if it relies on it,
# or ensure fileConfig doesn't need the db url.
# For safety, we set it here.
config.set_main_option('sqlalchemy.url', db_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# Assuming alembic.ini is in the directory above 'migrations/'
import os # Add import os here
ini_path = os.path.join(os.path.dirname(__file__), '..', 'alembic.ini')
fileConfig(ini_path)
logger = logging.getLogger('alembic.env')



def get_engine():
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# config.set_main_option('sqlalchemy.url', get_engine_url()) # Replaced by setting db_url above
# target_db is still used by get_engine indirectly via current_app, so keep it or adjust get_engine.
# For now, get_metadata will use application_db.metadata directly.
target_db = current_app.extensions['migrate'].db


def get_metadata():
    # Return metadata from the directly imported application_db
    return application_db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=get_metadata(), literal_binds=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    conf_args = current_app.extensions['migrate'].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    # Ensure compare_type is True to detect column type changes like String length
    conf_args['compare_type'] = True

    connectable = application_db.engine # Changed from get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
