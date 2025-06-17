import os
import re # For hashtag parsing
from datetime import datetime, timezone
import os
import re # For hashtag parsing
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app, jsonify, make_response, session
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy import or_, func, and_
from flask_babel import lazy_gettext as _l, gettext
import io # For CSV export
import csv # For CSV export
from sqlalchemy.orm import joinedload # Import joinedload
from werkzeug.utils import secure_filename
from app import db, socketio, cache # Import cache
from app.core.forms import RegistrationForm, LoginForm, EditProfileForm, PostForm, CommentForm, ForgotPasswordForm, ResetPasswordForm, GroupCreationForm, StoryForm, PollForm, EventForm, FriendListForm, AddUserToFriendListForm, PRIVACY_CHOICES, ArticleForm, AudioPostForm, SubscriptionPlanForm, TOTPSetupForm, Verify2FAForm, Disable2FAForm, ConfirmPasswordAndTOTPForm # Added Disable2FAForm, ConfirmPasswordAndTOTPForm
from app.core.models import User, Post, MediaItem, Reaction, Comment, Notification, Conversation, ChatMessage, Hashtag, Group, GroupMembership, Story, Poll, PollOption, PollVote, followers, Event, UserAnalytics, Share, MessageReadStatus, Mention, PRIVACY_PUBLIC, PRIVACY_FOLLOWERS, PRIVACY_CUSTOM_LIST, PRIVACY_PRIVATE, FriendList, Article, AudioPost, SubscriptionPlan, UserSubscription, Bookmark # Like removed from import, Bookmark added
from app.utils.helpers import save_picture, save_group_image, save_story_media, process_mentions, get_historical_engagement, get_top_performing_hashtags, get_top_performing_groups, save_media_file, slugify, save_audio_file, get_audio_duration, process_hashtags # Added process_hashtags
from app.utils.email import send_password_reset_email # Import email utility
import pyotp
import qrcode
import io
import base64
import json
from passlib.hash import sha256_crypt
import secrets # For slug generation
from wtforms.validators import DataRequired # For dynamic validator modification
from app.utils.helpers import generate_ics_file, subscription_required # For ICS export
import stripe # For Stripe integration

# Import for recommendations
from app.utils.helpers import get_recommendations

# Ensure these specific imports are present for set_theme_preference, though some might be redundant if already imported broadly.
from flask import request, jsonify, current_app # request, jsonify, current_app
from flask_login import current_user, login_required # current_user, login_required
from app import db # db
# from app.core.models import User # User model is typically imported with other models
import time # For rate limiting

main = Blueprint('main', __name__)

# Constants for login rate limiting
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_PERIOD_SECONDS = 300 # 5 minutes

# Global dictionary to store failed login attempts
# Structure: {'ip_address': {'attempts': count, 'lockout_until': timestamp}}
failed_login_attempts = {}

LIKE_MILESTONES = [10, 50, 100, 250, 500, 1000]

# Cache key generation function for user-specific caching
def make_user_specific_cache_key(*args, **kwargs):
    path = request.path
    user_id_part = str(current_user.id) if current_user.is_authenticated and not current_user.is_anonymous else 'anonymous'
    # Include query arguments for routes that might use them and need to be cached differently
    query_args_part = str(hash(frozenset(request.args.items())))
    return (path + '_' + user_id_part + '_' + query_args_part).encode('utf-8')

@main.route('/')
@main.route('/index')
@cache.cached(timeout=300, make_cache_key=make_user_specific_cache_key, unless=lambda: current_user.is_authenticated) # Cache for anonymous users
def index():
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('POSTS_PER_PAGE', 10)
    posts_pagination = None # Initialize to None

    if current_user.is_authenticated:
        followed_user_ids = [user.id for user in current_user.followed]

        # Condition for posts from others (followed, public, or custom list they are part of)
        # These must be published.
        others_posts_condition = and_(
            Post.is_published == True,
            or_(
                and_( # Posts from followed users
                    Post.user_id.in_(followed_user_ids),
                    or_(
                        Post.privacy_level == PRIVACY_PUBLIC,
                        Post.privacy_level == PRIVACY_FOLLOWERS
                    )
                ),
                and_( # Posts from ANY user shared with a custom list current_user is on
                    Post.privacy_level == PRIVACY_CUSTOM_LIST,
                    Post.custom_friend_list_id.isnot(None),
                    Post.custom_friend_list.has(
                        FriendList.members.any(User.id == current_user.id)
                    )
                ),
                Post.privacy_level == PRIVACY_PUBLIC # Public posts from anyone not followed
            )
        )

        # Condition for user's own posts (published or scheduled)
        own_posts_condition = and_(Post.user_id == current_user.id)

        posts_query = Post.query.filter(
            or_(
                others_posts_condition,
                own_posts_condition
            )
        ).distinct().order_by(Post.timestamp.desc())

        posts_pagination = db.paginate(posts_query, page=page, per_page=per_page, error_out=False)
        posts = posts_pagination.items
    else:
        # Public feed for guests (e.g., most recent posts from all users)
        # Only show published posts
        posts_query = Post.query.filter(Post.privacy_level == PRIVACY_PUBLIC, Post.is_published == True).order_by(Post.timestamp.desc())
        posts_pagination = db.paginate(posts_query, page=page, per_page=per_page, error_out=False)
        posts = posts_pagination.items

    comment_form = CommentForm()
    return render_template('index.html', title=_l('Home'), posts=posts, comment_form=comment_form, pagination=posts_pagination)


from app.core.models import post_hashtags # For hashtag popularity sort

@main.route('/search')
# Apply user-specific caching to search results if query_term is present OR if recommendations are shown
@cache.cached(timeout=120, make_cache_key=make_user_specific_cache_key,
              unless=lambda: not request.args.get('q', '').strip() and not (current_user.is_authenticated and not request.args.get('q', '').strip()))
def search():
    query_term = request.args.get('q', '').strip()
    category = request.args.get('category', 'all').lower()
    sort_by = request.args.get('sort_by', 'relevance').lower()

    recommendations = None
    if not query_term and current_user.is_authenticated:
        recommendations = get_recommendations(current_user.id)

    users_found, posts_found, groups_found, hashtags_found = [], [], [], []

    if query_term:
        # Users Search
        if category == 'all' or category == 'users':
            user_q = User.query.filter(or_(User.username.ilike(f'%{query_term}%'), User.email.ilike(f'%{query_term}%')))
            if current_user.is_authenticated:
                user_q = user_q.filter(
                    or_(
                        User.id == current_user.id, # Own profile
                        User.profile_visibility == PRIVACY_PUBLIC,
                        # Check if current_user is a follower of the User being searched
                        and_(User.profile_visibility == PRIVACY_FOLLOWERS, User.followers.any(User.id == current_user.id))
                    )
                )
            else: # Unauthenticated user
                user_q = user_q.filter(User.profile_visibility == PRIVACY_PUBLIC)
            if sort_by == 'popularity':
                user_q = user_q.outerjoin(followers, User.id == followers.c.followed_id)\
                               .group_by(User.id)\
                               .order_by(func.count(followers.c.follower_id).desc(), User.username.asc())
            elif sort_by == 'date':
                user_q = user_q.order_by(User.id.desc())
            else:
                user_q = user_q.order_by(User.username.asc())
            users_found = user_q.all()

        # Posts Search
        if category == 'all' or category == 'posts':
            post_q = Post.query.filter(Post.body.ilike(f'%{query_term}%'))
            if current_user.is_authenticated:
                # Define followed_ids_for_search if not already in scope
                followed_ids_for_search = [u.id for u in current_user.followed]
                post_q = post_q.filter(
                    or_(
                        Post.user_id == current_user.id, # Own posts
                        Post.privacy_level == PRIVACY_PUBLIC,
                        and_(Post.privacy_level == PRIVACY_FOLLOWERS, Post.user_id.in_(followed_ids_for_search)),
                        and_( # Posts matching search term shared via a custom list current_user is on
                            Post.privacy_level == PRIVACY_CUSTOM_LIST,
                            Post.custom_friend_list_id.isnot(None),
                            Post.custom_friend_list.has(
                                FriendList.members.any(User.id == current_user.id)
                            )
                        )
                    )
                ).distinct() # Added distinct()
            else: # Unauthenticated user
                post_q = post_q.filter(Post.privacy_level == PRIVACY_PUBLIC)
            if sort_by == 'date':
                post_q = post_q.order_by(Post.timestamp.desc())
            elif sort_by == 'popularity':
                # Updated to join with Reaction model, specifically counting 'like' reactions for popularity
                post_q = post_q.outerjoin(Post.reactions.and_(Reaction.reaction_type == 'like')).outerjoin(Post.comments)\
                               .group_by(Post.id)\
                               .order_by((func.coalesce(func.count(Reaction.id), 0) + func.coalesce(func.count(Comment.id), 0)).desc(), Post.timestamp.desc())
            else:
                post_q = post_q.order_by(Post.timestamp.desc())
            posts_found = post_q.all()

        # Groups Search
        if category == 'all' or category == 'groups':
            group_q = Group.query.filter(or_(Group.name.ilike(f'%{query_term}%'), Group.description.ilike(f'%{query_term}%')))
            if sort_by == 'date':
                group_q = group_q.order_by(Group.created_at.desc())
            elif sort_by == 'popularity':
                group_q = group_q.outerjoin(GroupMembership)\
                                 .group_by(Group.id)\
                                 .order_by(func.count(GroupMembership.id).desc(), Group.name.asc())
            else:
                group_q = group_q.order_by(Group.name.asc())
            groups_found = group_q.all()

        # Hashtags Search
        if category == 'all' or category == 'hashtags':
            hashtag_q = Hashtag.query.filter(Hashtag.tag_text.ilike(f'%{query_term}%'))
            if sort_by == 'popularity':
                hashtag_q = hashtag_q.outerjoin(post_hashtags, Hashtag.id == post_hashtags.c.hashtag_id)\
                                     .group_by(Hashtag.id)\
                                     .order_by(func.count(post_hashtags.c.post_id).desc(), Hashtag.tag_text.asc())
            elif sort_by == 'date':
                hashtag_q = hashtag_q.order_by(Hashtag.tag_text.asc())
            else:
                hashtag_q = hashtag_q.order_by(Hashtag.tag_text.asc())
            hashtags_found = hashtag_q.all()

    # Title Logic
    final_title = ""
    if not query_term and recommendations and \
       (recommendations.get('posts') or recommendations.get('users') or recommendations.get('groups')):
        final_title = 'Recommended for You'
    else:
        temp_title_parts = []
        if query_term:
            temp_title_parts.append(_l('Results for "%(query)s"', query=query_term))
            if category != 'all':
                temp_title_parts.append(_l('in %(category)s', category=category.capitalize()))
            if sort_by != 'relevance':
                temp_title_parts.append(_l('sorted by %(sort_by)s', sort_by=sort_by.capitalize()))

        if temp_title_parts:
            final_title = " ".join(temp_title_parts)
        elif recommendations:
             final_title = _l('Recommended for You')
        else:
            final_title = _l('Search')

    comment_form = CommentForm()

    return render_template('search_results.html',
                           title=final_title,
                           query=query_term,
                           users=users_found,
                           posts=posts_found,
                           groups=groups_found,
                           hashtags=hashtags_found,
                           selected_category=category,
                           selected_sort_by=sort_by,
                           recommendations=recommendations,
                           comment_form=comment_form)


@main.route('/search/recommendations')
@login_required
@cache.cached(timeout=600, make_cache_key=make_user_specific_cache_key, unless=lambda: current_user.is_anonymous)
def search_recommendations():
    """
    Provides personalized recommendations for the current user.
    Returns data in JSON format.
    """
    if current_user.is_anonymous: # Should be caught by @login_required but good for safety with cache
        return jsonify({'error': _l('Authentication required.')}), 401

    recommendations = get_recommendations(current_user.id)

    # Serialize recommendations
    rec_posts = []
    for post in recommendations.get('posts', []):
        rec_posts.append({
            'id': post.id,
            'body': post.body,
            'author_username': post.author.username if post.author else 'Unknown',
            'author_profile_pic': post.author.profile_picture_url if post.author else url_for('static', filename='images/default_profile_pic.png'),
            'image_filename': post.image_filename,
            'video_filename': post.video_filename,
            'alt_text': post.alt_text,
            'timestamp': post.timestamp.isoformat() if post.timestamp else None,
            'group_id': post.group_id,
            'group_name': post.group.name if post.group else None, # Add group name
            'user_id': post.user_id,
            'like_count': post.reaction_count('like'), # Updated to use reaction_count for 'like'
            'comment_count': post.comments.count(), # Assuming Comment model has direct count or a method like post.comments.count()
            'url': url_for('main.view_post_page', post_id=post.id) if hasattr(main, 'view_post_page') else '#' # Placeholder for post view URL
        })

    rec_users = []
    for user_obj in recommendations.get('users', []):
        rec_users.append({
            'id': user_obj.id,
            'username': user_obj.username,
            'bio': user_obj.bio,
            'profile_picture_url': user_obj.profile_picture_url or url_for('static', filename='images/default_profile_pic.png'),
            'follower_count': user_obj.followers.count(), # Add follower count
            'is_following': current_user.is_following(user_obj) if current_user.is_authenticated else False, # Check if current user is following
            'profile_url': url_for('main.profile', username=user_obj.username)
        })

    rec_groups = []
    for group_obj in recommendations.get('groups', []):
        rec_groups.append({
            'id': group_obj.id,
            'name': group_obj.name,
            'description': group_obj.description,
            'image_file': group_obj.image_file or url_for('static', filename='images/default_group_pic.png'),
            'member_count': group_obj.memberships.count(), # Add member count
            'is_member': current_user.is_member_of(group_obj.id) if current_user.is_authenticated else False, # Check if current user is a member
            'group_url': url_for('main.view_group', group_id=group_obj.id)
        })

    serialized_recommendations = {
        'posts': rec_posts,
        'users': rec_users,
        'groups': rec_groups
    }
    return jsonify(serialized_recommendations)

@main.route('/users/search_mentions')
@login_required
def search_mentions_for_autocomplete():
    query = request.args.get('q', '', type=str)
    results = []
    if query and len(query) >= 1: # Require at least 1 char for query
        # Search for users where username starts with the query (case-insensitive)
        users = User.query.filter(User.username.ilike(f"{query}%")).limit(10).all()
        for user in users:
            results.append({
                'username': user.username,
                # Construct profile picture URL safely
                'profile_picture_url': url_for('static', filename=f'images/{user.profile_picture_url if user.profile_picture_url else "default_profile_pic.png"}')
            })
    return jsonify({'users': results})


@main.route('/hashtag/<string:tag_text>')
def hashtag_feed(tag_text):
    normalized_tag_text = tag_text.lower()
    hashtag = Hashtag.query.filter_by(tag_text=normalized_tag_text).first()
    posts = []
    title = _l('No posts found for #%(tag)s', tag=normalized_tag_text)

    if hashtag:
        # Only show published posts in hashtag feeds
        posts = hashtag.posts.filter(Post.is_published == True).order_by(Post.timestamp.desc()).all()
        title = _l('Posts tagged #%(tag)s', tag=hashtag.tag_text)
        if not posts: # Hashtag exists but no posts are associated or published
             title = _l('No published posts found for #%(tag)s', tag=hashtag.tag_text)
    # else: title remains "No posts found..."

    return render_template('hashtag_feed.html', title=title, hashtag=hashtag, posts=posts, query=normalized_tag_text) # pass normalized


import random

@main.route('/trending_hashtags')
def trending_hashtags():
    all_hashtags = Hashtag.query.all()
    if len(all_hashtags) > 10:
        trending = random.sample(all_hashtags, 10)
    else:
        trending = all_hashtags
    return render_template('trending_hashtags.html', title=_l("Trending Hashtags"), hashtags=trending)


@main.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(_l('Congratulations, you are now a registered user!'), 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html', title=_l('Register'), form=form)

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    now = time.time()

    # Check if IP is currently locked out
    if ip_address in failed_login_attempts:
        attempt_info = failed_login_attempts[ip_address]
        if attempt_info.get('lockout_until', 0) > now:
            remaining_lockout = int(attempt_info['lockout_until'] - now)
            flash(_l('Too many failed login attempts. Please try again in %(seconds)s seconds.', seconds=remaining_lockout), 'danger')
            return redirect(url_for('main.login')) # Redirect to GET to show the flash message
        # If lockout has expired, clear old lockout_until but keep attempts if relevant, or reset fully.
        # For simplicity, we'll let a successful login clear it, or a new failed attempt re-evaluate.

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            # Successful login
            if ip_address in failed_login_attempts:
                failed_login_attempts.pop(ip_address, None) # Clear any previous failed attempts for this IP

            if user.otp_enabled:
                session['user_id_for_2fa'] = user.id
                session['remember_me_for_2fa'] = form.remember_me.data
                next_page_for_2fa = request.args.get('next')
                if next_page_for_2fa:
                    session['next_page_for_2fa'] = next_page_for_2fa
                else:
                    session.pop('next_page_for_2fa', None)
                return redirect(url_for('main.verify_2fa'))
            else:
                login_user(user, remember=form.remember_me.data)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('main.index'))
        else:
            # Failed login attempt
            current_app.logger.warning(f"Failed login attempt for email '{form.email.data}' from IP: {ip_address}")

            if ip_address not in failed_login_attempts:
                failed_login_attempts[ip_address] = {'attempts': 0, 'lockout_until': 0}

            attempt_info = failed_login_attempts[ip_address]
            # Ensure lockout_until is not in the future before incrementing if it's an old record
            if attempt_info.get('lockout_until', 0) > now:
                 remaining_lockout = int(attempt_info['lockout_until'] - now)
                 flash(_l('Too many failed login attempts. Please try again in %(seconds)s seconds.', seconds=remaining_lockout), 'danger')
                 return render_template('login.html', title=_l('Sign In'), form=form)


            attempt_info['attempts'] += 1

            if attempt_info['attempts'] >= MAX_FAILED_LOGIN_ATTEMPTS:
                attempt_info['lockout_until'] = now + LOGIN_LOCKOUT_PERIOD_SECONDS
                # Reset attempts count after locking out, or it will stay high
                # attempt_info['attempts'] = 0 # Or keep it to show they hit the max
                flash(_l('Too many failed login attempts. Your account has been locked for %(minutes)s minutes.', minutes=int(LOGIN_LOCKOUT_PERIOD_SECONDS/60)), 'danger')
            else:
                remaining_attempts = MAX_FAILED_LOGIN_ATTEMPTS - attempt_info['attempts']
                flash(_l('Login Unsuccessful. Please check email and password. You have %(attempts)s attempts remaining.', attempts=remaining_attempts), 'danger')

            failed_login_attempts[ip_address] = attempt_info # Ensure dictionary is updated
            return render_template('login.html', title=_l('Sign In'), form=form) # Re-render form with error

    # For GET request, also check lockout status in case user refreshes page
    if request.method == 'GET' and ip_address in failed_login_attempts:
        attempt_info = failed_login_attempts[ip_address]
        if attempt_info.get('lockout_until', 0) > now:
            remaining_lockout = int(attempt_info['lockout_until'] - now)
            flash(_l('Too many failed login attempts. Please try again in %(seconds)s seconds.', seconds=remaining_lockout), 'danger')
            # No redirect here, just let the template render with the message

    return render_template('login.html', title=_l('Sign In'), form=form)

@main.route('/logout')
def logout():
    logout_user()
    flash(_l('You have been logged out.'), 'info')
    return redirect(url_for('main.index'))

@main.route('/language/<lang_code>')
def set_language(lang_code):
    if lang_code in current_app.config['LANGUAGES']:
        session['language'] = lang_code
        refresh() # Refresh Babel translations for the current request
        flash(_l('Language changed to %(language)s.', language=current_app.config['LANGUAGES'][lang_code]), 'success')
    else:
        flash(_l('Invalid language selected.'), 'warning')

    # Try to redirect to the previous page, otherwise to index
    # Using request.referrer requires careful validation in production to avoid open redirect vulnerabilities
    # For simplicity, redirecting to index or a safe default.
    # A more robust solution might store the intended target URL in session before redirecting to language change.
    referrer = request.referrer
    if referrer and url_for('main.set_language', lang_code=lang_code, _external=False) in referrer: # Avoid self-referral loop
        return redirect(url_for('main.index'))

    # Basic check to prevent open redirect, ensure it's a local URL
    # This check is very basic. A more robust check would parse the URL.
    if referrer and referrer.startswith(request.host_url):
         return redirect(referrer)
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
                flash(_l('An email has been sent with instructions to reset your password.'), 'info')
            else:
                flash(_l('There was an issue sending the password reset email. Please try again later or contact support.'), 'danger')
        else:
            # Generic message for security (doesn't reveal if email exists or not)
            # flash(_l('If an account with that email exists, a password reset link has been sent.'), 'info')
            # To avoid user confusion if email sending fails, it's better to give the success message always here
            # as the email sending failure is already handled above by a more specific error.
            # However, for strict security against user enumeration, the generic message is preferred.
            # Let's stick to the more user-friendly approach for now, assuming logger captures send errors.
             flash(_l('If an account with that email exists, instructions to reset your password have been sent.'), 'info')
        return redirect(url_for('main.login'))
    return render_template('forgot_password.html', title=_l('Forgot Password'), form=form)


@main.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.verify_reset_password_token(token)
    if not user:
        flash(_l('That is an invalid or expired token.'), 'warning')
        return redirect(url_for('main.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(_l('Your password has been updated! You are now able to log in.'), 'success')
        return redirect(url_for('main.login'))

    return render_template('reset_password_form.html', title=_l('Reset Password'), form=form, token=token)


@main.route('/user/<username>')
# @cache.cached(timeout=3600, make_cache_key=make_user_specific_cache_key) # Removed for privacy refactor
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    comment_form = CommentForm() # Instantiate the form

    profile_is_private = False
    profile_is_limited = False

    if user.id != getattr(current_user, 'id', None): # Not viewing own profile
        if user.profile_visibility == PRIVACY_PRIVATE:
            flash(_l("%(username)s's profile is private.", username=user.username), "info")
            profile_is_private = True # Flag for template
            # posts = [] # Ensure no posts are passed if profile is fully private to others
        elif user.profile_visibility == PRIVACY_FOLLOWERS:
            if not current_user.is_authenticated or not current_user.is_following(user):
                flash(_l("%(username)s's profile is visible only to followers.", username=user.username), "info")
                profile_is_limited = True # Flag for template
                # posts = [] # Ensure no posts are passed if profile is limited

    # Pass flags to template. Modify the render_template call at the end of the route:
    # return render_template('profile.html', ..., profile_is_private=profile_is_private, profile_is_limited=profile_is_limited)

    posts_query = user.posts.order_by(Post.timestamp.desc())

    # If profile is fully private to this viewer, no need to query posts.
    if profile_is_private:
        posts = []
    elif getattr(current_user, 'id', None) == user.id: # Viewing own profile - show all (published and scheduled)
        posts = posts_query.all() # No is_published filter needed for own profile
    else: # Viewing another user's profile (and it's not fully private)
        # Base filter for published posts
        q_filters = [Post.is_published == True]

        # Add privacy level filters for published posts
        privacy_options = [Post.privacy_level == PRIVACY_PUBLIC]
        if current_user.is_authenticated and current_user.is_following(user):
            privacy_options.append(Post.privacy_level == PRIVACY_FOLLOWERS)

        if current_user.is_authenticated:
            privacy_options.append(
                and_(
                    Post.privacy_level == PRIVACY_CUSTOM_LIST,
                    Post.custom_friend_list_id.isnot(None),
                    Post.user_id == user.id,
                    Post.custom_friend_list.has(
                        FriendList.members.any(User.id == current_user.id)
                    )
                )
            )

        q_filters.append(or_(*privacy_options))
        posts_query = posts_query.filter(and_(*q_filters))
        posts = posts_query.distinct().all()

        if profile_is_limited:
             posts = []

    # Fetch equipped virtual goods
    equipped_badge = None
    equipped_frame = None
    equipped_items_error = None
    try:
        # Ensure UserVirtualGood and VirtualGood models are imported
        # from app.models import UserVirtualGood, VirtualGood (already handled at top)
        # from sqlalchemy.exc import SQLAlchemyError (already handled at top)
        # from sqlalchemy.orm import joinedload (already handled at top)

        equipped_items = UserVirtualGood.query.filter_by(user_id=user.id, is_equipped=True)\
                                             .options(joinedload(UserVirtualGood.virtual_good)).all()
        for item in equipped_items:
            if item.virtual_good:
                if item.virtual_good.type == 'badge' and not equipped_badge:
                    equipped_badge = item
                elif item.virtual_good.type == 'profile_frame' and not equipped_frame:
                    equipped_frame = item
                if equipped_badge and equipped_frame: # Optimization: stop if both found
                    break
    except SQLAlchemyError as e:
        current_app.logger.error(f"Error fetching equipped virtual goods for {username}: {e}")
        equipped_items_error = "Could not load equipped items due to a database issue."
    except Exception as e: # Catch any other unexpected errors during the query or processing
        current_app.logger.error(f"Unexpected error fetching equipped virtual goods for {username}: {e}")
        equipped_items_error = "An unexpected error occurred while loading equipped items."


    return render_template('profile.html', title=f"{user.username}'s Profile", user=user, posts=posts,
                           comment_form=comment_form, profile_is_private=profile_is_private,
                           profile_is_limited=profile_is_limited,
                           equipped_badge=equipped_badge, equipped_frame=equipped_frame,
                           equipped_items_error=equipped_items_error)

@main.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(obj=current_user) # Pre-populate form with current_user data for GET
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
                        # flash(_l('Old profile picture removed.'), 'info') # Optional feedback
                except Exception as e:
                    current_app.logger.error(f"Error deleting old profile picture {old_picture_url}: {e}")
                    # flash(_l('Error removing old profile picture.'), 'warning') # Optional feedback
            current_user.profile_picture_url = picture_file

        current_user.bio = form.bio.data
        current_user.theme_preference = form.theme.data # Save theme preference
        current_user.profile_visibility = form.profile_visibility.data
        current_user.default_post_privacy = form.default_post_privacy.data
        current_user.default_story_privacy = form.default_story_privacy.data

        db.session.commit()
        # Invalidate cache for the profile page of the current user
        cache.delete_key(make_user_specific_cache_key(request_path=url_for('main.profile', username=current_user.username)))
        flash(_l('Your profile has been updated!'), 'success')
        return redirect(url_for('main.profile', username=current_user.username))
    elif request.method == 'GET':
        form.bio.data = current_user.bio # Already handled by obj=current_user for WTForms-Alchemy
        form.theme.data = current_user.theme_preference or 'default' # Populate theme for GET
        # The profile picture field is not pre-filled.
    return render_template('edit_profile.html', title=_l('Edit Profile'), form=form)


@main.route('/2fa/verify', methods=['GET', 'POST'])
def verify_2fa():
    if 'user_id_for_2fa' not in session:
        flash('2FA process not initiated. Please login first.', 'warning')
        return redirect(url_for('main.login'))

    user_id = session['user_id_for_2fa']
    user = User.query.get(user_id)

    if not user:
        flash('User not found. Please try logging in again.', 'danger')
        session.pop('user_id_for_2fa', None)
        session.pop('remember_me_for_2fa', None)
        session.pop('next_page_for_2fa', None)
        return redirect(url_for('main.login'))

    form = Verify2FAForm()
    if form.validate_on_submit():
        submitted_code = form.code.data
        totp_verifier = pyotp.TOTP(user.otp_secret)

        verified = False
        # Try verifying as TOTP
        if totp_verifier.verify(submitted_code):
            verified = True
        else:
            # Try verifying as backup code
            if user.otp_backup_codes:
                hashed_backup_codes = json.loads(user.otp_backup_codes)
                remaining_hashed_codes = []
                for hashed_code in hashed_backup_codes:
                    if sha256_crypt.verify(submitted_code, hashed_code):
                        verified = True
                        # Backup code used, do not add it back to remaining_hashed_codes
                        flash('Backup code used. Remember to generate new codes if you run low.', 'info')
                        continue # Skip adding this code back
                    remaining_hashed_codes.append(hashed_code)

                if verified:
                    user.otp_backup_codes = json.dumps(remaining_hashed_codes)
                    # db.session.commit() # Commit will happen with login_user or at end of request

        if verified:
            remember_me = session.get('remember_me_for_2fa', False)
            login_user(user, remember=remember_me)

            next_page = session.get('next_page_for_2fa') or url_for('main.index')

            # Clear 2FA session variables
            session.pop('user_id_for_2fa', None)
            session.pop('remember_me_for_2fa', None)
            session.pop('next_page_for_2fa', None)

            flash('Successfully logged in.', 'success')
            return redirect(next_page)
        else:
            flash('Invalid verification code.', 'danger')
            # Potentially add rate limiting here in a real application

    return render_template('2fa_verify.html', title='Verify 2FA', form=form)


@main.route('/2fa/setup', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if current_user.otp_enabled:
        flash('Two-factor authentication is already enabled.', 'info')
        return redirect(url_for('main.profile', username=current_user.username)) # Or a dedicated manage_2fa page

    form = TOTPSetupForm()

    # Generate new secret and backup codes for GET request or if POST validation fails and needs re-display
    # Store them temporarily in session to use during POST validation, rather than re-generating on failed POST
    if 'otp_secret_temp' not in session:
        session['otp_secret_temp'] = pyotp.random_base32()

    otp_secret_key = session['otp_secret_temp']

    # Generate backup codes only if not already generated and stored in session for this setup attempt
    if 'backup_codes_temp' not in session:
        unhashed_backup_codes = [secrets.token_hex(8) for _ in range(10)] # 10 codes, 16 chars each
        session['backup_codes_temp'] = unhashed_backup_codes
    else:
        unhashed_backup_codes = session['backup_codes_temp']

    if form.validate_on_submit():
        totp_code = form.totp_code.data
        # Use the secret from the session for verification
        totp_verifier = pyotp.TOTP(otp_secret_key)
        if totp_verifier.verify(totp_code):
            current_user.otp_secret = otp_secret_key
            current_user.otp_enabled = True

            # Hash and store backup codes
            hashed_backup_codes = [sha256_crypt.hash(code) for code in unhashed_backup_codes]
            current_user.otp_backup_codes = json.dumps(hashed_backup_codes)

            db.session.commit()

            # Clear temporary session data
            session.pop('otp_secret_temp', None)
            session.pop('backup_codes_temp', None)

            flash('Two-factor authentication enabled successfully! Make sure you have saved your backup codes.', 'success')
            return redirect(url_for('main.profile', username=current_user.username)) # Or a dedicated success/manage page
        else:
            flash('Invalid authenticator code. Please try again.', 'danger')
            # QR and backup codes will be re-displayed using session data
            # No need to re-generate QR image data if secret hasn't changed.

    # For GET request or if POST fails:
    provisioning_uri = pyotp.totp.TOTP(otp_secret_key).provisioning_uri(
        name=current_user.email,  # Use email or username
        issuer_name=current_app.config.get('APP_NAME', 'YourAppName') # Consider adding APP_NAME to config
    )

    # Generate QR code image
    qr_img = qrcode.make(provisioning_uri)
    buffered = io.BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_code_image_data = base64.b64encode(buffered.getvalue()).decode('utf-8')

    return render_template('2fa_setup.html', title='Setup 2FA', form=form,
                           otp_secret_key=otp_secret_key,
                           qr_code_image_data=qr_code_image_data,
                           backup_codes=unhashed_backup_codes)


@main.route('/2fa/disable', methods=['GET', 'POST'])
@login_required
def disable_2fa():
    if not current_user.otp_enabled:
        flash('Two-factor authentication is not currently enabled.', 'info')
        return redirect(url_for('main.edit_profile')) # Or main.profile

    form = Disable2FAForm()
    if form.validate_on_submit():
        if current_user.check_password(form.password.data):
            totp_verifier = pyotp.TOTP(current_user.otp_secret)
            if totp_verifier.verify(form.totp_code.data):
                current_user.otp_enabled = False
                current_user.otp_secret = None
                current_user.otp_backup_codes = None
                db.session.commit()
                flash('Two-factor authentication has been disabled.', 'success')
                return redirect(url_for('main.edit_profile')) # Or main.profile
            else:
                flash('Invalid authenticator code.', 'danger')
        else:
            flash('Incorrect password.', 'danger')
    return render_template('disable_2fa.html', title='Disable 2FA', form=form) # New template needed

@main.route('/2fa/manage_backup_codes', methods=['GET', 'POST'])
@login_required
def manage_backup_codes():
    if not current_user.otp_enabled:
        flash('Two-factor authentication is not enabled. Cannot manage backup codes.', 'warning')
        return redirect(url_for('main.edit_profile'))

    form = ConfirmPasswordAndTOTPForm()
    if form.validate_on_submit():
        if current_user.check_password(form.password.data):
            totp_verifier = pyotp.TOTP(current_user.otp_secret)
            if totp_verifier.verify(form.totp_code.data):
                # Logic to regenerate or simply re-display existing UNHASHED codes.
                # For simplicity, we'll re-generate new ones here.
                # This means the user needs to save them again.
                new_unhashed_backup_codes = [secrets.token_hex(8) for _ in range(10)]
                hashed_backup_codes = [sha256_crypt.hash(code) for code in new_unhashed_backup_codes]
                current_user.otp_backup_codes = json.dumps(hashed_backup_codes)
                db.session.commit()
                flash('New backup codes generated. Please save them securely. Your old codes are now invalid.', 'success')
                # It's crucial to show these new_unhashed_backup_codes to the user ONCE.
                # We can pass them to a template that shows them, or flash them (less secure for copy-paste).
                # For this example, let's assume a template part will show them.
                return render_template('manage_backup_codes.html', title='Manage Backup Codes', form=form, new_backup_codes=new_unhashed_backup_codes, codes_generated=True)
            else:
                flash('Invalid authenticator code.', 'danger')
        else:
            flash('Incorrect password.', 'danger')

    # For GET request, or if POST validation fails before identity is confirmed
    return render_template('manage_backup_codes.html', title='Manage Backup Codes', form=form, codes_generated=False)


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

    # Populate choices for custom_friend_list_id
    form.custom_friend_list_id.choices = [(fl.id, fl.name) for fl in current_user.friend_lists.all()]

    if form.validate_on_submit():
        # Validate custom_friend_list_id if PRIVACY_CUSTOM_LIST is chosen
        if form.privacy_level.data == PRIVACY_CUSTOM_LIST and not form.custom_friend_list_id.data:
            flash('Please select a friend list when choosing "Custom List" visibility.', 'warning')
            return render_template('create_post.html', title='Create Post', form=form, group_id=group_id_param, group_name=group_name_for_template)

        scheduled_for_value = None
        is_published_value = True # Default to immediate publish

        if form.schedule_time.data:
            # form.schedule_time.data is naive, from DateTimeField
            # Compare with naive datetime.now() as per validator logic
            if form.schedule_time.data > datetime.now():
                # TODO: Convert form.schedule_time.data (user's local time) to UTC before storing.
                # This is critical for the scheduler to work correctly if server timezone != user timezone.
                # Example: scheduled_for_value = user_local_to_utc(form.schedule_time.data)
                # For now, we assign the naive datetime directly.
                scheduled_for_value = form.schedule_time.data
                is_published_value = False
                # Flash message for scheduling is now handled based on is_published_value at the end
            else:
                # If validation passed (e.g. future time) but time is now in past (e.g. due to server delay in processing), publish immediately
                flash('Scheduled time is in the past. Publishing post now.', 'warning')
                # is_published_value remains True, scheduled_for_value remains None

        post = Post(
            body=form.body.data, # Body now serves as caption for the album
            author=current_user,
            privacy_level=form.privacy_level.data,
            custom_friend_list_id=form.custom_friend_list_id.data if form.privacy_level.data == PRIVACY_CUSTOM_LIST else None,
            scheduled_for=scheduled_for_value,
            is_published=is_published_value
        )

        if target_group:
            post.group_id = target_group.id

        db.session.add(post)
        # Important: Commit post here if MediaItems need post.id immediately and are added in the same transaction scope.
        # Or, add MediaItems to session and commit all at once.
        # For simplicity, let's add post, then media items, then commit all.
        # If post.id is needed for file paths *before* commit, then flush or commit post first.
        # Assuming save_media_file doesn't strictly need post.id in path (e.g., uses temp names or UUIDs)
        # or that media items are associated after post gets an ID.

        # Process and save media files
        upload_folder = current_app.config.get('MEDIA_ITEMS_UPLOAD_FOLDER', 'static/media_items')
        media_items_to_add = []
        if form.media_files.data:
            for file_storage in form.media_files.data:
                if file_storage and file_storage.filename: # Check if FileStorage object is not empty
                    try:
                        # secure_filename is good practice, though WTForms FileField might do some sanitization.
                        # save_media_file should handle the actual saving and return (filename, media_type)
                        filename, media_type = save_media_file(file_storage, upload_folder)
                        media_item = MediaItem(
                            post_parent=post, # Associate with the post
                            filename=filename,
                            media_type=media_type,
                            alt_text=None # Alt text per item can be added later if needed
                        )
                        media_items_to_add.append(media_item)
                    except Exception as e:
                        current_app.logger.error(f"Media file upload error: {e} for file {secure_filename(file_storage.filename if file_storage else 'unknown_file')}")
                        flash(f'An error occurred while uploading one or more media files: {secure_filename(file_storage.filename if file_storage else "unknown_file")}. Please try again.', 'danger')
                        # Decide if to proceed without the failed file or abort. For now, aborting.
                        return render_template('create_post.html', title='Create Post', form=form, group_id=group_id_param, group_name=group_name_for_template)

        for item in media_items_to_add:
            db.session.add(item)

        process_hashtags(post.body, post)
        mentioned_users_in_post = process_mentions(text_content=post.body, owner_object=post, actor_user=current_user)

        # Commit everything (Post, MediaItems, Hashtags, Mentions)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error committing post and media: {e}")
            flash('An error occurred while creating your post. Please try again.', 'danger')
            return render_template('create_post.html', title='Create Post', form=form, group_id=group_id_param, group_name=group_name_for_template)


        # Create notifications for mentions and group posts ONLY IF the post is immediately published
        if post.is_published:
            if mentioned_users_in_post:
                for tagged_user in mentioned_users_in_post:
                    if tagged_user.id != current_user.id:
                        mention_obj = Mention.query.filter_by(
                            user_id=tagged_user.id,
                            post_id=post.id,
                            actor_id=current_user.id
                        ).order_by(Mention.timestamp.desc()).first()
                        if mention_obj:
                            notification = Notification(
                                recipient_id=tagged_user.id,
                                actor_id=current_user.id,
                                type='mention',
                                related_post_id=post.id,
                                related_mention_id=mention_obj.id)
                            db.session.add(notification)
                            socketio.emit('new_notification', {
                                'type': 'mention', 'message': f"{current_user.username} mentioned you in a post.",
                                'actor_username': current_user.username, 'tagged_username': tagged_user.username,
                                'post_id': post.id, 'post_body_preview': post.body[:50] + "..." if len(post.body) > 50 else post.body,
                                'owner_username': post.author.username,
                                'url': url_for('main.profile', username=post.author.username, _external=True) + f'#post-{post.id}'
                            }, room=str(tagged_user.id))
                db.session.commit() # Commit mention notifications

            if target_group: # This implies post.group_id is set
                for membership_assoc in target_group.memberships:
                    member_user = membership_assoc.user
                    if member_user.id != current_user.id:
                        notification = Notification(
                            recipient_id=member_user.id, actor_id=current_user.id,
                            type='new_group_post', related_post_id=post.id, related_group_id=target_group.id)
                        db.session.add(notification)
                db.session.commit() # Commit group post notifications

        if post.is_published:
            flash('Your post is now live!', 'success')
        else:
            flash(f'Your post has been scheduled for {post.scheduled_for.strftime("%Y-%m-%d %H:%M") if post.scheduled_for else "a future time"}.', 'info')

        if target_group:
            return redirect(url_for('main.view_group', group_id=target_group.id))
        else:
            return redirect(url_for('main.index'))

    return render_template('create_post.html', title='Create Post', form=form, group_id=group_id_param, group_name=group_name_for_template)


@main.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.options(joinedload(Post.media_items)).get_or_404(post_id) # Eager load media_items
    if post.author != current_user:
        abort(403)

    form = PostForm(obj=post)
    form.custom_friend_list_id.choices = [(fl.id, fl.name) for fl in current_user.friend_lists.all()]
    if request.method == 'GET':
        if post.privacy_level == PRIVACY_CUSTOM_LIST and post.custom_friend_list_id:
            form.custom_friend_list_id.data = post.custom_friend_list_id

    if form.validate_on_submit():
        post.body = form.body.data # Body is the caption
        post.privacy_level = form.privacy_level.data
        if post.privacy_level == PRIVACY_CUSTOM_LIST:
            if form.custom_friend_list_id.data:
                post.custom_friend_list_id = form.custom_friend_list_id.data
            else:
                flash('Please select a friend list for "Custom List" visibility.', 'warning')
                return render_template('edit_post.html', title='Edit Post', form=form, post=post)
        else:
            post.custom_friend_list_id = None

        upload_folder = current_app.config.get('MEDIA_ITEMS_UPLOAD_FOLDER', 'static/media_items')

        # Handle deletion of existing media items
        media_ids_to_delete = request.form.getlist('delete_media_ids[]')
        if media_ids_to_delete:
            for media_id_str in media_ids_to_delete:
                try:
                    media_id_to_delete = int(media_id_str)
                    media_item_to_delete = MediaItem.query.get(media_id_to_delete)
                    if media_item_to_delete and media_item_to_delete.post_id == post.id:
                        # Delete physical file
                        try:
                            file_path = os.path.join(current_app.root_path, upload_folder, media_item_to_delete.filename)
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        except OSError as e:
                            current_app.logger.error(f"Error deleting media file {media_item_to_delete.filename}: {e}")
                            flash(f'Error deleting file {media_item_to_delete.filename}.', 'warning')
                        db.session.delete(media_item_to_delete)
                    else:
                        flash(f'Media item with ID {media_id_to_delete} not found or not associated with this post.', 'warning')
                except ValueError:
                    flash(f'Invalid media ID format: {media_id_str}.', 'warning')


        # Handle newly uploaded files
        if form.media_files.data:
            for file_storage in form.media_files.data:
                if file_storage and file_storage.filename:
                    try:
                        filename, media_type = save_media_file(file_storage, upload_folder)
                        media_item = MediaItem(
                            post_id=post.id,
                            filename=filename,
                            media_type=media_type,
                            alt_text=None # Placeholder for individual alt text
                        )
                        db.session.add(media_item)
                    except Exception as e:
                        current_app.logger.error(f"Media file upload error during edit: {e} for file {secure_filename(file_storage.filename)}")
                        flash(f'An error occurred while uploading new media file: {secure_filename(file_storage.filename)}. Please try again.', 'danger')
                        # Potentially return early or collect errors
                        return render_template('edit_post.html', title='Edit Post', form=form, post=post)

        process_hashtags(post.body, post)
        Mention.query.filter_by(post_id=post.id).delete() # Clear old mentions
        mentioned_users_in_edited_post = process_mentions(text_content=post.body, owner_object=post, actor_user=current_user)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error committing edited post: {e}")
            flash('An error occurred while updating your post. Please try again.', 'danger')
            return render_template('edit_post.html', title='Edit Post', form=form, post=post)

        # Create notifications for mentions (post-commit)
        if mentioned_users_in_edited_post:
            for tagged_user in mentioned_users_in_edited_post:
                if tagged_user.id != current_user.id:
                    mention_obj = Mention.query.filter_by(
                        user_id=tagged_user.id, post_id=post.id, actor_id=current_user.id
                    ).order_by(Mention.timestamp.desc()).first()
                    if mention_obj:
                        existing_notification = Notification.query.filter_by(
                            recipient_id=tagged_user.id, actor_id=current_user.id,
                            type='mention', related_mention_id=mention_obj.id
                        ).first()
                        if not existing_notification:
                            notification = Notification(
                                recipient_id=tagged_user.id, actor_id=current_user.id, type='mention',
                                related_post_id=post.id, related_mention_id=mention_obj.id)
                            db.session.add(notification)
                            socketio.emit('new_notification', {
                                'type': 'mention', 'message': f"{current_user.username} mentioned you in an updated post.",
                                'actor_username': current_user.username, 'tagged_username': tagged_user.username,
                                'post_id': post.id, 'post_body_preview': post.body[:50] + "..." if len(post.body) > 50 else post.body,
                                'owner_username': post.author.username,
                                'url': url_for('main.profile', username=post.author.username, _external=True) + f'#post-{post.id}'
                            }, room=str(tagged_user.id))
            db.session.commit()

        flash('Your post has been updated!', 'success')
        # Assuming view_post_page exists or redirect to profile.
        return redirect(url_for('main.profile', username=current_user.username, _anchor=f'post-{post.id}'))


    return render_template('edit_post.html', title='Edit Post', form=form, post=post) # Pass post to access post.media_items in template


@main.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.options(joinedload(Post.media_items)).get_or_404(post_id) # Eager load media_items
    if post.author != current_user:
        abort(403)

    upload_folder = current_app.config.get('MEDIA_ITEMS_UPLOAD_FOLDER', 'static/media_items')

    # Delete associated media files first
    for item in post.media_items:
        try:
            file_path = os.path.join(current_app.root_path, upload_folder, item.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError as e: # Catch file system errors
            current_app.logger.error(f"Error deleting media file {item.filename} for post {post.id}: {e}")
            # Flash a warning but proceed with deleting the database record
            flash(f'Warning: Could not delete file {item.filename}. Please contact support if this persists.', 'warning')

    # The Post.media_items relationship has cascade='all, delete-orphan',
    # so MediaItem DB records will be deleted when the post is deleted.
    db.session.delete(post)
    db.session.commit()
    flash('Your post and all its media have been deleted!', 'success')
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

# Removed old /like and /unlike routes as Like model is deprecated
# New /react route handles likes and other reactions.

@main.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    form = CommentForm() # This form will be submitted from the template where the post is displayed
    if form.validate_on_submit(): # Check if the submitted form (from the template) is valid
        comment = Comment(body=form.body.data, author=current_user, commented_post=post)
        db.session.add(comment)

        # Process mentions before committing the comment
        # The actual notification creation will be handled in a subsequent step/subtask
        mentioned_users_in_comment = process_mentions(text_content=comment.body, owner_object=comment, actor_user=current_user)

        db.session.commit()

        # Create notifications for mentions in the comment
        if mentioned_users_in_comment:
            for tagged_user in mentioned_users_in_comment:
                if tagged_user.id != current_user.id: # Avoid self-notification
                    mention_obj = Mention.query.filter_by(
                        user_id=tagged_user.id,
                        comment_id=comment.id, # Key difference: filter by comment_id
                        actor_id=current_user.id
                    ).order_by(Mention.timestamp.desc()).first()

                    if mention_obj:
                        notification = Notification(
                            recipient_id=tagged_user.id,
                            actor_id=current_user.id,
                            type='mention',
                            related_post_id=comment.post_id, # Link to the parent post
                            related_mention_id=mention_obj.id
                        )
                        db.session.add(notification)

                        socketio.emit('new_notification', {
                            'type': 'mention',
                            'message': f"{current_user.username} mentioned you in a comment.",
                            'actor_username': current_user.username,
                            'tagged_username': tagged_user.username,
                            'post_id': comment.post_id,
                            'comment_id': comment.id,
                            'comment_body_preview': comment.body[:50] + "..." if len(comment.body) > 50 else comment.body,
                            'owner_username': comment.author.username, # Username of the comment author (could be current_user)
                            'post_author_username': post.author.username, # Username of the parent post's author
                               'url': url_for('main.profile', username=post.author.username, _external=True) + f'#comment-{comment.id}' # Basic URL
                        }, room=str(tagged_user.id))
            db.session.commit() # Commit mention notifications for comment

        flash('Your comment has been added!', 'success')

        # Notification and event for comment (original comment notification to post author)
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

# Define allowed reaction types
ALLOWED_REACTIONS = {'like', 'love', 'haha', 'wow', 'sad', 'angry'}

@main.route('/react/<int:post_id>/<string:reaction_type>', methods=['POST'])
@login_required
def react_to_post(post_id, reaction_type):
    post = Post.query.get_or_404(post_id)

    if reaction_type not in ALLOWED_REACTIONS:
        flash('Invalid reaction type.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    existing_reaction = Reaction.query.filter_by(user_id=current_user.id, post_id=post.id).first()

    if existing_reaction:
        if existing_reaction.reaction_type == reaction_type:
            # User clicked the same reaction again, so remove it (toggle off)
            db.session.delete(existing_reaction)
            db.session.commit()
            flash(f'Your reaction "{reaction_type}" has been removed.', 'success')
        else:
            # User changed their reaction
            existing_reaction.reaction_type = reaction_type
            existing_reaction.timestamp = datetime.now(timezone.utc) if hasattr(timezone, 'utc') else datetime.utcnow()
            db.session.commit()
            flash(f'Your reaction has been updated to "{reaction_type}".', 'success')
            # Notification logic for changed reaction can be added here if needed
    else:
        # New reaction
        new_reaction = Reaction(user_id=current_user.id, post_id=post.id, reaction_type=reaction_type)
        db.session.add(new_reaction)
        db.session.commit()
        flash(f'You reacted with "{reaction_type}" to the post!', 'success')

        # Notification for the post author (if not reacting to own post)
        if post.author.id != current_user.id:
            notification = Notification(
                recipient_id=post.author.id,
                actor_id=current_user.id,
                type=f'reaction_{reaction_type}', # More specific notification type
                related_post_id=post.id
            )
            db.session.add(notification)
            db.session.commit()
            socketio.emit('new_notification', {
                'message': f'{current_user.username} reacted with "{reaction_type}" to your post.',
                'type': f'reaction_{reaction_type}',
                'reaction_type': reaction_type,
                'actor_username': current_user.username,
                'post_id': post.id,
                'post_author_username': post.author.username
            }, room=str(post.author.id))

            # Milestone notifications specifically for 'like' reactions
            if reaction_type == 'like':
                current_like_count = post.reaction_count('like') # Use new method
                for milestone_val in LIKE_MILESTONES:
                    if current_like_count == milestone_val:
                        # Check if a milestone notification of this type already exists for this post for this author
                        # To prevent duplicate notifications if something causes a recount or re-trigger
                        existing_milestone_notif = Notification.query.filter_by(
                            recipient_id=post.author.id, # Should be post.author.id
                            related_post_id=post.id,
                            type=f'like_milestone_{milestone_val}'
                        ).first()
                        if not existing_milestone_notif:
                            milestone_notif = Notification(
                                recipient_id=post.author.id,
                                actor_id=current_user.id, # The user whose 'like' caused the milestone
                                type=f'like_milestone_{milestone_val}',
                                related_post_id=post.id
                            )
                            db.session.add(milestone_notif)
                            db.session.commit() # Commit milestone notification
                            socketio.emit('new_notification', {
                                'message': f"Your post '{post.body[:30]}{'...' if len(post.body) > 30 else ''}' reached {milestone_val} likes!",
                                'type': f'like_milestone_{milestone_val}',
                                'actor_username': current_user.username, # Or system/generic for milestones
                                'post_id': post.id,
                                'post_author_username': post.author.username,
                                'milestone_count': milestone_val
                            }, room=str(post.author.id))


    return redirect(request.referrer or url_for('main.index'))


@main.route('/bookmark/<int:post_id>', methods=['POST'])
@login_required
def bookmark_post(post_id):
    post = Post.query.get_or_404(post_id)
    existing_bookmark = Bookmark.query.filter_by(user_id=current_user.id, post_id=post.id).first()

    if existing_bookmark:
        db.session.delete(existing_bookmark)
        flash('Post unbookmarked.', 'success')
    else:
        new_bookmark = Bookmark(user_id=current_user.id, post_id=post.id)
        db.session.add(new_bookmark)
        flash('Post bookmarked.', 'success')

    db.session.commit()
    return redirect(request.referrer or url_for('main.index'))


@main.route('/bookmarks')
@login_required
def list_bookmarks():
    # Fetch Post objects bookmarked by the current_user, ordered by Bookmark.timestamp desc
    bookmarked_posts_query = Post.query.join(Bookmark, Post.id == Bookmark.post_id)\
        .filter(Bookmark.user_id == current_user.id)\
        .order_by(Bookmark.timestamp.desc())

    bookmarked_posts = bookmarked_posts_query.all()

    comment_form = CommentForm()  # For the _post.html partial
    return render_template('bookmarks.html', title=_l('My Bookmarks'), posts=bookmarked_posts, comment_form=comment_form)


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

    messages_query = conversation.messages.order_by(ChatMessage.timestamp.asc()).all() # Ensure order

    # Get read statuses for the current user for messages in this conversation
    message_ids_in_conversation = [msg.id for msg in messages_query]

    current_user_read_statuses = {}
    if message_ids_in_conversation: # Only query if there are messages
        statuses = MessageReadStatus.query.filter(
            MessageReadStatus.user_id == current_user.id,
            MessageReadStatus.message_id.in_(message_ids_in_conversation)
        ).all()
        current_user_read_statuses = {status.message_id: status.read_at for status in statuses}

    # Augment messages with read status for the current user and the general read_at
    augmented_messages = []
    for msg in messages_query:
        augmented_messages.append({
            'id': msg.id,
            'sender_id': msg.sender_id,
            'sender_username': msg.sender.username, # Assuming sender relationship is loaded or accessible
            'body': msg.body,
            'timestamp': msg.timestamp,
            'read_at': msg.read_at, # This is the general read_at (first read by anyone/recipient in 1-1)
            'is_read_by_current_user': msg.id in current_user_read_statuses,
            'read_at_by_current_user': current_user_read_statuses.get(msg.id) # Specific time current user read it
        })

    other_participants = [p for p in conversation.participants if p.id != current_user.id]

    return render_template('chat/view_conversation.html',
                           title=f'Chat with {", ".join(p.username for p in other_participants) if other_participants else "Saved Messages"}',
                           conversation=conversation,
                           messages=augmented_messages, # Pass augmented messages
                           other_participants=other_participants,
                           current_user_id=current_user.id) # Pass current_user_id for template logic

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
@cache.cached(timeout=3600, make_cache_key=make_user_specific_cache_key) # Cache for 1 hour
def analytics():
    selected_period = request.args.get('period', '7days')
    if selected_period not in ['7days', '30days', '90days', 'all']:
        selected_period = '7days' # Default to 7days if invalid period is provided

    # Fetch data using utility functions
    historical_engagement_data = get_historical_engagement(current_user.id, selected_period)
    top_hashtags_data = get_top_performing_hashtags(current_user.id, limit=5)
    top_groups_data = get_top_performing_groups(current_user.id, limit=5)

    # Prepare data for historical engagement chart (Chart.js)
    timestamps = [record.timestamp.strftime('%Y-%m-%d') for record in historical_engagement_data]
    likes_over_time = [record.likes_received for record in historical_engagement_data]
    comments_over_time = [record.comments_received for record in historical_engagement_data]
    followers_over_time = [record.followers_count for record in historical_engagement_data]

    historical_chart_labels_json = json.dumps(timestamps)
    historical_likes_json = json.dumps(likes_over_time)
    historical_comments_json = json.dumps(comments_over_time)
    historical_followers_json = json.dumps(followers_over_time)

    # Existing analytics data (summary stats)
    user_analytics_summary = UserAnalytics.query.filter_by(user_id=current_user.id).first()

    # Follower/Following counts (can also come from HistoricalAnalytics if desired for the latest day)
    # For consistency, let's use the direct counts for current snapshot
    follower_count = current_user.followers.count()
    following_count = current_user.followed.count()
    total_posts_count = current_user.posts.count() # More direct way to get total posts

    # Top posts logic (can remain as is or be enhanced)
    user_posts = current_user.posts.all() # Get all posts for sorting if needed by existing logic
    # Updated to use reaction_count('like') for sorting by engagement
    sorted_posts = sorted(user_posts, key=lambda p: p.reaction_count(reaction_type='like') + p.comments.count(), reverse=True)
    top_5_posts_list = sorted_posts[:5]

    top_posts_chart_data_json = []
    if top_5_posts_list:
        top_posts_chart_data_json = json.dumps([
            {'label': f"Post ID {post.id}: {post.body[:20]}..." if len(post.body) > 20 else f"Post ID {post.id}: {post.body}",
             'likes': post.reaction_count(reaction_type='like'), # Use reaction_count for 'like'
             'comments': post.comments.count()} # Assuming post.comments.count() is correct
            for post in top_5_posts_list
        ])


    return render_template('analytics.html', title='User Analytics',
                           user=current_user,
                           # Summary Stats (from UserAnalytics or direct counts)
                           total_posts=total_posts_count,
                           total_likes_received=user_analytics_summary.total_likes_received if user_analytics_summary else 0,
                           total_comments_received=user_analytics_summary.total_comments_received if user_analytics_summary else 0,
                           current_follower_count=follower_count, # Renamed to avoid clash if followers_over_time is also used directly
                           current_following_count=following_count,
                           user_analytics_summary=user_analytics_summary, # Pass the whole object for flexibility

                           # Historical Engagement Data for Charts
                           historical_engagement_raw_data=historical_engagement_data, # Pass raw for table display if needed
                           historical_chart_labels_json=historical_chart_labels_json,
                           historical_likes_json=historical_likes_json,
                           historical_comments_json=historical_comments_json,
                           historical_followers_json=historical_followers_json,

                           # Top Performing Content
                           top_hashtags_data=top_hashtags_data,
                           top_groups_data=top_groups_data,
                           top_posts_list=top_5_posts_list, # Renamed for clarity
                           top_posts_chart_data_json=top_posts_chart_data_json, # Renamed for clarity

                           # Control
                           selected_period=selected_period)


@main.route('/analytics/export', methods=['GET'])
@login_required
def analytics_export():
    period_for_export = request.args.get('period', 'all') # Default to 'all' for export
    if period_for_export not in ['7days', '30days', '90days', 'all']:
        period_for_export = 'all'

    # 1. Fetch Summary Statistics
    user_analytics_summary = UserAnalytics.query.filter_by(user_id=current_user.id).first()
    total_posts_count = Post.query.filter_by(user_id=current_user.id).count()
    current_follower_count = current_user.followers.count()
    current_following_count = current_user.followed.count()

    summary_data = [
        ("Total Posts", total_posts_count),
        ("Total Likes Received", user_analytics_summary.total_likes_received if user_analytics_summary else 0),
        ("Total Comments Received", user_analytics_summary.total_comments_received if user_analytics_summary else 0),
        ("Current Followers", current_follower_count),
        ("Current Following", current_following_count)
    ]

    # 2. Fetch Historical Engagement Data
    historical_engagement_data = get_historical_engagement(current_user.id, period=period_for_export)

    # 3. Fetch Top Performing Hashtags
    top_hashtags_data = get_top_performing_hashtags(current_user.id, limit=10)

    # 4. Fetch Top Performing Groups
    top_groups_data = get_top_performing_groups(current_user.id, limit=10)

    # Generate CSV
    si = io.StringIO()
    cw = csv.writer(si)

    # Section 1: Summary Statistics
    cw.writerow(["Summary Statistics"])
    cw.writerow(["Metric", "Value"])
    for row in summary_data:
        cw.writerow(row)
    cw.writerow([]) # Empty row for spacing

    # Section 2: Historical Engagement
    cw.writerow(["Historical Engagement Data"])
    cw.writerow(["Date", "Likes Received", "Comments Received", "Followers Count"])
    for record in historical_engagement_data:
        cw.writerow([
            record.timestamp.strftime('%Y-%m-%d'),
            record.likes_received,
            record.comments_received,
            record.followers_count
        ])
    cw.writerow([]) # Empty row

    # Section 3: Top Performing Hashtags
    cw.writerow(["Top Performing Hashtags"])
    cw.writerow(["Hashtag", "Total Engagement", "Likes", "Comments"])
    for hashtag in top_hashtags_data:
        cw.writerow([
            hashtag['tag_text'],
            hashtag['engagement'],
            hashtag['likes'],
            hashtag['comments']
        ])
    cw.writerow([]) # Empty row

    # Section 4: Top Performing Groups
    cw.writerow(["Top Performing Groups"])
    cw.writerow(["Group Name", "Total Engagement", "Likes", "Comments"])
    for group in top_groups_data:
        cw.writerow([
            group['group_name'],
            group['engagement'],
            group['likes'],
            group['comments']
        ])

    # Create response
    output = make_response(si.getvalue())
    filename = f"analytics_export_{current_user.username}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.csv"
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv"
    return output


@main.route('/update_analytics', methods=['POST'])
@login_required
def update_analytics_route():
    # This is a simplified manual trigger. In a real app, this would be a scheduled task.
    # And likely restricted to admins or system processes.

    users = User.query.all()
    for user in users:
        # Updated to count 'like' reactions for total_likes_received
        total_likes = db.session.query(func.count(Reaction.id))\
            .join(Post, Reaction.post_id == Post.id)\
            .filter(Post.user_id == user.id, Reaction.reaction_type == 'like')\
            .scalar()
        total_comments = db.session.query(func.count(Comment.id)).join(Post).filter(Post.user_id == user.id).scalar()

        analytics_entry = UserAnalytics.query.filter_by(user_id=user.id).first()
        if not analytics_entry:
            analytics_entry = UserAnalytics(user_id=user.id)
            db.session.add(analytics_entry)

        analytics_entry.total_likes_received = total_likes
        analytics_entry.total_comments_received = total_comments
        # last_updated is handled by onupdate in the model

    db.session.commit()
    flash('User analytics have been updated.', 'success')
    return redirect(url_for('main.analytics'))


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

@main.route('/event/<int:event_id>/export_calendar')
@login_required
def export_calendar(event_id):
    event = Event.query.get_or_404(event_id)

    # Authorization check: User must be organizer or an attendee
    is_attendee = current_user in event.attendees
    if event.organizer_id != current_user.id and not is_attendee:
        flash('You are not authorized to export this event.', 'danger')
        return redirect(url_for('main.view_event', event_id=event.id)) # Or abort(403)

    ics_content = generate_ics_file(event)

    # Simple slugification for the filename
    event_name_slug = re.sub(r'[^\w]+', '_', event.name.lower())
    if not event_name_slug: # handle case where name is all special chars
        event_name_slug = "event"

    filename = f"event_{event.id}_{event_name_slug[:50]}.ics" # Truncate slug part if too long

    response = make_response(ics_content)
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.headers['Content-Type'] = 'text/calendar; charset=utf-8'

    # Update is_synced status (optional, based on previous discussion for UI feedback)
    # This assumes that exporting means it's "synced" or an attempt was made.
    # If event.is_synced is a field, uncomment and adjust:
    # if not event.is_synced:
    #     event.is_synced = True
    #     db.session.add(event)
    #     db.session.commit()

    flash('Event calendar file (.ics) downloaded. Open it with your calendar application to add this event to your schedule.', 'success')
    return response

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
@cache.cached(timeout=300, make_cache_key=make_user_specific_cache_key)
def view_group(group_id):
    group = Group.query.get_or_404(group_id)

    feed_items = []

    # 1. Query for direct posts to the group - only published ones
    direct_posts = Post.query.filter_by(group_id=group_id, is_published=True).order_by(Post.timestamp.desc()).all()
    for post in direct_posts:
        feed_items.append({
            'type': 'post',
            'item': post,
            'timestamp': post.timestamp,
            'sharer': None
        })

    # 2. Query for shared posts to the group
    shared_posts_query = Share.query.filter_by(group_id=group_id)\
        .options(
            joinedload(Share.original_post).joinedload(Post.author),
            joinedload(Share.user)
        )\
        .order_by(Share.timestamp.desc())\
        .all()

    for share_item in shared_posts_query:
        # Only include if the original post is published
        if share_item.original_post and share_item.original_post.is_published:
            feed_items.append({
                'type': 'share',
                'item': share_item.original_post,
                'timestamp': share_item.timestamp,
                'sharer': share_item.user
            })

    # 3. Sort the unified list by timestamp (descending)
    feed_items.sort(key=lambda x: x['timestamp'], reverse=True)

    is_member = False
    is_admin = False
    if current_user.is_authenticated:
        membership = GroupMembership.query.filter_by(user_id=current_user.id, group_id=group.id).first()
        if membership:
            is_member = True
            if membership.role == 'admin':
                is_admin = True

    comment_form = CommentForm() # Added for posts within group view
    return render_template('group.html', title=group.name, group=group, feed_items=feed_items, is_member=is_member, is_admin=is_admin, comment_form=comment_form)

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

    stories_query = Story.query.filter(Story.expires_at > now)

    if current_user.is_authenticated:
        followed_user_ids = [user.id for user in current_user.followed]

        # Base filter for active stories (published and not expired, or own scheduled)
        active_filter = or_(
            and_(Story.is_published == True, Story.expires_at > now), # Published and not expired
            and_(Story.user_id == current_user.id, Story.is_published == False) # Own scheduled (expires_at is None or will be set on publish)
        )
        stories_query = stories_query.filter(active_filter)

        # Privacy filters on top of the active_filter
        privacy_filter = or_(
            Story.user_id == current_user.id, # Own stories (already covered by active_filter for scheduled, this ensures published are also included)
            and_( # Stories from followed users (must be published and not expired)
                Story.user_id.in_(followed_user_ids),
                Story.is_published == True, # Redundant if active_filter is perfect, but good for clarity
                or_(
                    Story.privacy_level == PRIVACY_PUBLIC,
                    Story.privacy_level == PRIVACY_FOLLOWERS
                )
            ),
            and_( # Stories from ANY user shared with a custom list current_user is on (must be published and not expired)
                Story.privacy_level == PRIVACY_CUSTOM_LIST,
                Story.custom_friend_list_id.isnot(None),
                Story.is_published == True, # Redundant if active_filter is perfect
                Story.custom_friend_list.has(
                    FriendList.members.any(User.id == current_user.id)
                )
            ),
            and_( # Public stories from anyone (must be published and not expired)
                 Story.privacy_level == PRIVACY_PUBLIC,
                 Story.is_published == True
            )
        )
        stories_query = stories_query.filter(privacy_filter).distinct()

    else: # Unauthenticated users
        stories_query = stories_query.filter(Story.privacy_level == PRIVACY_PUBLIC, Story.is_published == True, Story.expires_at > now)

    active_stories = stories_query.order_by(Story.timestamp.desc()).all()

    return render_template('stories.html', title='Stories', stories=active_stories)

@main.route('/story/create', methods=['GET', 'POST'])
@login_required
def create_story():
    form = StoryForm()

    # Populate choices for custom_friend_list_id
    form.custom_friend_list_id.choices = [(fl.id, fl.name) for fl in current_user.friend_lists.all()]

    if form.validate_on_submit():
        if form.media_file.data:
            try:
                filename, media_type = save_story_media(form.media_file.data) # Assuming save_story_media exists

                story_privacy_level = form.privacy_level.data
                story_custom_list_id = None

                if story_privacy_level == PRIVACY_CUSTOM_LIST:
                    if form.custom_friend_list_id.data:
                        story_custom_list_id = form.custom_friend_list_id.data
                    else:
                        flash('Please select a friend list if you choose "Custom List" visibility, or change visibility.', 'warning')
                        # Need to re-populate choices for rendering again
                        return render_template('create_story.html', title='Create Story', form=form)

                story_data = {
                    'user_id': current_user.id,
                    'caption': form.caption.data,
                    'privacy_level': story_privacy_level,
                    'custom_friend_list_id': story_custom_list_id
                    # scheduled_for and is_published will be added next
                }

                scheduled_for_value = None
                is_published_value = True # Default to immediate publish

                if form.schedule_time.data:
                    if form.schedule_time.data > datetime.now(): # Naive comparison
                        # TODO: Convert form.schedule_time.data (user's local time) to UTC before storing
                        scheduled_for_value = form.schedule_time.data
                        is_published_value = False
                        # Flash message handled below
                    else:
                        flash('Scheduled time is in the past. Publishing story now.', 'warning')

                story_data['scheduled_for'] = scheduled_for_value
                story_data['is_published'] = is_published_value

                if media_type == 'image':
                    story_data['image_filename'] = filename
                elif media_type == 'video':
                    story_data['video_filename'] = filename
                else:
                    flash('Unsupported media type after saving.', 'danger')
                    return render_template('create_story.html', title='Create Story', form=form)

                story = Story(**story_data) # is_published is passed here, Story.__init__ handles expires_at
                db.session.add(story)
                db.session.commit()

                if is_published_value:
                    flash('Your story has been posted!', 'success')
                else:
                    flash(f'Your story has been scheduled for {story.scheduled_for.strftime("%Y-%m-%d %H:%M") if story.scheduled_for else "a future time"}.', 'info')
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

            # Calculate updated vote counts and emit SocketIO event
            vote_counts = {option.id: option.vote_count() for option in poll.options}
            total_votes = poll.total_votes()
            socketio.emit('poll_update', {
                'poll_id': poll.id,
                'vote_counts': vote_counts,
                'total_votes': total_votes
            }, room=f'poll_{poll.id}')
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

        # Calculate updated vote counts and emit SocketIO event
        vote_counts = {option.id: option.vote_count() for option in poll.options}
        total_votes = poll.total_votes()
        socketio.emit('poll_update', {
            'poll_id': poll.id,
            'vote_counts': vote_counts,
            'total_votes': total_votes
        }, room=f'poll_{poll.id}')

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


@main.route('/post/<int:post_id>/share', methods=['POST'])
@login_required
def share_post(post_id):
    post_to_share = Post.query.get_or_404(post_id)
    group_id = request.form.get('group_id', type=int) # Optional group_id from form

    # Prevent sharing own post to own feed (though sharing to a group is fine)
    if post_to_share.author == current_user and group_id is None:
        flash("You cannot share your own post to your main feed.", "info")
        return redirect(request.referrer or url_for('main.index'))

    # Check if already shared to the same destination (user's feed or specific group)
    existing_share_query = Share.query.filter_by(
        user_id=current_user.id,
        post_id=post_to_share.id
    )
    if group_id:
        existing_share_query = existing_share_query.filter_by(group_id=group_id)
    else:
        existing_share_query = existing_share_query.filter(Share.group_id.is_(None))

    existing_share = existing_share_query.first()

    if existing_share:
        flash('You have already shared this post to this destination.', 'info')
        return redirect(request.referrer or url_for('main.index'))

    share = Share(user_id=current_user.id, post_id=post_to_share.id, group_id=group_id)
    db.session.add(share)
    db.session.commit()

    # Notification for the original poster (if not sharing own post to own feed implicitly)
    if post_to_share.author != current_user: # This condition implicitly handles not notifying self for a general share
        original_poster_notification = Notification(
            recipient_id=post_to_share.author.id,
            actor_id=current_user.id,
            type='share', # This is a general share to user's feed or a group
            related_post_id=share.post_id
            # related_share_id=share.id # If you add this to Notification model
        )
        db.session.add(original_poster_notification)
        # Commit this separately or together with group share notifications later
        # For now, let's commit it here to keep its logic contained.
        db.session.commit()
        socketio.emit('new_notification', {
            'message': f'{current_user.username} shared your post.',
            'type': 'share',
            'actor_username': current_user.username,
            'post_id': share.post_id,
            'post_author_username': post_to_share.author.username
        }, room=str(post_to_share.author.id))

    # Notifications for group members if it's a group share
    if share.group_id:
        group = Group.query.get(share.group_id)
        if group:
            notifications_for_socketio = [] # Store details for emitting socket events
            for membership_assoc in group.memberships:
                member_user = membership_assoc.user
                if member_user.id != current_user.id: # Don't notify the sharer
                    group_share_notification = Notification(
                        recipient_id=member_user.id,
                        actor_id=current_user.id,
                        type='group_share', # Distinct type for group shares
                        related_post_id=share.post_id,
                        related_group_id=share.group_id
                        # related_share_id=share.id # If you add this to Notification model
                    )
                    db.session.add(group_share_notification)
                    notifications_for_socketio.append({
                        'recipient_id': member_user.id,
                        'group_name': group.name
                    })
            db.session.commit() # Commit all group share notifications

            for notif_detail in notifications_for_socketio:
                socketio.emit('new_notification', {
                    'message': f"{current_user.username} shared a post to the group {notif_detail['group_name']}.",
                    'type': 'group_share',
                    'actor_username': current_user.username,
                    'post_id': share.post_id,
                    'group_id': share.group_id,
                    'group_name': notif_detail['group_name']
                }, room=str(notif_detail['recipient_id']))

    flash('Post shared successfully!', 'success')
    if group_id:
        return redirect(url_for('main.view_group', group_id=group_id))
    return redirect(url_for('main.index')) # Or redirect to current_user's profile/feed


# -------------------- OAuth and External Sharing Routes --------------------

@main.route('/authorize/twitter')
@login_required
def twitter_authorize():
    # Placeholder for actual OAuth flow
    flash("Imagine being redirected to Twitter for authorization...", "info")
    # In a real app, this would involve redirecting to Twitter's auth URL
    # and handling the OAuth dance with a library like Flask-Dance or requests-oauthlib
    return redirect(url_for('main.edit_profile'))

@main.route('/callback/twitter')
@login_required
def twitter_callback():
    # Placeholder for handling callback from Twitter
    # In a real app, you'd verify the response and get the access token
    current_user.twitter_access_token = "fake_twitter_token_for_user_" + str(current_user.id)
    db.session.commit()
    flash("Successfully connected your Twitter account (simulated).", "success")
    return redirect(url_for('main.edit_profile'))

@main.route('/authorize/facebook')
@login_required
def facebook_authorize():
    # Placeholder for actual OAuth flow
    flash("Imagine being redirected to Facebook for authorization...", "info")
    return redirect(url_for('main.edit_profile'))

@main.route('/callback/facebook')
@login_required
def facebook_callback():
    # Placeholder for handling callback from Facebook
    current_user.facebook_access_token = "fake_facebook_token_for_user_" + str(current_user.id)
    db.session.commit()
    flash("Successfully connected your Facebook account (simulated).", "success")
    return redirect(url_for('main.edit_profile'))

@main.route('/share/twitter/<int:post_id>', methods=['POST']) # Should be POST
@login_required
def share_to_twitter(post_id):
    post = Post.query.get_or_404(post_id)
    if not current_user.twitter_access_token:
        flash("Please connect your Twitter account first via your Edit Profile page.", "warning")
        return redirect(request.referrer or url_for('main.index'))

    # Placeholder for actual sharing logic using the token
    flash(f"Simulated sharing post '{post.body[:30]}...' to Twitter!", "success")
    # Example: client.create_tweet(text=post.body, user_auth=True) with tweepy
    return redirect(request.referrer or url_for('main.index'))

@main.route('/share/facebook/<int:post_id>', methods=['POST']) # Should be POST
@login_required
def share_to_facebook(post_id):
    post = Post.query.get_or_404(post_id)
    if not current_user.facebook_access_token:
        flash("Please connect your Facebook account first via your Edit Profile page.", "warning")
        return redirect(request.referrer or url_for('main.index'))

    # Placeholder for actual sharing logic
    flash(f"Simulated sharing post '{post.body[:30]}...' to Facebook!", "success")
    # Example: graph.put_object("me", "feed", message=post.body) with facebook-sdk
    return redirect(request.referrer or url_for('main.index'))


# -------------------- Live Stream Routes --------------------
import secrets
from app.core.models import LiveStream # Already have User, Post
from app.core.forms import StreamSetupForm # Already have other forms

@main.route('/stream/manage', methods=['GET', 'POST'])
@login_required
def manage_stream():
    stream = LiveStream.query.filter_by(user_id=current_user.id).first()
    if not stream:
        # Initialize a new stream object if one doesn't exist, but don't save yet
        stream = LiveStream(user_id=current_user.id)

    form = StreamSetupForm(obj=stream) # Populate form with stream data if it exists

    if form.validate_on_submit():
        previous_is_live = stream.is_live # Store previous state if stream object already existed
        if not stream.id: # If it's a new stream object
            db.session.add(stream)
            previous_is_live = False # For a new stream, previous state is effectively not live

        stream.title = form.title.data
        stream.description = form.description.data
        stream.is_live = form.go_live.data
        stream.enable_recording = form.enable_recording.data # Save enable_recording status

        if not stream.stream_key:
            stream.stream_key = secrets.token_hex(16)
            # flash("Your unique stream key has been generated. Keep it secret!", "info") # Flash moved below

        if stream.is_live and not stream.stream_conversation_id:
            # Create a new conversation for the stream chat
            new_conversation = Conversation()
            db.session.add(new_conversation)
            db.session.flush() # To get the new_conversation.id

            # Add the broadcaster as a participant
            new_conversation.participants.append(current_user)

            stream.stream_conversation_id = new_conversation.id
            # db.session.add(stream) # stream is already in session and will be committed
            flash(f'Chat room created for your stream.', 'info')

        try:
            db.session.commit() # Commit first to save stream details
            flash("Stream settings updated.", "success")

            # Emit global SocketIO events if is_live status changed
            if stream.is_live and not previous_is_live:
                # Stream just went live
                socketio.emit('global_stream_started', {
                    'username': current_user.username,
                    'title': stream.title,
                    'stream_page_url': url_for('main.view_stream', username=current_user.username, _external=True)
                }, namespace='/') # Emit to global namespace
                print(f"User {current_user.username} started a live stream: {stream.title}")
            elif not stream.is_live and previous_is_live:
                # Stream just ended
                socketio.emit('global_stream_ended', {
                    'username': current_user.username
                }, namespace='/')
                print(f"User {current_user.username} ended their live stream.")

            if not stream.stream_key and stream.is_live: # If stream key was just generated and went live
                 flash("Your unique stream key has been generated. Keep it secret!", "info")


        except Exception as e:
            db.session.rollback()
            flash(f"Error updating stream settings: {e}", "danger")
            current_app.logger.error(f"Error in manage_stream POST: {e}")

        return redirect(url_for('main.manage_stream'))

    # For GET request, or if form validation fails
    return render_template('manage_stream.html', title='Manage Your Live Stream', form=form, stream=stream)

@main.route('/stream/<username>')
def view_stream(username):
    user = User.query.filter_by(username=username).first_or_404()
    active_stream = LiveStream.query.filter_by(user_id=user.id, is_live=True).first()

    if not active_stream:
        flash(f"{username} is not currently live.", "info")
        return redirect(url_for('main.profile', username=username))

    stream_conversation = None
    chat_messages = []
    augmented_chat_messages = [] # For consistency with existing chat display

    if active_stream.stream_conversation_id:
        stream_conversation = Conversation.query.get(active_stream.stream_conversation_id)
        if stream_conversation:
            # Fetch messages, similar to view_conversation route
            raw_chat_messages = stream_conversation.messages.order_by(ChatMessage.timestamp.asc()).all()

            # Let's include basic augmentation for sender username
            for msg in raw_chat_messages:
                augmented_chat_messages.append({
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'sender_username': msg.sender.username, # Assumes sender relationship loads User
                    'body': msg.body,
                    'timestamp': msg.timestamp,
                    # Add other fields like read_at if your stream chat will show detailed read receipts
                })
            chat_messages = augmented_chat_messages # Use the augmented list

    return render_template('view_stream.html',
                           title=f"Live Stream by {user.username} - {active_stream.title}", # Updated title
                           stream=active_stream,
                           user=user,
                           stream_chat_conversation=stream_conversation, # Pass the conversation object
                           stream_chat_messages=chat_messages) # Pass the messages

# Placeholder for a potential view_post_page route if it's different from index or profile views
# This is just for the URL generation in recommendations, actual route can be defined elsewhere or may already exist
# @main.route('/post_page/<int:post_id>')
# def view_post_page(post_id):
#     post = Post.query.get_or_404(post_id)
#     return render_template('view_post_standalone.html', post=post) # Assuming a template for single post view
# If no dedicated page, links can point to where posts are usually viewed (e.g., profile or index with anchor)


# -------------------- Friend List Management Routes --------------------

@main.route('/friend_lists')
@login_required
def list_friend_lists():
    lists = current_user.friend_lists.order_by(FriendList.name).all()
    return render_template('friend_lists.html', title='Your Friend Lists', lists=lists)

@main.route('/friend_lists/create', methods=['GET', 'POST'])
@login_required
def create_friend_list():
    form = FriendListForm()
    if form.validate_on_submit():
        new_list = FriendList(name=form.name.data, owner=current_user)
        db.session.add(new_list)
        db.session.commit()
        flash(f'Friend list "{new_list.name}" created successfully!', 'success')
        return redirect(url_for('main.list_friend_lists'))
    return render_template('create_edit_friend_list.html', title='Create Friend List', form=form)

@main.route('/friend_lists/edit/<int:list_id>', methods=['GET', 'POST'])
@login_required
def edit_friend_list(list_id):
    friend_list = FriendList.query.get_or_404(list_id)
    if friend_list.user_id != current_user.id:
        abort(403)  # Forbidden

    form = FriendListForm(obj=friend_list) # Pre-populate with current name
    if form.validate_on_submit():
        friend_list.name = form.name.data
        db.session.commit()
        flash(f'Friend list "{friend_list.name}" updated!', 'success')
        return redirect(url_for('main.list_friend_lists'))
    return render_template('create_edit_friend_list.html', title='Edit Friend List', form=form, list_id=list_id)

@main.route('/friend_lists/delete/<int:list_id>', methods=['POST'])
@login_required
def delete_friend_list(list_id):
    friend_list = FriendList.query.get_or_404(list_id)
    if friend_list.user_id != current_user.id:
        abort(403)

    # Before deleting, consider posts/stories linked to this list.
    # The current Post/Story model has custom_friend_list_id which is nullable.
    # We might want to nullify these relationships or prevent deletion if in use.
    # For now, just deleting the list. Cascades on members are handled by DB relationships.
    # If Post/Story.custom_friend_list_id has a FK constraint, it might need ondelete='SET NULL' or similar.
    # Or, manually update linked posts/stories:
    Post.query.filter_by(custom_friend_list_id=list_id, user_id=current_user.id).update({'custom_friend_list_id': None, 'privacy_level': PRIVACY_PRIVATE}) # Or user's default
    Story.query.filter_by(custom_friend_list_id=list_id, user_id=current_user.id).update({'custom_friend_list_id': None, 'privacy_level': PRIVACY_PRIVATE}) # Or user's default
    db.session.commit() # Commit changes to posts/stories first

    db.session.delete(friend_list)
    db.session.commit()
    flash(f'Friend list "{friend_list.name}" deleted.', 'success')
    return redirect(url_for('main.list_friend_lists'))

@main.route('/friend_lists/manage/<int:list_id>', methods=['GET', 'POST'])
@login_required
def manage_friend_list_members(list_id):
    friend_list = FriendList.query.get_or_404(list_id)
    if friend_list.user_id != current_user.id:
        abort(403)

    form = AddUserToFriendListForm() # For adding new members

    if form.validate_on_submit(): # This is for the 'Add User' form submission
        user_to_add = User.query.filter_by(username=form.username.data).first()
        # form.validate_username ensures user_to_add exists.
        if user_to_add == current_user:
            flash("You cannot add yourself to your own friend list.", "warning")
        elif user_to_add in friend_list.members:
            flash(f"{user_to_add.username} is already in this list.", "info")
        else:
            friend_list.members.append(user_to_add)
            db.session.commit()
            flash(f"{user_to_add.username} added to '{friend_list.name}'.", "success")
        return redirect(url_for('main.manage_friend_list_members', list_id=list_id)) # Redirect to refresh list and clear form

    members = friend_list.members.all()
    return render_template('manage_friend_list_members.html', title=f'Manage "{friend_list.name}"', friend_list=friend_list, members=members, form=form)

@main.route('/friend_lists/remove_member/<int:list_id>/<int:user_id>', methods=['POST'])
@login_required
def remove_member_from_friend_list(list_id, user_id):
    friend_list = FriendList.query.get_or_404(list_id)
    if friend_list.user_id != current_user.id:
        abort(403)

    user_to_remove = User.query.get_or_404(user_id)

    if user_to_remove not in friend_list.members:
        flash(f"{user_to_remove.username} is not in this list.", "info")
    else:
        friend_list.members.remove(user_to_remove)
        db.session.commit()
        flash(f"{user_to_remove.username} removed from '{friend_list.name}'.", "success")
    return redirect(url_for('main.manage_friend_list_members', list_id=list_id))

# -------------------- Bulk Privacy Update Route --------------------
@main.route('/bulk_update_privacy', methods=['GET', 'POST'])
@login_required
def bulk_update_privacy():
    if request.method == 'POST':
        post_ids = request.form.getlist('post_ids') # Get list of selected post IDs
        new_privacy_level = request.form.get('new_privacy_level')

        if not post_ids:
            flash('Please select at least one post to update.', 'warning')
            return redirect(url_for('main.bulk_update_privacy'))

        if not new_privacy_level or new_privacy_level not in [choice[0] for choice in PRIVACY_CHOICES]:
            flash('Invalid privacy level selected.', 'danger')
            return redirect(url_for('main.bulk_update_privacy'))

        posts_to_update = Post.query.filter(Post.id.in_(post_ids), Post.user_id == current_user.id).all()

        updated_count = 0
        for post in posts_to_update:
            post.privacy_level = new_privacy_level
            # If new_privacy_level is PRIVACY_CUSTOM_LIST, custom_friend_list_id is not set here.
            # User would need to edit individually to assign a specific list.
            if new_privacy_level != PRIVACY_CUSTOM_LIST: # Or some other logic
                post.custom_friend_list_id = None # Clear if changing away from a specific list
            db.session.add(post)
            updated_count += 1

        if updated_count > 0:
            db.session.commit()
            flash(f'{updated_count} post(s) updated to {new_privacy_level}.', 'success')
        else:
            flash('No posts were updated. They might not belong to you or were not found.', 'info')

        return redirect(url_for('main.bulk_update_privacy'))

    # GET request: Display user's posts for selection
    user_posts = current_user.posts.order_by(Post.timestamp.desc()).all()
    # Make sure PRIVACY_CHOICES is available for the template
    # It's defined in app/forms.py. We need to pass it to the template.
    privacy_options = PRIVACY_CHOICES
    return render_template('bulk_update_privacy.html', title='Bulk Update Post Privacy', posts=user_posts, privacy_options=privacy_options)


# -------------------- Article Routes --------------------

@main.route('/article/create', methods=['GET', 'POST'])
@login_required
def create_article():
    form = ArticleForm()
    if form.validate_on_submit():
        title = form.title.data
        body = form.body.data

        # Generate unique slug
        original_slug = slugify(title)
        slug_candidate = original_slug
        counter = 1
        # Loop to ensure slug uniqueness
        while Article.query.filter_by(slug=slug_candidate).first():
            slug_candidate = f"{original_slug}-{secrets.token_hex(2)}" # Append short random hex for uniqueness
            # Alternative: increment counter: slug_candidate = f"{original_slug}-{counter}"; counter += 1
        unique_slug = slug_candidate

        article = Article(title=title, body=body, author=current_user, slug=unique_slug)
        db.session.add(article)
        db.session.commit()
        flash('Article published successfully!', 'success')
        return redirect(url_for('main.view_article', slug=article.slug))
    return render_template('create_article.html', title='Create New Article', form=form)

@main.route('/article/<slug>')
@subscription_required(creator_model=Article, creator_model_param_name='slug')
def view_article(slug):
    article = Article.query.filter_by(slug=slug).first_or_404()
    return render_template('view_article.html', title=article.title, article=article)

@main.route('/article/<slug>/edit', methods=['GET', 'POST'])
@login_required
def edit_article(slug):
    article = Article.query.filter_by(slug=slug).first_or_404()
    if article.author != current_user:
        abort(403)  # Forbidden

    form = ArticleForm(obj=article) # Pre-populate form with article data on GET
    if form.validate_on_submit():
        article.title = form.title.data
        article.body = form.body.data
        # Note: Slug is generally not updated on edit to maintain URL stability.
        # If title change should reflect in slug, new unique slug generation logic would be needed.
        db.session.commit()
        flash('Article updated successfully!', 'success')
        return redirect(url_for('main.view_article', slug=article.slug))

    return render_template('edit_article.html', title=f'Edit Article: {article.title}', form=form, article=article)

@main.route('/article/<slug>/delete', methods=['POST'])
@login_required
def delete_article(slug):
    article = Article.query.filter_by(slug=slug).first_or_404()
    if article.author != current_user:
        abort(403)
    db.session.delete(article)
    db.session.commit()
    flash('Article deleted successfully!', 'success')
    return redirect(url_for('main.articles_list')) # Or user's profile or another relevant page

@main.route('/articles')
def articles_list():
    page = request.args.get('page', 1, type=int)
    # Order by timestamp descending to show newest articles first
    articles_pagination = Article.query.order_by(Article.timestamp.desc()).paginate(page=page, per_page=current_app.config.get('ARTICLES_PER_PAGE', 10), error_out=False)
    articles = articles_pagination.items
    return render_template('articles_list.html', title='All Articles', articles=articles, pagination=articles_pagination)

@main.route('/user/<username>/articles')
def user_articles(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    # Assuming user.articles is the relationship from User to Article model
    articles_pagination = user.articles.order_by(Article.timestamp.desc()).paginate(page=page, per_page=current_app.config.get('ARTICLES_PER_PAGE', 10), error_out=False)
    articles = articles_pagination.items
    return render_template('articles_list.html', title=f'Articles by {username}', articles=articles, pagination=articles_pagination, user=user)


# -------------------- Audio Post Routes --------------------

@main.route('/audio/upload', methods=['GET', 'POST'])
@login_required
def upload_audio():
    form = AudioPostForm()
    if form.validate_on_submit():
        try:
            # Assuming AUDIO_UPLOAD_FOLDER is configured in app.config
            # e.g., current_app.config.get('AUDIO_UPLOAD_FOLDER', 'static/audio_uploads')
            # save_audio_file utility will use this config.
            upload_folder_config_name = current_app.config.get('AUDIO_UPLOAD_FOLDER_NAME', 'audio_uploads') # e.g. 'audio_uploads'
            saved_filename = save_audio_file(form.audio_file.data, upload_folder_config_name)

            duration_seconds = None
            # Construct full path for duration extraction
            # Assumes save_audio_file places it under 'static/audio_uploads_configured_name'
            # And AUDIO_UPLOAD_FOLDER_NAME is just the last part of the path after 'static/'
            base_static_path = current_app.config.get('MEDIA_UPLOAD_BASE_DIR', 'static')
            full_file_path = os.path.join(current_app.root_path, base_static_path, upload_folder_config_name, saved_filename)

            try:
                duration_seconds = get_audio_duration(full_file_path)
            except Exception as e:
                current_app.logger.warning(f"Could not get duration for {saved_filename}: {e}")
                # flash("Could not determine audio duration, but file uploaded.", "warning") # Optional

            audio_post = AudioPost(
                title=form.title.data,
                description=form.description.data,
                uploader=current_user,
                audio_filename=saved_filename,
                duration=duration_seconds
            )
            db.session.add(audio_post)
            db.session.commit()
            flash('Audio post uploaded successfully!', 'success')
            return redirect(url_for('main.view_audio_post', audio_id=audio_post.id))
        except Exception as e: # Catch errors from save_audio_file or other issues
            current_app.logger.error(f"Audio upload error: {e}")
            flash(f"An error occurred during audio upload: {e}", "danger")
            # Potentially db.session.rollback() if add was attempted before error

    return render_template('upload_audio.html', title='Upload New Audio', form=form)

@main.route('/audio/<int:audio_id>')
def view_audio_post(audio_id):
    audio_post = AudioPost.query.get_or_404(audio_id)
    # Assuming AUDIO_UPLOAD_FOLDER_NAME is like 'audio_uploads' and it's under 'static'
    audio_folder_name = current_app.config.get('AUDIO_UPLOAD_FOLDER_NAME', 'audio_uploads')
    audio_file_url = url_for('static', filename=f"{audio_folder_name}/{audio_post.audio_filename}")
    return render_template('view_audio_post.html', title=audio_post.title, audio_post=audio_post, audio_file_url=audio_file_url)

@main.route('/audio/<int:audio_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_audio_post(audio_id):
    audio_post = AudioPost.query.get_or_404(audio_id)
    if audio_post.uploader != current_user:
        abort(403)

    form = AudioPostForm(obj=audio_post) # Pre-populate for GET

    original_audio_file_validator = None
    # If it's a POST request and no new file is uploaded, make audio_file optional
    if request.method == 'POST' and not form.audio_file.data:
        # Store original validators and then remove DataRequired
        original_audio_file_validator = form.audio_file.validators
        form.audio_file.validators = [v for v in form.audio_file.validators if not isinstance(v, DataRequired)]

    if form.validate_on_submit():
        audio_post.title = form.title.data
        audio_post.description = form.description.data

        # Handle file replacement (optional, for now we're only editing metadata)
        # If form.audio_file.data was provided, it would be validated by FileAllowed
        # and then you would:
        # 1. Delete old file: os.remove(os.path.join(...old_filename...))
        # 2. Save new file: new_filename = save_audio_file(form.audio_file.data, ...)
        # 3. Update audio_post.audio_filename = new_filename
        # 4. Update audio_post.duration = get_audio_duration(...)

        db.session.commit()
        flash('Audio post updated successfully!', 'success')
        return redirect(url_for('main.view_audio_post', audio_id=audio_post.id))

    # If validation failed on POST and we removed validators, add them back for correct form rendering
    if request.method == 'POST' and original_audio_file_validator is not None:
        form.audio_file.validators = original_audio_file_validator

    # For GET request, populate form fields (already done by obj=audio_post for title/desc)
    # The audio_file field will be empty, which is fine as we're not requiring re-upload for edit.
    return render_template('edit_audio_post.html', title=f'Edit Audio Post: {audio_post.title}', form=form, audio_post=audio_post)

@main.route('/audio/<int:audio_id>/delete', methods=['POST'])
@login_required
def delete_audio_post(audio_id):
    audio_post = AudioPost.query.get_or_404(audio_id)
    if audio_post.uploader != current_user:
        abort(403)

    try:
        # Construct file path for deletion
        upload_folder_config_name = current_app.config.get('AUDIO_UPLOAD_FOLDER_NAME', 'audio_uploads')
        base_static_path = current_app.config.get('MEDIA_UPLOAD_BASE_DIR', 'static')
        file_path = os.path.join(current_app.root_path, base_static_path, upload_folder_config_name, audio_post.audio_filename)

        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        current_app.logger.error(f"Error deleting audio file {audio_post.audio_filename}: {e}")
        flash(f"Error deleting physical audio file. Please contact support.", "warning")
        # Decide if to proceed with DB deletion or not. For now, proceeding.

    db.session.delete(audio_post)
    db.session.commit()
    flash('Audio post deleted successfully!', 'success')
    return redirect(url_for('main.audio_list'))

@main.route('/audio/list')
def audio_list():
    page = request.args.get('page', 1, type=int)
    audio_posts_pagination = AudioPost.query.order_by(AudioPost.timestamp.desc()).paginate(
        page=page, per_page=current_app.config.get('AUDIO_POSTS_PER_PAGE', 10), error_out=False
    )
    audios = audio_posts_pagination.items
    return render_template('audio_list.html', title='All Audio Posts', audio_posts=audios, pagination=audio_posts_pagination)

@main.route('/user/<username>/audio')
def user_audio_list(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    audio_posts_pagination = user.audio_posts.order_by(AudioPost.timestamp.desc()).paginate(
        page=page, per_page=current_app.config.get('AUDIO_POSTS_PER_PAGE', 10), error_out=False
    )
    audios = audio_posts_pagination.items
    # Need to pass audio_folder_name for constructing URLs in the template
    audio_folder_name = current_app.config.get('AUDIO_UPLOAD_FOLDER_NAME', 'audio_uploads')
    return render_template('audio_list.html', title=f'Audio Posts by {username}', audio_posts=audios, pagination=audio_posts_pagination, user=user, audio_folder_name=audio_folder_name)



# -------------------- Virtual Goods Storefront Routes --------------------
from app.core.models import VirtualGood, UserVirtualGood # Added UserVirtualGood
from sqlalchemy.exc import SQLAlchemyError # Added SQLAlchemyError

@main.route('/store')
@login_required
def storefront():
    goods = []
    error_message = None
    try:
        # Attempt to fetch active virtual goods
        # This might fail if the database hasn't been migrated yet after adding VirtualGood model
        goods = VirtualGood.query.filter_by(is_active=True).all()
    except Exception as e:
        current_app.logger.error(f"Error fetching virtual goods from database: {e}")
        error_message = "Store currently unavailable due to a database issue. Please try again later."
        # Depending on how critical this is, you might flash a message or just pass error_message to template
        # flash("Store currently unavailable. Please try again later.", "warning")

    return render_template('storefront.html', title='Store', goods=goods, error_message=error_message)

@main.route('/purchase_virtual_good/<int:good_id>', methods=['POST'])
@login_required
def purchase_virtual_good(good_id):
    # good = VirtualGood.query.get_or_404(good_id) # Will be used when implementing logic
    # For now, just a placeholder
    flash('Purchase functionality is not yet implemented.', 'info')
    return redirect(url_for('main.storefront'))

# -------------------- Subscription Plan Management Routes --------------------
@main.route('/creator/plans/create', methods=['GET', 'POST'])
@login_required
def create_subscription_plan():
    form = SubscriptionPlanForm()
    if form.validate_on_submit():
        try:
            stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
            if not stripe.api_key:
                flash('Stripe integration is not configured (missing secret key).', 'danger')
                return render_template('creator/create_edit_plan.html', title='Create Subscription Plan', form=form)

            # Create Stripe Product
            stripe_product = stripe.Product.create(
                name=form.name.data,
                description=form.description.data or None # Stripe description can be None
            )

            # Create Stripe Price
            stripe_price = stripe.Price.create(
                product=stripe_product.id,
                unit_amount=int(form.price.data * 100), # Price in cents
                currency=form.currency.data.lower(),
                recurring={'interval': form.duration.data}
            )

            features_list = [f.strip() for f in form.features.data.splitlines() if f.strip()]
            features_json_string = json.dumps(features_list) # json import is already there

            new_plan = SubscriptionPlan(
                name=form.name.data,
                description=form.description.data,
                price=form.price.data,
                currency=form.currency.data.upper(), # Store currency in uppercase consistently
                duration=form.duration.data,
                features=features_json_string,
                creator_id=current_user.id,
                stripe_product_id=stripe_product.id,
                stripe_price_id=stripe_price.id
            )
            db.session.add(new_plan)
            db.session.commit()
            flash('Subscription plan created successfully!', 'success')
            return redirect(url_for('main.list_creator_plans'))
        except stripe.error.StripeError as e:
            flash(f'Stripe API Error: {str(e)}', 'danger')
            current_app.logger.error(f"Stripe API error during plan creation: {e}")
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
            current_app.logger.error(f"Error during plan creation: {e}")

    return render_template('creator/create_edit_plan.html', title='Create Subscription Plan', form=form, action="Create")


@main.route('/creator/dashboard/plans')
@login_required
def list_creator_plans():
    plans = SubscriptionPlan.query.filter_by(creator_id=current_user.id).order_by(SubscriptionPlan.created_at.desc()).all()
    return render_template('creator/list_plans.html', title='Your Subscription Plans', plans=plans)


@main.route('/creator/plans/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_creator_plan(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    if plan.creator_id != current_user.id:
        abort(403) # Forbidden

    form = SubscriptionPlanForm(obj=plan if request.method == 'GET' else None)

    if request.method == 'GET':
        if plan.features:
            try:
                features_list = json.loads(plan.features)
                form.features.data = '\n'.join(features_list)
            except json.JSONDecodeError:
                form.features.data = plan.features # Fallback if not valid JSON (though it should be)
                current_app.logger.warning(f"Could not parse features JSON for plan {plan.id} during edit GET: {plan.features}")
        # Price, currency, duration, name, description are pre-filled by obj=plan

    if form.validate_on_submit():
        original_price = plan.price
        original_currency = plan.currency
        original_duration = plan.duration

        plan.name = form.name.data
        plan.description = form.description.data

        features_list = [f.strip() for f in form.features.data.splitlines() if f.strip()]
        plan.features = json.dumps(features_list)

        # Update descriptive fields on Stripe Product
        if plan.stripe_product_id:
            try:
                stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
                stripe.Product.modify(
                    plan.stripe_product_id,
                    name=form.name.data,
                    description=form.description.data or "" # Stripe description can be empty string
                )
            except stripe.error.StripeError as e:
                flash(f'Warning: Error updating Stripe Product details: {str(e)}', 'warning')
                current_app.logger.error(f"Stripe Product.modify error for plan {plan.id}: {e}")
            except Exception as e:
                flash(f'Warning: A non-Stripe error occurred while updating Stripe Product: {str(e)}', 'warning')
                current_app.logger.error(f"Non-Stripe error during Product.modify for plan {plan.id}: {e}")


        # Handle price, currency, duration changes with a note
        price_changed = form.price.data != original_price
        currency_changed = form.currency.data.upper() != original_currency # Compare with consistent casing
        duration_changed = form.duration.data != original_duration

        if price_changed or currency_changed or duration_changed:
            flash('Note: Price, currency, and billing interval changes are complex with existing Stripe Prices. '
                  'This version updates the local database values, but for Stripe, '
                  'you typically need to create a new Price and archive the old one. '
                  'The Stripe Price associated with this plan has NOT been updated.', 'info')

        plan.price = form.price.data
        plan.currency = form.currency.data.upper() # Store consistently
        plan.duration = form.duration.data

        try:
            db.session.commit()
            flash('Subscription plan updated successfully!', 'success')
            return redirect(url_for('main.list_creator_plans'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving updated plan: {str(e)}', 'danger')
            current_app.logger.error(f"Database error updating plan {plan.id}: {e}")

    return render_template('creator/create_edit_plan.html', title=f'Edit Plan: {plan.name}', form=form, plan=plan, action="Edit")


@main.route('/creator/plans/<int:plan_id>/deactivate', methods=['POST'])
@login_required
def deactivate_creator_plan(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    if plan.creator_id != current_user.id:
        abort(403) # Forbidden

    if not plan.is_active:
        flash('This plan is already inactive.', 'info')
        return redirect(url_for('main.list_creator_plans'))

    plan.is_active = False
    action_successful = True # Flag to track if all operations were successful

    # Archive Stripe Price
    if plan.stripe_price_id:
        try:
            stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
            stripe.Price.modify(plan.stripe_price_id, active=False)
            flash('Stripe Price archived successfully.', 'info')
        except stripe.error.StripeError as e:
            action_successful = False
            flash(f'Could not archive Stripe Price: {str(e)}. Please check your Stripe dashboard. Local plan will still be marked as inactive.', 'warning')
            current_app.logger.error(f"Stripe Price.modify error for plan {plan.id}, price {plan.stripe_price_id}: {e}")
        except Exception as e:
            action_successful = False
            flash(f'A non-Stripe error occurred while archiving Stripe Price: {str(e)}. Local plan will still be marked as inactive.', 'warning')
            current_app.logger.error(f"Non-Stripe error during Price.modify for plan {plan.id}, price {plan.stripe_price_id}: {e}")


    # Optionally, attempt to archive Stripe Product
    # This is a simplified attempt. In reality, you'd check if other active prices exist for this product.
    if plan.stripe_product_id:
        try:
            stripe.api_key = current_app.config['STRIPE_SECRET_KEY'] # Ensure API key is set if not done above or if Price modify failed
            # Check if product has other active prices (simplified check - assumes product might be shared)
            # A more robust check would list all prices for the product and see if any others are active.
            # For now, we just try to deactivate and catch error if it fails (e.g. due to active prices).
            stripe.Product.modify(plan.stripe_product_id, active=False)
            flash('Stripe Product also marked as inactive (if applicable).', 'info')
        except stripe.error.StripeError as e:
            # This error is less critical if the price is already inactive or if product has other active prices.
            flash(f'Note: Could not automatically archive Stripe Product ({plan.stripe_product_id}): {str(e)}. This might be because other active prices are still attached to it. You may need to manage it in your Stripe dashboard.', 'notice')
            current_app.logger.warning(f"Stripe Product.modify error for product {plan.stripe_product_id} (plan {plan.id}): {e}")
        except Exception as e:
            flash(f'Note: A non-Stripe error occurred while archiving Stripe Product ({plan.stripe_product_id}): {str(e)}.', 'notice')
            current_app.logger.warning(f"Non-Stripe error during Product.modify for product {plan.stripe_product_id} (plan {plan.id}): {e}")

    try:
        db.session.commit()
        if action_successful:
            flash('Subscription plan deactivated successfully.', 'success')
        else:
            flash('Subscription plan marked as inactive locally, but there were issues with Stripe operations. Please review warnings.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deactivating plan locally: {str(e)}', 'danger')
        current_app.logger.error(f"Database error deactivating plan {plan.id}: {e}")

    return redirect(url_for('main.list_creator_plans'))


@main.route('/creator/dashboard/subscribers')
@login_required
def list_creator_subscribers():
    # Fetch active subscriptions to plans created by the current user
    # Ensure User and SubscriptionPlan models are correctly joined to UserSubscription
    subscriptions = UserSubscription.query \
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id) \
        .join(User, UserSubscription.subscriber_id == User.id) \
        .filter(SubscriptionPlan.creator_id == current_user.id, UserSubscription.status == 'active') \
        .options(db.joinedload(UserSubscription.subscriber), db.joinedload(UserSubscription.plan)) \
        .order_by(UserSubscription.start_date.desc()) \
        .all()

    return render_template('creator/list_subscribers.html', title='Active Subscribers', subscriptions=subscriptions)


# -------------------- User's Own Subscriptions Route --------------------
@main.route('/user/subscriptions')
@login_required
def my_subscriptions():
    subscriptions = UserSubscription.query \
        .filter_by(subscriber_id=current_user.id) \
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id) \
        .join(User, SubscriptionPlan.creator_id == User.id) \
        .options(
            db.joinedload(UserSubscription.plan).joinedload(SubscriptionPlan.creator)
        ) \
        .order_by(UserSubscription.start_date.desc()) \
        .all()

    return render_template('user/my_subscriptions.html', title='My Subscriptions', subscriptions=subscriptions)


# Developer Portal Routes
from app.core.forms import ApplicationRegistrationForm, ApplicationEditForm # New forms
from app.core.models import Application # OAuth Application model
import secrets # For client secret generation

@main.route('/developer/dashboard')
@login_required
def developer_dashboard():
    applications = Application.query.filter_by(owner_user_id=current_user.id).order_by(Application.created_at.desc()).all()
    return render_template('developer/dashboard.html', applications=applications, title="Developer Dashboard")

@main.route('/developer/applications/register', methods=['GET', 'POST'])
@login_required
def register_application():
    form = ApplicationRegistrationForm()
    if form.validate_on_submit():
        # Generate client_id (done by model's __init__) and client_secret
        new_plain_client_secret = secrets.token_urlsafe(32)

        # Process redirect_uris: store as space-separated string. Model uses Text.
        # Newlines from TextAreaField should be converted.
        processed_redirect_uris = ' '.join(form.redirect_uris.data.splitlines())

        application = Application(
            name=form.name.data,
            description=form.description.data,
            redirect_uris=processed_redirect_uris,
            owner_user_id=current_user.id
            # client_id is auto-generated by model
        )
        application.set_client_secret(new_plain_client_secret) # Hash and set the secret

        db.session.add(application)
        db.session.commit()

        # Flash the new client secret to be shown once.
        # The actual secret is new_plain_client_secret.
        # The template for view_application will need to handle this flashed message.
        flash(new_plain_client_secret, 'new_client_secret')
        flash('Application registered successfully!', 'success')
        return redirect(url_for('main.view_application', app_id=application.id))

    return render_template('developer/register_application.html', title='Register Application', form=form)

@main.route('/developer/applications/<int:app_id>', methods=['GET'])
@login_required
def view_application(app_id):
    application = Application.query.get_or_404(app_id)
    if application.owner_user_id != current_user.id:
        flash('You are not authorized to view this application.', 'danger')
        return redirect(url_for('main.developer_dashboard')) # Or abort(403)

    # For redirect_uris, split by space for display if stored that way.
    # The template currently handles .split()

    return render_template('developer/view_application.html', title=f"View Application: {application.name}", application=application)

@main.route('/developer/applications/<int:app_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_application(app_id):
    application = Application.query.get_or_404(app_id)
    if application.owner_user_id != current_user.id:
        flash('You are not authorized to edit this application.', 'danger')
        return redirect(url_for('main.developer_dashboard')) # Or abort(403)

    form = ApplicationEditForm(obj=application) # Pre-populate form with existing data

    # When form is loaded (GET request), populate redirect_uris correctly from space-separated to newline for TextArea
    if request.method == 'GET':
        form.redirect_uris.data = '\n'.join(application.redirect_uris.split())

    if form.validate_on_submit():
        application.name = form.name.data
        application.description = form.description.data
        application.redirect_uris = ' '.join(form.redirect_uris.data.splitlines())

        db.session.commit()
        flash('Application updated successfully!', 'success')
        return redirect(url_for('main.view_application', app_id=application.id))

    return render_template('developer/edit_application.html', title=f"Edit Application: {application.name}", form=form, application=application)

@main.route('/developer/applications/<int:app_id>/delete', methods=['POST']) # Should be POST for deletion
@login_required
def delete_application(app_id):
    application = Application.query.get_or_404(app_id)
    if application.owner_user_id != current_user.id:
        flash('You are not authorized to delete this application.', 'danger')
        return redirect(url_for('main.developer_dashboard')) # Or abort(403)

    # AccessTokens are set to cascade delete via model relationship's cascade='all, delete-orphan'
    db.session.delete(application)
    db.session.commit()

    flash('Application deleted successfully.', 'success')
    return redirect(url_for('main.developer_dashboard'))

@main.route('/developer/applications/<int:app_id>/regenerate_secret', methods=['POST'])
@login_required
def regenerate_secret(app_id):
    application = Application.query.get_or_404(app_id)
    if application.owner_user_id != current_user.id:
        flash('You are not authorized to modify this application.', 'danger')
        return redirect(url_for('main.developer_dashboard'))

    new_plain_client_secret = secrets.token_urlsafe(32)
    application.set_client_secret(new_plain_client_secret) # Hash and set the new secret
    db.session.commit()

    # Flash the new client secret to be shown once on the view page.
    flash(new_plain_client_secret, 'new_client_secret')
    flash('Client secret regenerated successfully. Please store the new secret securely.', 'success_secret_regenerated')
    return redirect(url_for('main.view_application', app_id=application.id))

@main.route('/user/subscriptions/<int:subscription_id>/cancel', methods=['POST'])
@login_required
def cancel_user_subscription(subscription_id):
    user_sub = UserSubscription.query.get_or_404(subscription_id)

    if user_sub.subscriber_id != current_user.id:
        current_app.logger.warning(f"User {current_user.id} attempt to cancel subscription {subscription_id} not belonging to them.")
        abort(403) # Forbidden

    # Define cancellable states. 'past_due' can also be cancelled by user, Stripe might retry payment or eventually cancel.
    cancellable_states = ['active', 'trialing', 'past_due']
    if user_sub.status not in cancellable_states:
        flash(f"This subscription is currently '{user_sub.status.replace('_', ' ').capitalize()}' and cannot be cancelled through this action or is already processing a cancellation.", 'info')
        return redirect(url_for('main.my_subscriptions'))

    if user_sub.stripe_subscription_id:
        try:
            stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
            # Request Stripe to cancel the subscription at the end of the current billing period.
            # The actual 'cancelled' status and final end_date will be set by webhook (e.g., customer.subscription.updated/deleted).
            stripe_subscription_object = stripe.Subscription.retrieve(user_sub.stripe_subscription_id)

            if stripe_subscription_object.status == 'canceled':
                 flash('This subscription has already been canceled with Stripe.', 'info')
            elif stripe_subscription_object.cancel_at_period_end:
                flash('This subscription is already scheduled to be cancelled at the end of the current billing period.', 'info')
            else:
                stripe.Subscription.modify(
                    user_sub.stripe_subscription_id,
                    cancel_at_period_end=True
                )
                # Optionally, update local status to something like 'pending_cancellation'
                # user_sub.status = 'pending_cancellation'
                # db.session.commit()
                flash('Your subscription cancellation has been requested. It will be finalized at the end of your current billing period.', 'success')
                current_app.logger.info(f"User {current_user.id} requested cancellation for Stripe subscription {user_sub.stripe_subscription_id} at period end.")

        except stripe.error.StripeError as e:
            flash(f'Error requesting subscription cancellation with payment provider: {str(e)}', 'danger')
            current_app.logger.error(f"Stripe API error cancelling subscription {user_sub.stripe_subscription_id} for user {current_user.id}: {e}")
        except Exception as e:
            flash(f'An unexpected error occurred while processing your cancellation request: {str(e)}', 'danger')
            current_app.logger.error(f"Unexpected error cancelling subscription {user_sub.stripe_subscription_id} for user {current_user.id}: {e}")
    else:
        # Fallback for local subscriptions without a Stripe ID (should be rare for active ones)
        current_app.logger.warning(f"UserSubscription {user_sub.id} for user {current_user.id} has no stripe_subscription_id. Cancelling locally.")
        user_sub.status = 'cancelled'
        user_sub.end_date = datetime.now(timezone.utc)
        try:
            db.session.commit()
            flash('Your subscription has been cancelled locally as no payment provider ID was found.', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'Error cancelling local subscription: {str(e)}', 'danger')
            current_app.logger.error(f"Database error cancelling local subscription {user_sub.id} for user {current_user.id}: {e}")

    return redirect(url_for('main.my_subscriptions'))


# -------------------- Stripe Customer Portal Session Route --------------------
@main.route('/stripe/create-customer-portal-session', methods=['POST'])
@login_required
def create_customer_portal_session():
    stripe_customer_id = current_user.stripe_customer_id

    if not stripe_customer_id:
        # Although flash is usually for rendered templates, it can be useful for server-side logging/awareness.
        # The primary response for an AJAX call should be JSON.
        flash('No billing information found for this user.', 'info')
        current_app.logger.info(f"User {current_user.id} attempted to access Stripe portal without a stripe_customer_id.")
        return jsonify({'error': 'No Stripe customer ID found for user.'}), 404 # Or 400 Bad Request

    # This is the URL to which the user will be redirected after they are done managing their billing on Stripe.
    return_url = url_for('main.my_subscriptions', _external=True)

    try:
        stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY')
        if not stripe.api_key:
            current_app.logger.error("Stripe secret key is not configured for portal session creation.")
            return jsonify({'error': 'Payment provider configuration error.'}), 500

        portal_session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url
        )
        return jsonify({'portal_url': portal_session.url})

    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe Billing Portal session creation failed for customer {stripe_customer_id}: {str(e)}")
        return jsonify({'error': f'Could not create billing portal session: {str(e)}'}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error creating billing portal session for customer {stripe_customer_id}: {e}")
        return jsonify({'error': 'An unexpected error occurred while creating billing portal session.'}), 500


# -------------------- Stripe Checkout Session Route --------------------
@main.route('/api/subscriptions/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    try:
        stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY')
        if not stripe.api_key:
            current_app.logger.error("Stripe secret key is not configured.")
            return jsonify({'error': 'Payment provider not configured.'}), 500

        data = request.get_json()
        if not data or 'plan_id' not in data:
            return jsonify({'error': 'Missing plan_id in request.'}), 400

        plan_id = data['plan_id']
        # Ensure plan_id is an integer if it comes as a string from JSON
        try:
            plan_id = int(plan_id)
        except ValueError:
            return jsonify({'error': 'Invalid plan_id format.'}), 400

        plan = SubscriptionPlan.query.get(plan_id)

        if not plan:
            return jsonify({'error': 'Subscription plan not found.'}), 404

        if not plan.stripe_price_id:
            current_app.logger.error(f"SubscriptionPlan ID {plan.id} ('{plan.name}') is missing Stripe Price ID.")
            return jsonify({'error': 'Subscription plan is not configured for payments.'}), 500

        stripe_customer_id = current_user.stripe_customer_id
        if not stripe_customer_id:
            try:
                customer = stripe.Customer.create(
                    email=current_user.email,
                    name=current_user.username
                    # Add other metadata if needed, e.g., 'user_id': current_user.id
                )
                stripe_customer_id = customer.id
                current_user.stripe_customer_id = stripe_customer_id
                db.session.commit()
            except stripe.error.StripeError as e:
                current_app.logger.error(f"Stripe customer creation failed: {e}")
                return jsonify({'error': str(e)}), 500
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Database error after Stripe customer creation: {e}")
                return jsonify({'error': 'Could not save customer information.'}), 500

        base_url = request.url_root
        if base_url.endswith('/'):
            base_url = base_url[:-1]

        # Using url_for for dynamic URL generation is safer and more flexible.
        # Assuming 'main.index' is a valid route. Adjust if success/cancel pages are different.
        success_url = url_for('main.index', _external=True, _anchor='subscription-success') + '&session_id={CHECKOUT_SESSION_ID}'
        cancel_url = url_for('main.index', _external=True, _anchor='subscription-cancelled')

        try:
            checkout_session = stripe.checkout.Session.create(
                customer=stripe_customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price': plan.stripe_price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                subscription_data={
                    'metadata': {
                        'user_id': str(current_user.id),
                        'plan_id': str(plan.id)
                    }
                }
            )
            return jsonify({'sessionId': checkout_session.id})
        except stripe.error.StripeError as e:
            current_app.logger.error(f"Stripe Checkout Session creation failed: {e}")
            return jsonify({'error': str(e)}), 500
        except Exception as e:
            current_app.logger.error(f"Generic error during Checkout Session creation: {e}")
            return jsonify({'error': 'Could not initiate payment session.'}), 500

    except Exception as e:
        current_app.logger.error(f"Unexpected error in create_checkout_session: {e}")
        return jsonify({'error': 'An unexpected error occurred.'}), 500


# -------------------- Stripe Webhook Handler --------------------
@main.route('/api/stripe-webhooks', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')

    if not endpoint_secret:
        current_app.logger.error("Stripe webhook secret is not configured.")
        return jsonify({'error': 'Webhook secret not configured.'}), 500

    event = None
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e: # Invalid payload
        current_app.logger.error(f"Webhook error while parsing payload: {str(e)}")
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e: # Invalid signature
        current_app.logger.error(f"Webhook signature verification failed: {str(e)}")
        return jsonify({'error': 'Invalid signature'}), 400
    except Exception as e: # Other construction errors
        current_app.logger.error(f"Webhook event construction error: {str(e)}")
        return jsonify({'error': 'Could not construct webhook event.'}), 500

    # Initialize Stripe API key for any further API calls if needed
    # Although for webhook event processing, usually the event object contains all necessary info.
    # stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY')

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        current_app.logger.info(f"Processing checkout.session.completed: {session.get('id')}")
        stripe_subscription_id = session.get('subscription')
        stripe_customer_id = session.get('customer') # For verification or logging

        # Corrected metadata path based on Stripe's structure for subscription_data
        subscription_data = session.get('subscription_data', {})
        metadata = {}
        if subscription_data: # subscription_data can be None if not a subscription mode checkout
            metadata = subscription_data.get('metadata', {})

        user_id = metadata.get('user_id')
        plan_id = metadata.get('plan_id')

        if user_id and plan_id and stripe_subscription_id:
            user = User.query.get(user_id)
            plan = SubscriptionPlan.query.get(plan_id)

            if user and plan:
                try:
                    # Retrieve the subscription to get current period details
                    stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
                    current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start, tz=timezone.utc)
                    current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc)

                    # Check for existing subscription to update, or create new
                    user_subscription = UserSubscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
                    if not user_subscription:
                        user_subscription = UserSubscription.query.filter_by(subscriber_id=user.id, plan_id=plan.id, status='pending').first() # Example for pending
                        if not user_subscription:
                             user_subscription = UserSubscription()

                    user_subscription.subscriber_id = user.id
                    user_subscription.plan_id = plan.id
                    user_subscription.stripe_subscription_id = stripe_subscription_id
                    user_subscription.stripe_customer_id = stripe_customer_id # Save customer_id if not already linked
                    user_subscription.status = 'active' # Or stripe_sub.status
                    user_subscription.start_date = current_period_start
                    user_subscription.end_date = current_period_end

                    db.session.add(user_subscription)
                    db.session.commit()
                    current_app.logger.info(f"UserSubscription created/updated for user {user_id}, plan {plan_id}, stripe_sub {stripe_subscription_id}")

                    # Send notification to subscriber
                    if user and plan: # plan is already fetched, user is already fetched
                        creator = User.query.get(plan.creator_id)
                        if creator:
                            notification_message = f"You are now subscribed to {creator.username}'s '{plan.name}' plan!"
                            notification = Notification(
                                recipient_id=user.id,
                                actor_id=creator.id,
                                type='subscription_started'
                            )
                            db.session.add(notification)
                            db.session.commit() # Commit notification

                            socketio.emit('new_notification', {
                                'type': 'subscription_started',
                                'message': notification_message,
                                'recipient_id': user.id,
                                'plan_name': plan.name,
                                'creator_username': creator.username
                            }, room=str(user.id))
                            current_app.logger.info(f"Sent 'subscription_started' notification to user {user.id}")

                except stripe.error.StripeError as e:
                    current_app.logger.error(f"Stripe API error processing checkout.session.completed: {e}")
                    # Don't necessarily return 500 to Stripe, as they might retry. Log and investigate.
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"Database error processing checkout.session.completed: {e}")
            else:
                current_app.logger.warning(f"User or Plan not found for checkout.session.completed. User ID: {user_id}, Plan ID: {plan_id}")
        else:
            current_app.logger.warning(f"Missing metadata or subscription ID in checkout.session.completed: UserID-{user_id}, PlanID-{plan_id}, StripeSubID-{stripe_subscription_id}")

    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        current_app.logger.info(f"Processing invoice.payment_succeeded: {invoice.get('id')}")
        stripe_subscription_id = invoice.get('subscription')
        if stripe_subscription_id:
            subscription = UserSubscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
            if subscription:
                try:
                    stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
                    subscription.end_date = datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc)
                    subscription.status = 'active' # Ensure active on payment success
                    db.session.commit()
                    current_app.logger.info(f"UserSubscription {subscription.id} updated by invoice.payment_succeeded.")

                    # Send notification for renewal
                    if subscription.status == 'active': # Confirm it's active after payment
                        user = User.query.get(subscription.subscriber_id)
                        plan = SubscriptionPlan.query.get(subscription.plan_id)
                        if user and plan and plan.creator: # Assumes plan.creator relationship is loaded or accessible
                            renewal_end_date_str = subscription.end_date.strftime('%Y-%m-%d %H:%M UTC') if subscription.end_date else "the next period"
                            notification_message = f"Your subscription to {plan.creator.username}'s '{plan.name}' plan has been successfully renewed until {renewal_end_date_str}."
                            notification = Notification(
                                recipient_id=user.id,
                                actor_id=plan.creator.id,
                                type='subscription_renewed'
                            )
                            db.session.add(notification)
                            db.session.commit()

                            socketio.emit('new_notification', {
                                'type': 'subscription_renewed',
                                'message': notification_message,
                                'recipient_id': user.id,
                                'plan_name': plan.name,
                                'creator_username': plan.creator.username,
                                'renewal_date': renewal_end_date_str
                            }, room=str(user.id))
                            current_app.logger.info(f"Sent 'subscription_renewed' notification to user {user.id}")

                except stripe.error.StripeError as e:
                    current_app.logger.error(f"Stripe API error processing invoice.payment_succeeded: {e}")
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"Database error processing invoice.payment_succeeded: {e}")
            else:
                 current_app.logger.warning(f"UserSubscription not found for stripe_subscription_id {stripe_subscription_id} from invoice.payment_succeeded.")


    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        current_app.logger.info(f"Processing invoice.payment_failed: {invoice.get('id')}")
        stripe_subscription_id = invoice.get('subscription')
        if stripe_subscription_id:
            subscription = UserSubscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
            if subscription:
                subscription.status = 'past_due' # Or a more specific status based on your needs
                try:
                    db.session.commit()
                    current_app.logger.info(f"UserSubscription {subscription.id} status set to past_due.")

                    # Send notification for payment failure
                    if subscription.status == 'past_due':
                        user = User.query.get(subscription.subscriber_id)
                        plan = SubscriptionPlan.query.get(subscription.plan_id)
                        if user and plan and plan.creator:
                            notification_message = f"Action required: Payment failed for your subscription to {plan.creator.username}'s '{plan.name}' plan. Please update your payment method via 'Manage Billing'."
                            notification = Notification(
                                recipient_id=user.id,
                                actor_id=plan.creator.id,
                                type='subscription_payment_failed'
                            )
                            db.session.add(notification)
                            db.session.commit()

                            socketio.emit('new_notification', {
                                'type': 'subscription_payment_failed',
                                'message': notification_message,
                                'recipient_id': user.id,
                                'plan_name': plan.name,
                                'creator_username': plan.creator.username
                            }, room=str(user.id))
                            current_app.logger.info(f"Sent 'subscription_payment_failed' notification to user {user.id}")

                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"Database error processing invoice.payment_failed: {e}")
            else:
                current_app.logger.warning(f"UserSubscription not found for stripe_subscription_id {stripe_subscription_id} from invoice.payment_failed.")


    elif event['type'] == 'customer.subscription.deleted':
        stripe_sub_object = event['data']['object'] # This is a Stripe Subscription object
        current_app.logger.info(f"Processing customer.subscription.deleted: {stripe_sub_object.get('id')}")
        stripe_subscription_id = stripe_sub_object.get('id')
        if stripe_subscription_id:
            subscription = UserSubscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
            if subscription:
                subscription.status = 'cancelled'
                if stripe_sub_object.get('canceled_at'):
                    subscription.end_date = datetime.fromtimestamp(stripe_sub_object.canceled_at, tz=timezone.utc)
                # else: end_date might remain as current_period_end or be set to now
                try:
                    db.session.commit()
                    current_app.logger.info(f"UserSubscription {subscription.id} status set to cancelled.")
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"Database error processing customer.subscription.deleted: {e}")
            else:
                current_app.logger.warning(f"UserSubscription not found for stripe_subscription_id {stripe_subscription_id} from customer.subscription.deleted.")

    elif event['type'] == 'customer.subscription.updated':
        stripe_sub_object = event['data']['object'] # This is a Stripe Subscription object
        current_app.logger.info(f"Processing customer.subscription.updated: {stripe_sub_object.get('id')}")
        stripe_subscription_id = stripe_sub_object.get('id')
        if stripe_subscription_id:
            subscription = UserSubscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
            if subscription:
                # Map Stripe status to your application's status if necessary
                # For example, Stripe 'trialing' could be 'active' or 'trialing' in your system
                new_status = stripe_sub_object.status # e.g., active, past_due, trialing, canceled
                subscription.status = new_status

                # Update period end
                if stripe_sub_object.current_period_end:
                    subscription.end_date = datetime.fromtimestamp(stripe_sub_object.current_period_end, tz=timezone.utc)

                # If canceled, ensure end_date reflects cancellation time if available and appropriate
                if new_status == 'canceled' and stripe_sub_object.canceled_at:
                    subscription.end_date = datetime.fromtimestamp(stripe_sub_object.canceled_at, tz=timezone.utc)

                try:
                    db.session.commit()
                    current_app.logger.info(f"UserSubscription {subscription.id} updated by customer.subscription.updated. New status: {new_status}")

                    # Send notification if subscription is definitively cancelled
                    if new_status == 'canceled':
                        user = User.query.get(subscription.subscriber_id)
                        plan = SubscriptionPlan.query.get(subscription.plan_id)
                        if user and plan and plan.creator:
                            end_date_str = datetime.fromtimestamp(stripe_sub_object.canceled_at, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if stripe_sub_object.canceled_at else "the end of the current period"
                            notification_message = f"Your subscription to {plan.creator.username}'s '{plan.name}' plan has been cancelled, effective {end_date_str}."
                            notification = Notification(
                                recipient_id=user.id,
                                actor_id=plan.creator.id,
                                type='subscription_cancelled'
                            )
                            db.session.add(notification)
                            db.session.commit()

                            socketio.emit('new_notification', {
                                'type': 'subscription_cancelled',
                                'message': notification_message,
                                'recipient_id': user.id,
                                'plan_name': plan.name,
                                'creator_username': plan.creator.username,
                                'cancellation_date': end_date_str
                            }, room=str(user.id))
                            current_app.logger.info(f"Sent 'subscription_cancelled' notification to user {user.id}")

                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(f"Database error processing customer.subscription.updated: {e}")
            else:
                current_app.logger.warning(f"UserSubscription not found for stripe_subscription_id {stripe_subscription_id} from customer.subscription.updated.")
    else:
        current_app.logger.info(f"Unhandled Stripe webhook event type: {event['type']}")

    return jsonify({'status': 'success'}), 200


@main.route('/set-theme-preference', methods=['POST'])
@login_required
def set_theme_preference():
    data = request.get_json()
    if not data or 'theme' not in data:
        return jsonify({'status': 'error', 'message': 'Missing theme data.'}), 400

    theme = data['theme']
    if theme not in ['light', 'dark', 'default']: # Allow 'default' as well
        return jsonify({'status': 'error', 'message': 'Invalid theme value.'}), 400

    if current_user.is_authenticated: # Redundant due to @login_required, but good for clarity
        current_user.theme_preference = theme
        try:
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Theme preference saved.'})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error saving theme preference for user {current_user.id}: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to save theme preference.'}), 500
    else:
        # This case should ideally not be hit due to @login_required
        return jsonify({'status': 'error', 'message': 'User not authenticated.'}), 401
