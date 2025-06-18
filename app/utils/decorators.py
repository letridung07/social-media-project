from functools import wraps
from flask_login import current_user
from flask import abort, flash, redirect, url_for

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            # If using Flask-Login, unauthenticated users are usually redirected by @login_required
            # If not, this is a good place to redirect them to login.
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('main.login', next=request.url))
        if not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            # Decide where to redirect non-admins. Home page is a common choice.
            return redirect(url_for('main.index'))
            # Alternatively, abort(403) if you want to show a generic "Forbidden" page
            # abort(403)
        return f(*args, **kwargs)
    return decorated_function
