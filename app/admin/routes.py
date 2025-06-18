from functools import wraps
from flask import Blueprint, render_template, flash, redirect, url_for, abort, request
from flask_login import current_user, login_required
# Import models and db when needed for actual admin routes, e.g.:
# from app.models import User, Post
from app import db, socketio # Added socketio
from app.utils.decorators import admin_required
from app.core.models import Post, Comment, ModerationLog, Notification, User # Added Notification, User
from app.utils.helpers import award_points # Added award_points
from sqlalchemy import or_
from flask import current_app # For logging

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Removed redundant admin_required decorator definition

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
            title_text=form.title_text.data,
            title_icon_url=form.title_icon_url.data if form.title_icon_url.data else None,
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
        good.title_text = form.title_text.data
        good.title_icon_url = form.title_icon_url.data if form.title_icon_url.data else None
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


@admin_bp.route('/moderation_queue')
@login_required
@admin_required
def moderation_queue():
    # Fetch posts needing moderation
    pending_posts = Post.query.filter(
        or_(Post.is_pending_moderation == True, Post.is_hidden_by_moderation == True)
    ).order_by(Post.timestamp.asc()).all()

    # Fetch comments needing moderation
    pending_comments = Comment.query.filter(
        or_(Comment.is_pending_moderation == True, Comment.is_hidden_by_moderation == True)
    ).order_by(Comment.timestamp.asc()).all()

    # Optionally, fetch associated ModerationLog entries
    # This can be done more efficiently in the template or by processing here
    # For now, we'll pass the items and let the template query logs if needed, or pass them separately.

    # A more optimized way would be to fetch logs and map them.
    # Example for posts:
    posts_with_logs = []
    for post in pending_posts:
        log_entry = ModerationLog.query.filter_by(related_post_id=post.id)\
                                     .order_by(ModerationLog.timestamp.desc()).first()
        posts_with_logs.append({'content': post, 'log': log_entry, 'type': 'Post'})

    comments_with_logs = []
    for comment in pending_comments:
        log_entry = ModerationLog.query.filter_by(related_comment_id=comment.id)\
                                     .order_by(ModerationLog.timestamp.desc()).first()
        comments_with_logs.append({'content': comment, 'log': log_entry, 'type': 'Comment'})

    all_pending_items = sorted(posts_with_logs + comments_with_logs, key=lambda x: x['content'].timestamp)


    return render_template('admin/moderation_queue.html',
                           all_pending_items=all_pending_items,
                           title="Moderation Queue")

# Helper function to get content object
def get_content_item(content_type, content_id):
    if content_type == 'post':
        return Post.query.get(content_id)
    elif content_type == 'comment':
        return Comment.query.get(content_id)
    return None

@admin_bp.route('/moderation/approve/<string:content_type>/<int:content_id>', methods=['POST'])
@login_required
@admin_required
def approve_content(content_type, content_id):
    content = get_content_item(content_type, content_id)
    if not content:
        flash(f'{content_type.capitalize()} not found.', 'danger')
        return redirect(url_for('admin.moderation_queue'))

    was_hidden = content.is_hidden_by_moderation
    content.is_pending_moderation = False
    content.is_hidden_by_moderation = False
    author_notified = False
    if content_type == 'post' and was_hidden:
        content.is_published = True # Publish if it was hidden

    # Create ModerationLog entry for this action
    log_entry = ModerationLog(
        user_id=current_user.id, # Admin who took the action
        action_taken=f'approved_by_admin',
        reason="Content approved by administrator.",
        related_post_id=content.id if content_type == 'post' else None,
        related_comment_id=content.id if content_type == 'comment' else None
    )
    db.session.add(log_entry)

    # Award points and send notifications if content was previously hidden and is now approved
    try:
        if was_hidden and content.author: # Ensure author exists
            author = content.author
            content_snippet = content.body[:50] + "..." if len(content.body) > 50 else content.body

            # Notification for approval
            approval_notification = Notification(
                recipient_id=author.id,
                actor_id=current_user.id, # Admin
                type='content_approved',
                related_post_id=content.id if content_type == 'post' else None,
                related_comment_id=content.id if content_type == 'comment' else None,
            )
            db.session.add(approval_notification)
            author_notified = True # Mark that we've prepared a notification

            # Gamification points
            if content_type == 'post':
                # Assuming media_items relationship exists or a way to check if it has media
                media_items_count = content.media_items.count() if hasattr(content, 'media_items') else 0
                points_for_post = 15 if media_items_count > 0 else 10
                award_points(author, 'create_post', points_for_post, related_item=content)
            elif content_type == 'comment':
                award_points(author, 'create_comment', 5, related_item=content)
                if content.commented_post and content.commented_post.author.id != author.id:
                    award_points(content.commented_post.author, 'receive_comment', 3, related_item=content)

            # TODO: Trigger general 'new post' or 'new comment' notifications
            # This is complex and might involve re-triggering logic from core routes.
            # Example: if content_type == 'post' and content.group_id:
            #   notify_group_members(content.group, content, current_user) # Hypothetical function
            # For now, this part is largely a placeholder.

        db.session.commit() # Commit all changes: content status, log, notifications, points

        if author_notified and content.author: # Send socket event after commit
             socketio.emit('new_notification', {
                'type': 'content_approved',
                'message': f"Your {content_type} ('{content.body[:30]}...') has been approved and is now visible.",
                'content_id': content.id,
                'content_type': content_type
            }, room=str(content.author.id))

        flash(f'{content_type.capitalize()} ID {content.id} approved and published.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error approving content: {str(e)}', 'danger')
        current_app.logger.error(f"Error approving {content_type} {content_id}: {e}")

    return redirect(url_for('admin.moderation_queue'))

@admin_bp.route('/moderation/reject_hide/<string:content_type>/<int:content_id>', methods=['POST'])
@login_required
@admin_required
def reject_hide_content(content_type, content_id):
    content = get_content_item(content_type, content_id)
    if not content:
        flash(f'{content_type.capitalize()} not found.', 'danger')
        return redirect(url_for('admin.moderation_queue'))

    content.is_pending_moderation = False
    content.is_hidden_by_moderation = True # Explicitly keep/make hidden
    if content_type == 'post':
        content.is_published = False # Ensure it's not published

    # Create ModerationLog entry
    log_entry = ModerationLog(
        user_id=current_user.id, # Admin
        action_taken='rejected_by_admin_hidden',
        reason="Content rejected by administrator and kept hidden.",
        related_post_id=content.id if content_type == 'post' else None,
        related_comment_id=content.id if content_type == 'comment' else None
    )
    db.session.add(log_entry)
    author_notified_rejection = False

    if content.author:
        rejection_notification = Notification(
            recipient_id=content.author.id,
            actor_id=current_user.id, # Admin
            type='content_rejected_hidden',
            related_post_id=content.id if content_type == 'post' else None,
            related_comment_id=content.id if content_type == 'comment' else None,
        )
        db.session.add(rejection_notification)
        author_notified_rejection = True

    try:
        db.session.commit()

        if author_notified_rejection and content.author:
            socketio.emit('new_notification', {
                'type': 'content_rejected_hidden',
                'message': f"Your {content_type} ('{content.body[:30]}...') was reviewed and will remain hidden.",
                'content_id': content.id,
                'content_type': content_type
            }, room=str(content.author.id))

        flash(f'{content_type.capitalize()} ID {content.id} rejected and will remain hidden.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error rejecting/hiding content: {str(e)}', 'danger')
        current_app.logger.error(f"Error rejecting/hiding {content_type} {content_id}: {e}")

    return redirect(url_for('admin.moderation_queue'))

@admin_bp.route('/moderation/delete/<string:content_type>/<int:content_id>', methods=['POST'])
@login_required
@admin_required
def delete_moderated_content(content_type, content_id):
    content = get_content_item(content_type, content_id)
    if not content:
        flash(f'{content_type.capitalize()} not found.', 'danger')
        return redirect(url_for('admin.moderation_queue'))

    # Create ModerationLog entry before deleting
    log_entry = ModerationLog(
        user_id=current_user.id, # Admin
        action_taken='deleted_by_admin',
        reason="Content deleted by administrator from moderation queue.",
        related_post_id=content.id if content_type == 'post' else None, # Log association before it's gone
        related_comment_id=content.id if content_type == 'comment' else None
    )
    db.session.add(log_entry)
    # Important: Need to commit the log entry before deleting the content if there are FK constraints
    # or if the deletion would prevent logging. However, ModerationLog's FKs are nullable.
    # For safety, one might flush here, or commit log separately.
    # For now, assume commit below handles it or FKs are fine.
    author_notified_deletion = False
    original_author_id = None
    content_snippet_for_notif = content.body[:30] + "..." if content.body and len(content.body) > 30 else (content.body or "N/A")


    if content.author:
        original_author_id = content.author.id # Save before content (and author attr) is deleted
        deletion_notification = Notification(
            recipient_id=original_author_id,
            actor_id=current_user.id, # Admin
            type='content_deleted_by_admin',
            # related_post_id and related_comment_id will be null after deletion,
            # so include info in message or store separately if needed for notification display.
            # For now, the type itself is the main info.
        )
        db.session.add(deletion_notification)
        author_notified_deletion = True

    try:
        db.session.delete(content) # Delete the actual post or comment
        db.session.commit() # Commit deletion and the log entry (and notification)

        if author_notified_deletion and original_author_id:
            socketio.emit('new_notification', {
                'type': 'content_deleted_by_admin',
                'message': f"Your {content_type} ('{content_snippet_for_notif}') was removed by an administrator.",
                # No content_id as it's deleted
                'content_type': content_type
            }, room=str(original_author_id))

        flash(f'{content_type.capitalize()} ID {content_id} has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting content: {str(e)}', 'danger')
        current_app.logger.error(f"Error deleting {content_type} {content_id}: {e}")

    return redirect(url_for('admin.moderation_queue'))
