import os
import re # For hashtag parsing
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app, jsonify # Import jsonify
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy import or_
from app import db, socketio
from app.forms import RegistrationForm, LoginForm, EditProfileForm, PostForm, CommentForm, ForgotPasswordForm, ResetPasswordForm, GroupCreationForm, StoryForm, PollForm, EventForm
from app.models import User, Post, Like, Comment, Notification, Conversation, ChatMessage, Hashtag, Group, GroupMembership, Story, Poll, PollOption, PollVote, followers, Event # Import PollVote and Event
from app.utils import save_picture, save_post_image, save_post_video, save_group_image, save_story_media
from app.email_utils import send_password_reset_email # Import email utility

main = Blueprint('main', __name__)

LIKE_MILESTONES = [10, 50, 100, 250, 500, 1000]

# Helper function for processing hashtags
def process_hashtags(post_body, post_object):
    # Clear existing hashtags for the post (important for edits)
    post_object.hashtags = []

    # Regex to find hashtags: words starting with #, alphanumeric characters and underscores
    hashtag_regex = r"#([a-zA-Z0-9_]+)"
    found_tags_texts = re.findall(hashtag_regex, post_body)

    for tag_text in set(found_tags_texts): # Use set to avoid duplicate processing for same tag in one post
        normalized_tag = tag_text.lower() # Normalize to lowercase
        hashtag = Hashtag.query.filter_by(tag_text=normalized_tag).first()
        if not hashtag:
            hashtag = Hashtag(tag_text=normalized_tag)
            db.session.add(hashtag)
            # No commit here yet, will be committed with the post

        if hashtag not in post_object.hashtags: # Ensure not to add duplicates
             post_object.hashtags.append(hashtag)

@main.route('/')
@main.route('/index')
def index():
    page = request.args.get('page', 1, type=int) # Optional: for pagination later
    if current_user.is_authenticated:
        # Personalized feed for logged-in users
        # followed_posts() returns a query, so we can paginate it if needed
        # For now, just get all:
        posts = current_user.followed_posts().all()
        # If pagination was desired:
        # posts_query = current_user.followed_posts()
        # posts_pagination = posts_query.paginate(page=page, per_page=current_app.config.get('POSTS_PER_PAGE', 10), error_out=False)
        # posts = posts_pagination.items
        # render_template('index.html', ..., pagination=posts_pagination)
    else:
        # Public feed for guests (e.g., most recent posts from all users)
        posts = Post.query.order_by(Post.timestamp.desc()).all()
        # If pagination was desired:
        # posts_query = Post.query.order_by(Post.timestamp.desc())
        # posts_pagination = posts_query.paginate(page=page, per_page=current_app.config.get('POSTS_PER_PAGE', 10), error_out=False)
        # posts = posts_pagination.items
        # render_template('index.html', ..., pagination=posts_pagination)

    # The template 'index.html' already iterates through 'posts'
    comment_form = CommentForm() # Instantiate the form
    return render_template('index.html', title='Home', posts=posts, comment_form=comment_form) # Pass to template


@main.route('/search')
def search():
    query = request.args.get('q', '').strip()
    users_found = []
    posts_found = []
    groups_found = []

    if query:
        # Search Users by username or email (case-insensitive)
        users_found = User.query.filter(
            or_(
                User.username.ilike(f'%{query}%'),
                User.email.ilike(f'%{query}%')
            )
        ).all()

        # Search Posts by body content (case-insensitive)
        posts_found = Post.query.filter(
            Post.body.ilike(f'%{query}%')
        ).order_by(Post.timestamp.desc()).all()

        # Search Groups by name or description (case-insensitive)
        groups_found = Group.query.filter(
            or_(
                Group.name.ilike(f'%{query}%'),
                Group.description.ilike(f'%{query}%')
            )
        ).all()

    return render_template('search_results.html',
                           title=f'Search Results for "{query}"' if query else 'Search',
                           query=query,
                           users=users_found,
                           posts=posts_found,
                           groups=groups_found)


@main.route('/hashtag/<string:tag_text>')
def hashtag_feed(tag_text):
    normalized_tag_text = tag_text.lower()
    hashtag = Hashtag.query.filter_by(tag_text=normalized_tag_text).first()
    posts = []
    title = f'No posts found for #{normalized_tag_text}'

    if hashtag:
        posts = hashtag.posts.order_by(Post.timestamp.desc()).all()
        title = f'Posts tagged #{hashtag.tag_text}'
        if not posts: # Hashtag exists but no posts are associated
             title = f'No posts found for #{hashtag.tag_text}'


    return render_template('hashtag_feed.html', title=title, hashtag=hashtag, posts=posts, query=tag_text) # Pass original tag_text as query for display


@main.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html', title='Register', form=form)

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.index'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Sign In', form=form)

@main.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@main.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = user.get_reset_password_token()
            reset_url = url_for('main.reset_password', token=token, _external=True)
            email_sent = send_password_reset_email(user.email, user.username, reset_url)
            if email_sent:
                flash('An email has been sent with instructions to reset your password.', 'info')
            else:
                flash('There was an issue sending the password reset email. Please try again later or contact support.', 'danger')
        else:
            # Generic message for security (doesn't reveal if email exists or not)
            # flash('If an account with that email exists, a password reset link has been sent.', 'info')
            # To avoid user confusion if email sending fails, it's better to give the success message always here
            # as the email sending failure is already handled above by a more specific error.
            # However, for strict security against user enumeration, the generic message is preferred.
            # Let's stick to the more user-friendly approach for now, assuming logger captures send errors.
             flash('If an account with that email exists, instructions to reset your password have been sent.', 'info')
        return redirect(url_for('main.login'))
    return render_template('forgot_password.html', title='Forgot Password', form=form)


@main.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.verify_reset_password_token(token)
    if not user:
        flash('That is an invalid or expired token.', 'warning')
        return redirect(url_for('main.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been updated! You are now able to log in.', 'success')
        return redirect(url_for('main.login'))

    return render_template('reset_password_form.html', title='Reset Password', form=form, token=token)


@main.route('/user/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    # Query posts for this specific user, newest first
    posts = user.posts.order_by(Post.timestamp.desc()).all() # Assuming 'posts' is the relationship name
    comment_form = CommentForm() # Instantiate the form
    return render_template('profile.html', title=f"{user.username}'s Profile", user=user, posts=posts, comment_form=comment_form) # Pass to template

@main.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        if form.profile_picture.data:
            old_picture_url = current_user.profile_picture_url # Store old one
            picture_file = save_picture(form.profile_picture.data)
            # Delete old profile picture if not default and if it exists
            if old_picture_url and old_picture_url != 'default_profile_pic.png':
                try:
                    # Path confirmed from app/utils.py: static/images/
                    old_picture_path = os.path.join(current_app.root_path, 'static/images', old_picture_url)
                    if os.path.exists(old_picture_path):
                        os.remove(old_picture_path)
                        # flash('Old profile picture removed.', 'info') # Optional feedback
                except Exception as e:
                    current_app.logger.error(f"Error deleting old profile picture {old_picture_url}: {e}")
                    # flash('Error removing old profile picture.', 'warning') # Optional feedback
            current_user.profile_picture_url = picture_file
        current_user.bio = form.bio.data
        db.session.commit()
        flash('Your profile has been updated!', 'success')
        return redirect(url_for('main.profile', username=current_user.username))
    elif request.method == 'GET':
        form.bio.data = current_user.bio
        # The profile picture field is not pre-filled for security and usability reasons.
        # Users must re-select a file if they want to change it.
    return render_template('edit_profile.html', title='Edit Profile', form=form)

@main.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    group_id_param = request.args.get('group_id', type=int)
    target_group = None
    group_name_for_template = None

    if group_id_param:
        target_group = Group.query.get(group_id_param)
        if not target_group:
            flash('Group not found.', 'warning')
            return redirect(url_for('main.index'))

        membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=target_group.id).first()
        if not membership:
            flash('You are not a member of this group and cannot post in it.', 'danger')
            return redirect(url_for('main.view_group', group_id=target_group.id))
        group_name_for_template = target_group.name

    form = PostForm()
    video_filename_to_save = None # Initialize
    if form.validate_on_submit():
        image_filename_to_save = None # Initialize
        if form.image_file.data:
            try:
                image_filename_to_save = save_post_image(form.image_file.data)
            except Exception as e:
                # Log the error e (e.g., using current_app.logger.error(f"Image upload error: {e}"))
                flash('An error occurred while uploading the image. Please try a different image or contact support.', 'danger')
                return render_template('create_post.html', title='Create Post', form=form) # Re-render form

        if form.video_file.data:
            try:
                video_filename_to_save = save_post_video(form.video_file.data)
            except Exception as e:
                # Log the error e (e.g., using current_app.logger.error(f"Video upload error: {e}"))
                flash('An error occurred while uploading the video. Please try a different video or contact support.', 'danger')
                return render_template('create_post.html', title='Create Post', form=form) # Re-render form

        # Create Post object, including the image_filename if one was saved
        post = Post(
            body=form.body.data,
            author=current_user,
            image_filename=image_filename_to_save, # If applicable
            video_filename=video_filename_to_save, # If applicable
            alt_text=form.alt_text.data
        )
        if target_group:
            post.group_id = target_group.id

        db.session.add(post)
        # Process hashtags before committing the post
        process_hashtags(post.body, post)
        # Commit post first to get post.id
        db.session.commit()

        if target_group: # target_group is the Group object from earlier in the route
            # Notify group members about the new post
            for membership_assoc in target_group.memberships:
                member_user = membership_assoc.user
                if member_user.id != current_user.id: # Don't notify the post author
                    notification = Notification(
                        recipient_id=member_user.id,
                        actor_id=current_user.id,
                        type='new_group_post',
                        related_post_id=post.id,
                        related_group_id=target_group.id
                    )
                    db.session.add(notification)
            db.session.commit() # Commit notifications

        flash('Your post is now live!', 'success')
        if target_group:
            return redirect(url_for('main.view_group', group_id=target_group.id))
        else:
            return redirect(url_for('main.index'))

    return render_template('create_post.html', title='Create Post', form=form, group_id=group_id_param, group_name=group_name_for_template)


@main.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)  # Forbidden access

    form = PostForm(obj=post)  # Pre-populate with existing post data for GET

    if form.validate_on_submit():
        post.body = form.body.data

        # Handle image update
        if form.image_file.data:
            # Delete old image if it exists and is not the default
            if post.image_filename:
                try:
                    old_image_path = os.path.join(current_app.root_path, current_app.config.get('POST_IMAGES_UPLOAD_FOLDER', 'app/static/post_images_default'), post.image_filename)
                    if os.path.exists(old_image_path):
                        os.remove(old_image_path)
                except Exception as e:
                    current_app.logger.error(f"Error deleting old post image {post.image_filename}: {e}")
                    flash('Error removing old image.', 'warning')
            # Save new image
            try:
                post.image_filename = save_post_image(form.image_file.data)
            except Exception as e:
                flash('An error occurred while uploading the new image. Please try again.', 'danger')
                return render_template('edit_post.html', title='Edit Post', form=form, post=post)

        # Handle video update
        if form.video_file.data:
            # Delete old video if it exists
            if post.video_filename:
                try:
                    old_video_path = os.path.join(current_app.root_path, current_app.config.get('VIDEO_UPLOAD_FOLDER', 'app/static/videos_default'), post.video_filename)
                    if os.path.exists(old_video_path):
                        os.remove(old_video_path)
                except Exception as e:
                    current_app.logger.error(f"Error deleting old post video {post.video_filename}: {e}")
                    flash('Error removing old video.', 'warning')
            # Save new video
            try:
                post.video_filename = save_post_video(form.video_file.data)
            except Exception as e:
                flash('An error occurred while uploading the new video. Please try again.', 'danger')
                return render_template('edit_post.html', title='Edit Post', form=form, post=post)

        # Process hashtags before committing the post changes
        post.alt_text = form.alt_text.data # <-- Add this line
        process_hashtags(post.body, post)
        db.session.commit()
        flash('Your post has been updated!', 'success')
        return redirect(url_for('main.profile', username=current_user.username)) # Or redirect to post view: url_for('main.view_post', post_id=post.id)

    # For GET requests, pre-fill form fields if not already done by obj=post for WTForms-Alchemy
    # For standard WTForms, you might do:
    # elif request.method == 'GET':
    # form.body.data = post.body
    # The image/video fields are not pre-filled as they are file inputs

    return render_template('edit_post.html', title='Edit Post', form=form, post=post)


@main.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)

    # Delete associated image file
    if post.image_filename:
        try:
            image_path = os.path.join(current_app.root_path, current_app.config.get('POST_IMAGES_UPLOAD_FOLDER', 'app/static/post_images_default'), post.image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            current_app.logger.error(f"Error deleting post image {post.image_filename}: {e}")
            flash('Error deleting post image file.', 'warning') # Inform user, but proceed with DB deletion

    # Delete associated video file
    if post.video_filename:
        try:
            video_path = os.path.join(current_app.root_path, current_app.config.get('VIDEO_UPLOAD_FOLDER', 'app/static/videos_default'), post.video_filename)
            if os.path.exists(video_path):
                os.remove(video_path)
        except Exception as e:
            current_app.logger.error(f"Error deleting post video {post.video_filename}: {e}")
            flash('Error deleting post video file.', 'warning') # Inform user, but proceed with DB deletion

    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted!', 'success')
    return redirect(url_for('main.profile', username=current_user.username)) # Or redirect to main.index


@main.route('/follow/<username>', methods=['POST']) # Use POST as it changes state
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user == current_user:
        flash('You cannot follow yourself!', 'warning')
        return redirect(url_for('main.profile', username=username))
    if current_user.is_following(user):
        flash(f'You are already following {username}.', 'info')
        return redirect(url_for('main.profile', username=username))

    current_user.follow(user)
    db.session.commit()
    flash(f'You are now following {username}!', 'success')

    # Notification and event for follow
    notification = Notification(
        recipient_id=user.id, # The user being followed
        actor_id=current_user.id, # The user who initiated the follow
        type='follow'
    )
    db.session.add(notification)
    db.session.commit()
    socketio.emit('new_notification',
                  {'message': f'{current_user.username} started following you.', 'type': 'follow', 'actor_username': current_user.username},
                  room=str(user.id))

    return redirect(url_for('main.profile', username=username))

@main.route('/unfollow/<username>', methods=['POST']) # Use POST as it changes state
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user == current_user:
        flash('You cannot unfollow yourself!', 'warning')
        return redirect(url_for('main.profile', username=username))
    if not current_user.is_following(user):
        flash(f'You are not following {username}.', 'info')
        return redirect(url_for('main.profile', username=username))

    current_user.unfollow(user)
    db.session.commit()
    flash(f'You have unfollowed {username}.', 'success')
    return redirect(url_for('main.profile', username=username))

@main.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id): # Renamed function to avoid conflict with Like model
    post = Post.query.get_or_404(post_id)
    if Like.query.filter_by(user_id=current_user.id, post_id=post.id).first():
        flash('You have already liked this post.', 'info')
    else:
        like = Like(user_id=current_user.id, post_id=post.id)
        db.session.add(like)
        db.session.commit() # Commit the like first to update post.like_count()
        flash('You liked the post!', 'success')

        # Notification and event for like (and milestones)
        if post.author.id != current_user.id:
            # Standard 'like' notification
            std_like_notification = Notification(
                recipient_id=post.author.id,
                actor_id=current_user.id,
                type='like',
                related_post_id=post.id
            )
            db.session.add(std_like_notification)
            # Commit the standard 'like' notification first if it's the only one or before milestone processing
            # This ensures its availability if milestone logic depends on it, though it doesn't directly.
            # More importantly, it makes its emission happen after its commit.

            # db.session.add(std_like_notification) # This was duplicated and part of the syntax error source

            # Buffer for milestone notifications to be created
            # new_milestone_notifications_to_emit = [] # Not strictly needed if we iterate milestones_hit_this_like
            milestones_hit_this_like = [] # To store (milestone_obj, milestone_count)

            current_like_count = post.like_count()
            for milestone_val in LIKE_MILESTONES:
                if current_like_count == milestone_val:
                    existing_milestone_notif = Notification.query.filter_by(
                        recipient_id=post.author.id,
                        related_post_id=post.id,
                        type=f'like_milestone_{milestone_val}'
                    ).first()
                    if not existing_milestone_notif:
                        milestone_notif = Notification(
                            recipient_id=post.author.id,
                            actor_id=current_user.id,
                            type=f'like_milestone_{milestone_val}',
                            related_post_id=post.id
                        )
                        db.session.add(milestone_notif)
                        # Prepare data for emit, but don't emit yet
                        milestones_hit_this_like.append({'milestone_obj': milestone_notif, 'milestone_count': milestone_val})

            # Commit all new notifications (standard like + any milestones) together
            db.session.commit()

            # Now emit events after commit
            # Standard like notification (if post author is not current user)
            socketio.emit('new_notification',
                          {'message': f'{current_user.username} liked your post.',
                           'type': 'like',
                           'actor_username': current_user.username,
                           'post_id': post.id,
                           'post_author_username': post.author.username
                           },
                          room=str(post.author.id))

            # Milestone notifications
            for item in milestones_hit_this_like:
                # milestone_notif_obj = item['milestone_obj'] # Object reference if needed later
                milestone_count = item['milestone_count']
                socketio.emit('new_notification',
                              {'message': f"Your post '{post.body[:30]}{'...' if len(post.body) > 30 else ''}' reached {milestone_count} likes!",
                               'type': f'like_milestone_{milestone_count}',
                               'actor_username': current_user.username,
                               'post_id': post.id,
                               'post_author_username': post.author.username,
                               'milestone_count': milestone_count
                               },
                              room=str(post.author.id))

    # Consider redirecting to request.referrer if available and safe, otherwise index or post permalink
    return redirect(request.referrer or url_for('main.index'))

@main.route('/unlike/<int:post_id>', methods=['POST'])
@login_required
def unlike_post(post_id): # Renamed function
    post = Post.query.get_or_404(post_id) # Ensure post exists
    like = Like.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    if like:
        db.session.delete(like)
        db.session.commit()
        flash('You unliked the post.', 'success')
    else:
        flash('You have not liked this post yet.', 'info')
    return redirect(request.referrer or url_for('main.index'))

@main.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    form = CommentForm() # This form will be submitted from the template where the post is displayed
    if form.validate_on_submit(): # Check if the submitted form (from the template) is valid
        comment = Comment(body=form.body.data, author=current_user, commented_post=post)
        db.session.add(comment)
        db.session.commit()
        flash('Your comment has been added!', 'success')

        # Notification and event for comment
        if post.author.id != current_user.id:
            notification = Notification(
                recipient_id=post.author.id,
                actor_id=current_user.id,
                type='comment',
                related_post_id=post.id
                # Consider adding related_comment_id=comment.id if useful
            )
            db.session.add(notification)
            db.session.commit() # Commit notification
            socketio.emit('new_notification', # Emit after commit
                          {'message': f'{current_user.username} commented on your post.',
                           'type': 'comment', # notification.type
                           'actor_username': current_user.username,
                           'post_id': post.id,
                           'post_author_username': post.author.username,
                           'comment_body': comment.body[:50] + "..." if len(comment.body) > 50 else comment.body
                           },
                          room=str(post.author.id))
    else:
        # Handle form errors, e.g., if comment is empty or too long.
        # Flashing errors might be one way, but usually, the form is re-rendered with errors.
        # For now, just a generic flash if validation fails, though this is not ideal UX.
        # A better approach for complex pages is AJAX or rendering the page again with form errors.
        if form.errors:
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(f"{field.capitalize()}: {error}")
            flash("Error adding comment: " + "; ".join(error_messages), 'danger')
        else:
            flash('Error adding comment. Please try again.', 'danger')

    # Redirect to the previous page, or the index page as a fallback.
    # Ideally, redirect to the post itself, perhaps with an anchor to the comments section.
    # e.g., redirect(url_for('main.some_post_view_route', post_id=post.id) + '#comments')
    # For now, request.referrer is a good general solution.
    return redirect(request.referrer or url_for('main.index'))

@main.route('/notifications')
@login_required
def notifications():
    # Fetch notifications for the current user, newest first
    user_notifications = Notification.query.filter_by(recipient_id=current_user.id).order_by(Notification.timestamp.desc()).all()
    for notification in user_notifications:
        notification.is_read = True
    db.session.commit()
    socketio.emit('notifications_cleared', {'message': 'All notifications marked as read.'}, room=str(current_user.id))
    return render_template('notifications.html', title='Your Notifications', notifications=user_notifications)


@main.route('/chat')
@main.route('/conversations')
@login_required
def list_conversations():
    # Fetch conversations where the current user is a participant, ordered by last_updated
    user_conversations = current_user.conversations.order_by(Conversation.last_updated.desc()).all()
    return render_template('chat/conversations_list.html', title='My Chats', conversations=user_conversations, ChatMessage=ChatMessage)

@main.route('/chat/<int:conversation_id>')
@login_required
def view_conversation(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    # Ensure current_user is part of this conversation
    if current_user not in conversation.participants:
        flash('You are not part of this conversation.', 'danger')
        return redirect(url_for('main.list_conversations'))

    messages = conversation.messages.all()

    other_participants = [p for p in conversation.participants if p.id != current_user.id]

    return render_template('chat/view_conversation.html',
                           title=f'Chat with {", ".join(p.username for p in other_participants) if other_participants else "Saved Messages"}',
                           conversation=conversation,
                           messages=messages,
                           other_participants=other_participants)

@main.route('/chat/start/<int:user_id>', methods=['POST', 'GET'])
@login_required
def start_or_get_conversation(user_id):
    other_user = User.query.get_or_404(user_id)
    if other_user == current_user:
        flash("You cannot start a chat with yourself.", 'warning')
        # Assuming 'main.profile' is the correct endpoint for user profiles
        return redirect(url_for('main.profile', username=current_user.username))

    # Find conversations current_user is in
    current_user_conv_ids = [conv.id for conv in current_user.conversations]

    # Find conversations other_user is in
    other_user_conv_ids = [conv.id for conv in other_user.conversations]

    # Find common conversations
    common_conv_ids = list(set(current_user_conv_ids) & set(other_user_conv_ids))

    existing_conversation = None
    for conv_id in common_conv_ids:
        conv = Conversation.query.get(conv_id)
        if conv and len(conv.participants) == 2: # Strictly 1-on-1
            # Ensure both current_user and other_user are the participants
            participant_ids = {p.id for p in conv.participants}
            if current_user.id in participant_ids and other_user.id in participant_ids:
                 existing_conversation = conv
                 break

    if not existing_conversation:
        conversation = Conversation()
        conversation.participants.append(current_user)
        conversation.participants.append(other_user)
        db.session.add(conversation)
        db.session.commit()
        flash(f'Chat started with {other_user.username}.', 'success')
        return redirect(url_for('main.view_conversation', conversation_id=conversation.id))
    else:
        return redirect(url_for('main.view_conversation', conversation_id=existing_conversation.id))

import json # Added for preparing data for Chart.js
from sqlalchemy import func

@main.route('/analytics')
@login_required
def analytics():
    user_posts = current_user.posts.all() # Get all posts once

    total_posts_count = len(user_posts)

    total_likes_received = 0
    total_comments_received = 0
    for post in user_posts:
        total_likes_received += post.likes.count()
        total_comments_received += post.comments.count()

    follower_count = current_user.followers.count()
    following_count = current_user.followed.count()

    # Simpler method for top posts using Python's sorted()
    # This is generally fine for a moderate number of posts per user.
    # For users with extremely large numbers of posts, a DB-level query would be more performant.
    sorted_posts = sorted(user_posts, key=lambda p: p.likes.count(), reverse=True)
    top_5_posts = sorted_posts[:5]

    # Alternative DB-level query for top 5 posts (more performant for very large datasets)
    # top_5_posts_query_result = db.session.query(
    # Post, func.count(Like.id).label('total_likes')
    # ).join(Like, Like.post_id == Post.id, isouter=True).filter(
    # Post.user_id == current_user.id
    # ).group_by(Post.id).order_by(func.count(Like.id).desc()).limit(5).all()
    # top_5_posts = [post_obj for post_obj, _ in top_5_posts_query_result]

    # Prepare data for "Likes per Post" chart
    top_posts_chart_data = []
    if top_5_posts:
        top_posts_chart_data = json.dumps([
            {'label': f"Post ID {post.id}: {post.body[:20]}..." if len(post.body) > 20 else f"Post ID {post.id}: {post.body}", 'value': post.likes.count()}
            for post in top_5_posts
        ])


    return render_template('analytics.html', title='User Analytics',
                           user=current_user,
                           total_posts=total_posts_count,
                           total_likes_received=total_likes_received,
                           total_comments_received=total_comments_received,
                           follower_count=follower_count,
                           following_count=following_count,
                           top_posts=top_5_posts,
                           top_posts_chart_data=top_posts_chart_data)

# -------------------- Event Routes --------------------

@main.route('/event/create', methods=['GET', 'POST'])
@login_required
def create_event():
    form = EventForm()
    if form.validate_on_submit():
        event = Event(
            name=form.name.data,
            description=form.description.data,
            start_datetime=form.start_datetime.data,
            end_datetime=form.end_datetime.data,
            location=form.location.data,
            organizer_id=current_user.id
        )
        db.session.add(event)
        db.session.commit()
        flash('Event created successfully!', 'success')
        return redirect(url_for('main.view_event', event_id=event.id)) # Assuming view_event route exists
    return render_template('create_event.html', title='Create Event', form=form)

@main.route('/events')
def events_list():
    events = Event.query.order_by(Event.start_datetime.asc()).all()
    return render_template('events_list.html', title='Upcoming Events', events=events)

@main.route('/event/<int:event_id>')
def view_event(event_id):
    event = Event.query.get_or_404(event_id)
    is_attending = False
    if current_user.is_authenticated:
        is_attending = current_user in event.attendees
    return render_template('event_detail.html', title=event.name, event=event, is_attending=is_attending)

@main.route('/event/<int:event_id>/join', methods=['POST'])
@login_required
def join_event(event_id):
    event = Event.query.get_or_404(event_id)
    if current_user not in event.attendees:
        event.attendees.append(current_user)
        db.session.add(event) # Add event to session if it was modified

        # Notification for the event organizer
        if event.organizer_id != current_user.id:
            notification = Notification(
                recipient_id=event.organizer_id,
                actor_id=current_user.id,
                type='event_join',
                related_event_id=event.id
            )
            db.session.add(notification)
            # Emit socketio event if desired for real-time notification
            socketio.emit('new_notification',
                          {'message': f'{current_user.username} is attending your event: {event.name}.',
                           'type': 'event_join',
                           'actor_username': current_user.username,
                           # 'event_id': event.id, # Optional: for client-side routing
                           'event_name': event.name
                           },
                          room=str(event.organizer_id))

        db.session.commit()
        flash(f'You are now attending {event.name}!', 'success')
    else:
        flash(f'You are already attending {event.name}.', 'info')
    return redirect(url_for('main.view_event', event_id=event.id))

@main.route('/event/<int:event_id>/leave', methods=['POST'])
@login_required
def leave_event(event_id):
    event = Event.query.get_or_404(event_id)
    if current_user in event.attendees:
        event.attendees.remove(current_user)
        db.session.add(event) # Add event to session if it was modified
        db.session.commit()
        flash(f'You are no longer attending {event.name}.', 'success')
    else:
        flash(f'You were not attending {event.name}.', 'info')
    return redirect(url_for('main.view_event', event_id=event.id))

@main.route('/event/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)
    if event.organizer_id != current_user.id:
        abort(403)  # Forbidden
    form = EventForm(obj=event)
    if form.validate_on_submit():
        event.name = form.name.data
        event.description = form.description.data
        event.start_datetime = form.start_datetime.data
        event.end_datetime = form.end_datetime.data
        event.location = form.location.data
        db.session.commit() # Commit event changes first

        # Notify attendees about the update
        for attendee in event.attendees:
            if attendee.id != current_user.id: # Don't notify the organizer
                notification = Notification(
                    recipient_id=attendee.id,
                    actor_id=current_user.id,
                    type='event_updated',
                    related_event_id=event.id
                )
                db.session.add(notification)
                # Emit socketio event for real-time notification
                socketio.emit('new_notification',
                              {'message': f'Event "{event.name}" has been updated.',
                               'type': 'event_updated',
                               'actor_username': current_user.username,
                               'event_id': event.id,
                               'event_name': event.name
                               },
                              room=str(attendee.id))
        db.session.commit() # Commit notifications
        flash('Event updated successfully! Attendees have been notified.', 'success')
        return redirect(url_for('main.view_event', event_id=event.id))
    return render_template('edit_event.html', title='Edit Event', form=form, event=event)

@main.route('/event/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    if event.organizer_id != current_user.id:
        abort(403)  # Forbidden

    # Before deleting the event, clear its attendees list to manage the many-to-many relationship
    # This might not be strictly necessary depending on cascade settings, but it's explicit.
    # Store event name and attendees before clearing/deleting for notifications
    event_name_for_notification = event.name
    attendees_to_notify = list(event.attendees) # Create a copy

    event.attendees = []
    db.session.commit() # Commit this change first

    db.session.delete(event)
    db.session.commit() # Commit deletion of event

    # Notify former attendees about the cancellation
    for attendee in attendees_to_notify:
        if attendee.id != current_user.id: # Don't notify the organizer
            notification = Notification(
                recipient_id=attendee.id,
                actor_id=current_user.id,
                type='event_cancelled',
                # related_event_id is not set here as the event is deleted.
                # Store event name in notification body/data if needed, or handle in template.
                # For simplicity, we'll rely on the type and actor.
            )
            # Add event name to notification message if possible, or handle in template
            # For now, keeping it simple as related_event_id won't link to a live event.
            db.session.add(notification)
            socketio.emit('new_notification',
                          {'message': f'Event "{event_name_for_notification}" has been cancelled.',
                           'type': 'event_cancelled',
                           'actor_username': current_user.username,
                           # 'event_id': event_id, # Pass original event_id if useful for client
                           'event_name': event_name_for_notification
                           },
                          room=str(attendee.id))
    db.session.commit() # Commit notifications

    flash('Event deleted successfully! Attendees have been notified of the cancellation.', 'success')
    return redirect(url_for('main.events_list'))


# -------------------- Group Routes --------------------

@main.route('/group/create', methods=['GET', 'POST'])
@login_required
def create_group():
    form = GroupCreationForm()
    if form.validate_on_submit():
        group_image_filename = None
        if form.image_file.data:
            try:
                group_image_filename = save_group_image(form.image_file.data)
            except Exception as e:
                current_app.logger.error(f"Group image upload error: {e}")
                flash('An error occurred while uploading the group image. Please try again.', 'danger')
                return render_template('create_group.html', title='Create Group', form=form)

        group = Group(
            name=form.name.data,
            description=form.description.data,
            creator_id=current_user.id,
            image_file=group_image_filename if group_image_filename else 'default_group_pic.png'
        )
        db.session.add(group)
        db.session.flush() # Flush to get group.id for GroupMembership

        # Add creator as admin member
        membership = GroupMembership(
            user_id=current_user.id,
            group_id=group.id,
            role='admin'
        )
        db.session.add(membership)
        db.session.commit()
        flash('Group created successfully!', 'success')
        return redirect(url_for('main.view_group', group_id=group.id))
    return render_template('create_group.html', title='Create Group', form=form)

@main.route('/group/<int:group_id>')
def view_group(group_id):
    group = Group.query.get_or_404(group_id)
    # Fetch posts associated with this group, newest first
    # Assuming group.posts is the backref from Post model
    posts = group.posts.order_by(Post.timestamp.desc()).all()

    is_member = False
    is_admin = False
    if current_user.is_authenticated:
        membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=group.id).first()
        if membership:
            is_member = True
            if membership.role == 'admin':
                is_admin = True

    # TODO: Create app/templates/group.html in a later step
    return render_template('group.html', title=group.name, group=group, posts=posts, is_member=is_member, is_admin=is_admin)

@main.route('/group/<int:group_id>/join', methods=['POST'])
@login_required
def join_group(group_id):
    group = Group.query.get_or_404(group_id)
    existing_membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=group.id).first()
    if existing_membership:
        flash('You are already a member of this group.', 'info')
    else:
        membership = GroupMembership(user_id=current_user.id, group_id=group.id, role='member') # Default role
        db.session.add(membership)
        db.session.commit() # Commit membership first

        # Notify group admins about the new member
        admins = User.query.join(GroupMembership).filter(
            GroupMembership.group_id == group.id,
            GroupMembership.role == 'admin'
        ).all()

        for admin_user in admins:
            if admin_user.id != current_user.id: # Don't notify admin if they are the one joining (should not happen for join)
                notification = Notification(
                    recipient_id=admin_user.id,
                    actor_id=current_user.id,
                    type='user_joined_group',
                    related_group_id=group.id
                )
                db.session.add(notification)
        db.session.commit() # Commit notifications

        flash(f'You have successfully joined the group: {group.name}!', 'success')
    return redirect(url_for('main.view_group', group_id=group.id))

@main.route('/group/<int:group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    group = Group.query.get_or_404(group_id)
    membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=group.id).first()
    if not membership:
        flash('You are not a member of this group.', 'info')
    else:
        # Consideration: Prevent creator from leaving if they are the only admin.
        # For now, allowing leave. If they are an admin, their admin role is removed with membership.
        # If group has no admins left, it might become unmanageable. This logic can be added later.
        # Example check (can be more complex):
        # if group.creator_id == current_user.id:
        #     admins = GroupMembership.query.filter_by(group_id=group.id, role='admin').all()
        #     if len(admins) == 1 and admins[0].user_id == current_user.id:
        #         flash('As the creator and only admin, you cannot leave the group. Please designate another admin first.', 'warning')
        #         return redirect(url_for('main.view_group', group_id=group.id))

        db.session.delete(membership)
        db.session.commit()
        flash(f'You have left the group: {group.name}.', 'success')
        # TODO: Notification for group admin/creator about member leaving (if not self)
    return redirect(url_for('main.view_group', group_id=group.id)) # Could also redirect to a general groups listing page

@main.route('/groups')
@login_required # Or remove @login_required for public browsing
def groups_list():
    all_groups = Group.query.order_by(Group.name).all()
    # The template groups.html will be created in a subsequent step
    return render_template('groups.html', title='Browse Groups', groups=all_groups)


# -------------------- Story Routes --------------------

@main.route('/stories')
@login_required
def display_stories():
    now = datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow()

    followed_user_ids = [user.id for user in current_user.followed]
    user_ids_to_show = followed_user_ids + [current_user.id]

    active_stories = Story.query.filter(
        Story.user_id.in_(user_ids_to_show),
        Story.expires_at > now
    ).order_by(Story.timestamp.desc()).all()

    return render_template('stories.html', title='Stories', stories=active_stories)

@main.route('/story/create', methods=['GET', 'POST'])
@login_required
def create_story():
    form = StoryForm()
    if form.validate_on_submit():
        if form.media_file.data:
            try:
                filename, media_type = save_story_media(form.media_file.data)

                story_data = {
                    'user_id': current_user.id,
                    'caption': form.caption.data
                }
                if media_type == 'image':
                    story_data['image_filename'] = filename
                elif media_type == 'video':
                    story_data['video_filename'] = filename
                else:
                    # This case should ideally not be reached if FileAllowed and save_story_media are robust
                    flash('Unsupported media type after saving.', 'danger')
                    return render_template('create_story.html', title='Create Story', form=form)

                story = Story(**story_data)
                db.session.add(story)
                db.session.commit()
                flash('Your story has been posted!', 'success')
                return redirect(url_for('main.index')) # Or a dedicated stories page later

            except Exception as e:
                current_app.logger.error(f"Story media upload/save error: {e}")
                flash('An error occurred while processing your story media. Please try again.', 'danger')
        else:
            # This case should be caught by form.validate_on_submit() if media_file has DataRequired()
            flash('No media file provided.', 'warning')

    return render_template('create_story.html', title='Create Story', form=form)

# -------------------- Poll Routes --------------------

@main.route('/poll/create', methods=['GET', 'POST'])
@login_required
def create_poll():
    post_id_arg = request.args.get('post_id', type=int)
    group_id_arg = request.args.get('group_id', type=int)

    linked_post = None
    linked_group = None

    form = PollForm() # Instantiate form first

    if request.method == 'GET':
        if post_id_arg:
            linked_post = Post.query.get(post_id_arg)
            if linked_post:
                # Basic check: is current_user the author of the post?
                # Or if it's a group post, is current_user a member of the group?
                # For simplicity, let's assume for now if post_id is provided, it's valid for linking.
                # More complex validation can be added (e.g. cannot attach poll to other's direct post).
                form.post_id.data = post_id_arg
            else:
                flash('Linked post not found.', 'warning')
        if group_id_arg:
            linked_group = Group.query.get(group_id_arg)
            if linked_group:
                # Basic check: is current_user a member of the group?
                # membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=linked_group.id).first()
                # if not membership:
                #     flash('You are not a member of this group, cannot create poll for it.', 'danger')
                # else:
                form.group_id.data = group_id_arg
            else:
                flash('Linked group not found.', 'warning')

    if form.validate_on_submit():
        new_poll = Poll(question=form.question.data, user_id=current_user.id)

        # Process post_id and group_id from the form's hidden fields
        form_post_id = form.post_id.data
        form_group_id = form.group_id.data

        if form_post_id:
            # Re-verify post exists and user is authorized (e.g., author or group admin/member)
            post_check = Post.query.get(int(form_post_id))
            if post_check: # Add authorization checks if needed
                new_poll.post_id = int(form_post_id)
            else:
                flash('Invalid post ID linked to poll.', 'danger')
                # Need to reload context for rendering
                if form_group_id: linked_group = Group.query.get(int(form_group_id))
                return render_template('create_poll.html', title='Create Poll', form=form, linked_post=None, linked_group=linked_group)


        if form_group_id:
            # Re-verify group exists and user is authorized (e.g., member)
            group_check = Group.query.get(int(form_group_id))
            if group_check: # Add authorization checks if needed
                new_poll.group_id = int(form_group_id)
            else:
                flash('Invalid group ID linked to poll.', 'danger')
                # Need to reload context for rendering
                if form_post_id: linked_post = Post.query.get(int(form_post_id))
                return render_template('create_poll.html', title='Create Poll', form=form, linked_post=linked_post, linked_group=None)

        # Prevent linking to both a post and a group simultaneously if that's a business rule
        # For now, allowing both if data is provided, though UI might only provide one context.

        db.session.add(new_poll)
        db.session.flush() # Get new_poll.id for options

        for entry in form.options.entries:
            option_text = entry.form.option_text.data.strip()
            if option_text: # Only save options with actual text
                new_option = PollOption(poll_id=new_poll.id, option_text=option_text)
                db.session.add(new_option)

        db.session.commit() # This commits the poll and its options
        flash('Poll created successfully!', 'success')

        # --- Notification Logic Start ---
        if new_poll.group_id:
            group = Group.query.get(new_poll.group_id)
            if group:
                for membership in group.memberships:
                    member_user = membership.user
                    if member_user.id != current_user.id:
                        notification = Notification(
                            recipient_id=member_user.id,
                            actor_id=current_user.id,
                            type='new_group_poll',
                            related_group_id=group.id
                            # related_poll_id=new_poll.id # Would add this if model supported it
                        )
                        db.session.add(notification)
                        socketio.emit('new_notification', {
                            'message': f'New poll in group {group.name}: "{new_poll.question[:30]}{"..." if len(new_poll.question) > 30 else ""}"',
                            'type': 'new_group_poll',
                            'actor_username': current_user.username,
                            'group_id': group.id,
                            'group_name': group.name,
                            'poll_question': new_poll.question[:70] # Slightly longer for direct display
                        }, room=str(member_user.id))
        else: # Not a group poll, so notify followers (user poll)
            for follower in current_user.followers:
                # No need to check if follower.id != current_user.id, as one cannot follow oneself.
                notification = Notification(
                    recipient_id=follower.id,
                    actor_id=current_user.id,
                    type='new_user_poll',
                    related_post_id=new_poll.post_id if new_poll.post_id else None # Link to post if poll is tied to one
                    # related_poll_id=new_poll.id # Would add this if model supported it
                )
                db.session.add(notification)
                socketio.emit('new_notification', {
                    'message': f'{current_user.username} created a new poll: "{new_poll.question[:30]}{"..." if len(new_poll.question) > 30 else ""}"',
                    'type': 'new_user_poll',
                    'actor_username': current_user.username,
                    'poll_question': new_poll.question[:70] # Slightly longer for direct display
                    # 'post_id': new_poll.post_id if new_poll.post_id else None # Optional: if want to link to post
                }, room=str(follower.id))

        db.session.commit() # Commit notifications
        # --- Notification Logic End ---

        if new_poll.post_id:
            # Assuming a route like 'main.view_post' exists
            # return redirect(url_for('main.view_post', post_id=new_poll.post_id))
            # For now, redirect to index or a generic poll display page if that exists
            return redirect(url_for('main.index'))
        elif new_poll.group_id:
            return redirect(url_for('main.view_group', group_id=new_poll.group_id))
        else:
            return redirect(url_for('main.index')) # Fallback, or a dedicated page for the poll itself

    # If validation failed on POST, need to re-fetch context for template
    if request.method == 'POST' and not form.validate_on_submit():
        if form.post_id.data:
            linked_post = Post.query.get(int(form.post_id.data))
        if form.group_id.data:
            linked_group = Group.query.get(int(form.group_id.data))

    return render_template('create_poll.html', title='Create Poll', form=form, linked_post=linked_post, linked_group=linked_group)

@main.route('/poll/<int:poll_id>/vote', methods=['POST'])
@login_required
def vote_on_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    selected_option_id = request.form.get('option_id', type=int)

    # Default redirect location
    # Fallback to index, but try to redirect to where the poll was (post or group page)
    redirect_url = url_for('main.index')
    if poll.post_id:
        # Assuming a 'view_post' route exists that takes post_id
        # redirect_url = url_for('main.view_post', post_id=poll.post_id)
        pass # Placeholder, as view_post route is not defined yet. For now, will use request.referrer or index.
    elif poll.group_id:
        redirect_url = url_for('main.view_group', group_id=poll.group_id)

    # Prefer request.referrer if available and seems safe, otherwise use constructed URL
    # A more robust check for request.referrer might be needed in production (e.g., ensure it's on the same domain)
    # final_redirect_url = request.referrer or redirect_url # Not needed for pure AJAX JSON response

    if selected_option_id is None:
        # flash('Please select an option to vote.', 'warning') # Replaced by JSON
        return jsonify({'success': False, 'error': 'Please select an option to vote.'}), 400

    chosen_option = PollOption.query.get(selected_option_id)

    if not chosen_option or chosen_option.poll_id != poll.id:
        # flash('Invalid option selected.', 'danger') # Replaced by JSON
        return jsonify({'success': False, 'error': 'Invalid option selected.'}), 400

    existing_vote = PollVote.query.filter_by(user_id=current_user.id, poll_id=poll.id).first()
    message = ''
    status_changed = False

    if existing_vote:
        if existing_vote.option_id == chosen_option.id:
            message = 'You have already voted for this option.'
            # No change in DB, but still success in terms of receiving the vote
            return jsonify({'success': True, 'message': message, 'status_changed': status_changed})
        else:
            existing_vote.option_id = chosen_option.id
            db.session.commit()
            message = 'Your vote has been updated.'
            status_changed = True
    else:
        new_vote = PollVote(user_id=current_user.id, option_id=chosen_option.id, poll_id=poll.id)
        db.session.add(new_vote)
        db.session.commit()
        message = 'Your vote has been recorded.'
        status_changed = True

        # Optional: Notify poll creator about a new vote (if not self-vote)
        if poll.author.id != current_user.id:
            # Notification logic (as before, currently placeholder/skipped)
            pass

    return jsonify({'success': True, 'message': message, 'status_changed': status_changed})

# -------------------- Group Management Routes --------------------

@main.route('/group/<int:group_id>/manage', methods=['GET', 'POST'])
@login_required
def manage_group(group_id):
    group = Group.query.get_or_404(group_id)

    # Authorization: Check if current_user is an admin of the group
    membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=group.id).first()
    if not membership or membership.role != 'admin':
        flash('You are not authorized to manage this group.', 'danger')
        return redirect(url_for('main.view_group', group_id=group.id))

    form = GroupCreationForm(obj=group) # Reuse GroupCreationForm, pre-populate with group data for GET

    if form.validate_on_submit(): # This handles POST request for updating group details
        group.name = form.name.data
        group.description = form.description.data

        if form.image_file.data:
            # Delete old group image if it's not the default
            if group.image_file and group.image_file != 'default_group_pic.png':
                try:
                    old_image_path = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER_GROUP_IMAGES'], group.image_file)
                    if os.path.exists(old_image_path):
                        os.remove(old_image_path)
                except Exception as e:
                    current_app.logger.error(f"Error deleting old group image {group.image_file}: {e}")
                    flash('Error removing old group image.', 'warning')
            try:
                group.image_file = save_group_image(form.image_file.data)
            except Exception as e:
                current_app.logger.error(f"Error saving new group image: {e}")
                flash('An error occurred while uploading the new group image.', 'danger')
                # Fall through to render template with existing data if image save fails

        db.session.commit()
        flash('Group details updated successfully!', 'success')
        return redirect(url_for('main.manage_group', group_id=group.id))

    # For GET request, form is already pre-populated by obj=group
    # Fetch members for display
    members = group.memberships.all() # This gives GroupMembership objects

    # TODO: Create app/templates/manage_group.html in a later step
    return render_template('manage_group.html', title=f'Manage {group.name}', form=form, group=group, members=members)

@main.route('/group/<int:group_id>/remove_member/<int:user_id>', methods=['POST'])
@login_required
def remove_group_member(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    user_to_remove = User.query.get_or_404(user_id)

    # Authorization: Check if current_user is an admin of the group
    current_user_membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=group.id).first()
    if not current_user_membership or current_user_membership.role != 'admin':
        flash('You are not authorized to manage this group.', 'danger')
        return redirect(url_for('main.view_group', group_id=group.id))

    membership_to_delete = GroupMembership.query.filter_by(user_id=user_to_remove.id, group_id=group.id).first()

    if not membership_to_delete:
        flash(f'{user_to_remove.username} is not a member of this group.', 'info')
        return redirect(url_for('main.manage_group', group_id=group.id))

    # Prevent removing the group creator if they are the only admin
    if group.creator_id == user_to_remove.id:
        admins = GroupMembership.query.filter_by(group_id=group.id, role='admin').all()
        if len(admins) == 1 and admins[0].user_id == user_to_remove.id:
            flash('You cannot remove the group creator as they are the only admin. Designate another admin first or delete the group.', 'warning')
            return redirect(url_for('main.manage_group', group_id=group.id))

    # Prevent admin from removing themselves if they are the only admin (even if not creator)
    if current_user.id == user_to_remove.id and current_user_membership.role == 'admin':
        admins = GroupMembership.query.filter_by(group_id=group.id, role='admin').all()
        if len(admins) == 1:
            flash('You cannot remove yourself as you are the only admin. Designate another admin or delete the group.', 'warning')
            return redirect(url_for('main.manage_group', group_id=group.id))


    db.session.delete(membership_to_delete)
    db.session.commit()
    flash(f'{user_to_remove.username} has been removed from the group.', 'success')
    return redirect(url_for('main.manage_group', group_id=group.id))

@main.route('/group/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    group = Group.query.get_or_404(group_id)

    # Authorization: Check if current_user is an admin of the group
    # For group deletion, often only the creator or a super-admin might be allowed.
    # For now, any group admin can delete, but this could be restricted further (e.g., only creator).
    membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=group.id).first()
    if not membership or membership.role != 'admin': # or group.creator_id != current_user.id (if only creator can delete)
        flash('You are not authorized to delete this group.', 'danger')
        return redirect(url_for('main.view_group', group_id=group.id))

    # Handle Posts: Nullify their group_id
    # This needs to be done before deleting memberships if there are FK constraints or specific post handling logic.
    # However, since Post.group_id is nullable, and GroupMembership deletion is handled by cascade on Group deletion,
    # we can do this.
    for post in group.posts:
        post.group_id = None
    db.session.flush() # Apply post changes before group deletion

    # Delete Group Image (if not default)
    if group.image_file and group.image_file != 'default_group_pic.png':
        try:
            image_path = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER_GROUP_IMAGES'], group.image_file)
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            current_app.logger.error(f"Error deleting group image {group.image_file} during group deletion: {e}")
            # Non-critical, log and continue with group deletion

    # Delete the group. Associated GroupMemberships should be deleted by cascade.
    db.session.delete(group)
    db.session.commit()

    flash(f'Group "{group.name}" has been deleted successfully.', 'success')
    return redirect(url_for('main.index')) # Or a future groups listing page
