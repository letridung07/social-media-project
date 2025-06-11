import os # Ensure os is imported
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app # Ensure current_app is imported
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy import or_
from app import db, socketio # Import socketio
from app.forms import RegistrationForm, LoginForm, EditProfileForm, PostForm, CommentForm
from app.models import User, Post, Like, Comment, Notification, Conversation, ChatMessage # Import Notification, Conversation, ChatMessage
from app.utils import save_picture, save_post_image, save_post_video

main = Blueprint('main', __name__)

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
        post = Post(body=form.body.data, author=current_user, image_filename=image_filename_to_save, video_filename=video_filename_to_save)
        db.session.add(post)
        db.session.commit()
        flash('Your post is now live!', 'success')
        return redirect(url_for('main.index'))
    return render_template('create_post.html', title='Create Post', form=form)

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
        db.session.commit()
        flash('You liked the post!', 'success')

        # Notification and event for like
        if post.author.id != current_user.id:
            notification = Notification(
                recipient_id=post.author.id,
                actor_id=current_user.id,
                type='like',
                related_post_id=post.id
            )
            db.session.add(notification)
            db.session.commit()
            socketio.emit('new_notification',
                          {'message': f'{current_user.username} liked your post.', 'type': 'like', 'actor_username': current_user.username, 'post_id': post.id},
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
            db.session.commit()
            socketio.emit('new_notification',
                          {'message': f'{current_user.username} commented on your post.', 'type': 'comment', 'actor_username': current_user.username, 'post_id': post.id, 'comment_body': comment.body},
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
    # Optionally, mark notifications as read when they are viewed, or implement a separate mechanism.
    # For now, just fetch them.
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
