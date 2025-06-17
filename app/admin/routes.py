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

from app.core.models import VirtualGood
from app.core.forms import VirtualGoodForm
from app import db
from sqlalchemy.exc import SQLAlchemyError
from flask import current_app # For logging

# List Virtual Goods
@admin_bp.route('/virtual_goods')
@login_required
@admin_required
def list_virtual_goods():
    goods = []
    error_message = None
    try:
        goods = VirtualGood.query.all()
    except SQLAlchemyError as e:
        current_app.logger.error(f"Error fetching virtual goods for admin list: {e}")
        error_message = "Error fetching virtual goods. Please check logs."
        flash(error_message, "danger")
    return render_template('admin/virtual_goods_list.html', goods=goods, error_message=error_message, title="Manage Virtual Goods")

# Add Virtual Good
@admin_bp.route('/virtual_goods/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_virtual_good():
    form = VirtualGoodForm()
    if form.validate_on_submit():
        new_good = VirtualGood(
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            currency=form.currency.data,
            type=form.type.data,
            image_url=form.image_url.data if form.image_url.data else None,
            is_active=form.is_active.data
        )
        try:
            db.session.add(new_good)
            db.session.commit()
            flash('Virtual good added successfully!', 'success')
            return redirect(url_for('admin.list_virtual_goods'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding virtual good: {e}")
            flash('Error adding virtual good. Please check logs and try again.', 'danger')
        except Exception as e: # Catch other potential errors
            db.session.rollback()
            current_app.logger.error(f"Unexpected error adding virtual good: {e}")
            flash('An unexpected error occurred. Please try again.', 'danger')

    return render_template('admin/virtual_good_form.html', form=form, title="Add New Virtual Good", form_action="Add")

# Edit Virtual Good
@admin_bp.route('/virtual_goods/edit/<int:good_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_virtual_good(good_id):
    good = VirtualGood.query.get_or_404(good_id)
    form = VirtualGoodForm(obj=good)
    if form.validate_on_submit():
        good.name = form.name.data
        good.description = form.description.data
        good.price = form.price.data
        good.currency = form.currency.data
        good.type = form.type.data
        good.image_url = form.image_url.data if form.image_url.data else None
        good.is_active = form.is_active.data
        try:
            db.session.commit()
            flash('Virtual good updated successfully!', 'success')
            return redirect(url_for('admin.list_virtual_goods'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating virtual good {good_id}: {e}")
            flash('Error updating virtual good. Please check logs and try again.', 'danger')
        except Exception as e: # Catch other potential errors
            db.session.rollback()
            current_app.logger.error(f"Unexpected error updating virtual good {good_id}: {e}")
            flash('An unexpected error occurred. Please try again.', 'danger')

    return render_template('admin/virtual_good_form.html', form=form, title="Edit Virtual Good", good=good, form_action="Edit")
