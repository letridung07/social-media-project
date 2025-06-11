import os # Ensure os is imported
import re # For hashtag parsing
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app # Ensure current_app is imported
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy import or_
from app import db, socketio # Import socketio
from app.forms import RegistrationForm, LoginForm, EditProfileForm, PostForm, CommentForm, ForgotPasswordForm, ResetPasswordForm # Import new forms
from app.models import User, Post, Like, Comment, Notification, Conversation, ChatMessage, Hashtag # Import Hashtag
from app.utils import save_picture, save_post_image, save_post_video
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

    return render_template('search_results.html',
                           title=f'Search Results for "{query}"' if query else 'Search',
                           query=query,
                           users=users_found,
                           posts=posts_found)


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
            alt_text=form.alt_text.data # <-- Add this line
        )
        db.session.add(post)
        # Process hashtags before committing the post
        process_hashtags(post.body, post)
        db.session.commit()
        flash('Your post is now live!', 'success')
        return redirect(url_for('main.index'))
    return render_template('create_post.html', title='Create Post', form=form)


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
