from functools import wraps
from flask import Blueprint, render_template, flash, redirect, url_for, abort, request
from flask_login import current_user, login_required
# Import models and db when needed for actual admin routes, e.g.:
# from app.models import User, Post
# from app import db

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            # If using login_required before admin_required, this might be redundant,
            # but it's a good safeguard if admin_required is ever used alone.
            return redirect(url_for('main.login', next=request.url))

        # hasattr check is good if is_admin might not exist on some User-like objects,
        # but for standard User model from Flask-Login, is_admin should exist if added.
        # current_user.is_admin relies on the User model having an is_admin attribute.
        if not getattr(current_user, 'is_admin', False): # Safely check for is_admin, default to False
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('main.index')) # Or abort(403)
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@login_required # Ensures user is logged in
@admin_required # Ensures user is an admin
def admin_dashboard():
    # This will be replaced with a proper dashboard template later
    return "Admin Dashboard Placeholder"

# Example of how other admin routes would be defined:
# @admin_bp.route('/users')
# @login_required
# @admin_required
# def manage_users():
#     # Logic to manage users
#     return "Manage Users Placeholder"
