import os
import secrets
from functools import wraps
from flask import current_app, redirect, url_for, flash, abort
from PIL import Image # For image resizing - will need to install Pillow
from werkzeug.utils import secure_filename # For secure filenames

import re # For mention processing

# Mutagen (for audio duration)
try:
    from mutagen.mp3 import MP3
    from mutagen.wave import WAVE
    from mutagen.oggvorbis import OggVorbis
    from mutagen.aac import AAC
    from mutagen.mp4 import MP4 # For M4A/MP4 AAC files
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3NoHeaderError # Specific error for some MP3s
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    # Optionally log that mutagen is not available if it's considered important
    # current_app.logger.info("Mutagen library not found. Audio duration extraction will be disabled.")

# Imports for recommendation functions
from sqlalchemy import func, desc, not_, and_, or_, distinct
from app import db # Assuming db instance is available in app package
from app.core.models import User, Post, Reaction, Comment, Hashtag, Group, GroupMembership, followers, Mention, HistoricalAnalytics, post_hashtags, Article, Event as AppEvent, UserSubscription, SubscriptionPlan, UserPoints, ActivityLog # Added UserPoints, ActivityLog
from datetime import datetime, timedelta, timezone # Ensure timezone is imported
from app.utils.gamification_utils import check_and_award_badges # Import for badge checking

# Imports for iCalendar generation
from icalendar import Calendar, Event as IcsEvent

def get_current_utc():
    """Returns the current datetime in UTC with timezone info."""
    return datetime.now(timezone.utc)

def slugify(text_to_slugify: str, model_to_check=None, target_column_name: str = 'slug', max_slug_length: int = 200) -> str:
    """
    Generates a URL-friendly slug from a string, ensuring uniqueness.
    """
    if model_to_check is None:
        model_to_check = Article # Default to Article model

    if not text_to_slugify or not text_to_slugify.strip():
        # If input is empty, generate a purely random slug
        base_slug = secrets.token_hex(8)
    else:
        # Convert to lowercase
        slug = text_to_slugify.lower()
        # Remove non-alphanumeric characters (except spaces and hyphens)
        slug = re.sub(r'[^\w\s-]', '', slug).strip()
        # Replace spaces with hyphens
        slug = re.sub(r'\s+', '-', slug)
        # Consolidate multiple hyphens
        slug = re.sub(r'-+', '-', slug)
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        base_slug = slug

        if not base_slug: # If all characters were special chars and removed
            base_slug = secrets.token_hex(8)

    # Truncate base_slug to ensure space for potential suffixes
    # Max length for suffix like "-xxxxxx" (1 hyphen + 6 hex chars) is 7
    # Initial truncation to leave space for this
    effective_max_base_length = max_slug_length - 8
    if len(base_slug) > effective_max_base_length:
        base_slug = base_slug[:effective_max_base_length]

    # Ensure base_slug is not empty after truncation, and re-strip hyphens
    base_slug = base_slug.strip('-')
    if not base_slug: # If truncation made it empty or just hyphens
         base_slug = secrets.token_hex(min(8, effective_max_base_length if effective_max_base_length > 0 else 8))


    current_slug_candidate = base_slug
    attempt_counter = 0
    max_attempts = 15 # Max attempts before switching to fully random slug

    while True:
        existing_record = model_to_check.query.filter(getattr(model_to_check, target_column_name) == current_slug_candidate).first()
        if not existing_record:
            return current_slug_candidate # Slug is unique

        attempt_counter += 1
        if attempt_counter > max_attempts:
            # Fallback to a highly random slug if too many collisions
            # Ensure this random slug also fits max_slug_length
            random_len = min(max_slug_length, 16) # e.g. 16 hex chars
            current_slug_candidate = secrets.token_hex(random_len // 2)
            # One last check for this highly random slug (extremely unlikely to collide)
            if not model_to_check.query.filter(getattr(model_to_check, target_column_name) == current_slug_candidate).first():
                return current_slug_candidate
            else:
                # This case is astronomically rare. Could raise an error or log.
                # For now, we'll just return it and assume it's okay, or let DB constraint catch it.
                current_app.logger.error(f"Slugify: Extremely rare collision with fully random slug {current_slug_candidate}")
                return current_slug_candidate # Or raise Exception("Could not generate unique slug after max attempts and random fallback.")


        # Generate suffix
        suffix = secrets.token_hex(3) # 6 characters long

        # Calculate max length for the base part of the slug to accommodate the suffix
        max_len_for_base_with_suffix = max_slug_length - len(suffix) - 1 # -1 for the hyphen

        # Truncate the original base_slug if necessary
        truncated_base = base_slug
        if len(base_slug) > max_len_for_base_with_suffix:
            truncated_base = base_slug[:max_len_for_base_with_suffix]

        current_slug_candidate = f"{truncated_base}-{suffix}"
        # Ensure the final slug with suffix does not exceed max_slug_length
        if len(current_slug_candidate) > max_slug_length:
             current_slug_candidate = current_slug_candidate[:max_slug_length]


# Define allowed extensions comprehensively at the top
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}


def save_picture(form_picture_field):
    random_hex = secrets.token_hex(8)
    original_filename = secure_filename(form_picture_field.filename)
    _, f_ext = os.path.splitext(original_filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static/images', picture_fn)

    # Output size for resizing
    output_size = (256, 256) # Profile picture size
    i = Image.open(form_picture_field)
    i.thumbnail(output_size)
    # Convert to RGB if it's a P or RGBA mode image (common for PNGs)
    # to ensure JPEG saving doesn't fail and to remove alpha channel if not needed.
    if i.mode in ("P", "RGBA"):
        i = i.convert("RGB")
    i.save(picture_path, optimize=True, quality=85)

    return picture_fn

def save_media_file(form_media_file, upload_folder_name='media_items'):
    """
    Saves an uploaded media file (image or video) to a specified folder,
    performing resizing for images.
    Returns a tuple (saved_filename, media_type).
    Raises ValueError for unsupported file types.
    """
    random_hex = secrets.token_hex(12)
    # Use secure_filename to ensure the original filename is safe before extracting extension
    original_filename = secure_filename(form_media_file.filename)
    _, f_ext_with_dot = os.path.splitext(original_filename)
    f_ext = f_ext_with_dot.lower().lstrip('.')

    saved_filename = random_hex + f_ext_with_dot.lower()
    media_type = None

    if f_ext in ALLOWED_IMAGE_EXTENSIONS:
        media_type = 'image'
    elif f_ext in ALLOWED_VIDEO_EXTENSIONS:
        media_type = 'video'
    else:
        raise ValueError(f"Unsupported file type: '.{f_ext}'. Allowed images: {ALLOWED_IMAGE_EXTENSIONS}, Allowed videos: {ALLOWED_VIDEO_EXTENSIONS}")

    # The 'upload_folder_name' parameter is expected to be the path relative to app.root_path
    # e.g., 'static/media_items' or as retrieved by routes:
    # current_app.config.get('MEDIA_ITEMS_UPLOAD_FOLDER', 'static/media_items')

    # Construct the full save path directory
    full_save_path_dir = os.path.join(current_app.root_path, upload_folder_name)

    # Ensure the specific directory for the media type exists
    os.makedirs(full_save_path_dir, exist_ok=True)

    full_file_path = os.path.join(full_save_path_dir, saved_filename)

    if media_type == 'image':
        img = Image.open(form_media_file)
        output_max_width = 1200 # Max width for general media items
        if img.width > output_max_width:
            aspect_ratio = img.height / img.width
            new_height = int(output_max_width * aspect_ratio)
            img = img.resize((output_max_width, new_height), Image.Resampling.LANCZOS)

        if img.mode in ("P", "RGBA"): # Convert PNGs with palette or alpha to RGB for broader compatibility and smaller size
            img = img.convert("RGB")
        img.save(full_file_path, optimize=True, quality=85)
    elif media_type == 'video':
        form_media_file.save(full_file_path)

    return saved_filename, media_type

def save_group_image(form_image_field):
    random_hex = secrets.token_hex(10)
    original_filename = secure_filename(form_image_field.filename)
    _, f_ext = os.path.splitext(original_filename)
    image_fn = random_hex + f_ext

    upload_path_from_config = current_app.config.get('UPLOAD_FOLDER_GROUP_IMAGES', 'app/static/group_images_default')
    picture_path = os.path.join(current_app.root_path, upload_path_from_config, image_fn)

    os.makedirs(os.path.dirname(picture_path), exist_ok=True)

    # Define output size for group images. Let's use 400x400.
    # Resize while maintaining aspect ratio and cropping if necessary, or just resize to fit.
    # For simplicity, let's resize to fit within 400x400, similar to profile pics but larger.
    output_size = (400, 400)
    img = Image.open(form_image_field)

    # To maintain aspect ratio and fit within the bounds, we can use thumbnail.
    # If we want a fixed size, we might need to crop.
    # Let's use thumbnail to keep it simple and preserve aspect ratio.
    img.thumbnail(output_size, Image.Resampling.LANCZOS)

    # If image is smaller than output_size, thumbnail won't enlarge it.
    # If we want a consistent size, and potentially crop, a different approach is needed.
    # For now, thumbnail is acceptable (it scales down if larger, keeps if smaller).

    img.save(picture_path)
    return image_fn

from flask_login import current_user
from app.core.models import Notification # Keep this specific import for Notification
from app.core.forms import SearchForm # Import SearchForm

def inject_unread_notification_count():
    if current_user.is_authenticated:
        count = Notification.query.filter_by(recipient_id=current_user.id, is_read=False).count()
    else:
        count = 0
    return {'unread_notification_count': count}

def inject_search_form():
    form = SearchForm()
    return {'search_form': form}

# ALLOWED_IMAGE_EXTENSIONS and ALLOWED_VIDEO_EXTENSIONS are already defined at the top.

def save_story_media(form_media_file):
    # This function can potentially be refactored to use save_media_file
    # by passing a specific upload_folder_name like 'story_media'
    # and handling any story-specific resizing/processing if different.
    # For now, keeping it separate as per subtask focus.
    random_hex = secrets.token_hex(12)
    original_filename = secure_filename(form_media_file.filename)
    _, f_ext_with_dot = os.path.splitext(original_filename)
    f_ext = f_ext_with_dot.lower().lstrip('.') # ensure lowercase and no dot

    media_fn = random_hex + f_ext_with_dot.lower() # Keep the dot for the final filename

    media_type = None
    if f_ext in ALLOWED_IMAGE_EXTENSIONS:
        media_type = 'image'
    elif f_ext in ALLOWED_VIDEO_EXTENSIONS:
        media_type = 'video'
    else:
        # This case should ideally be caught by FileAllowed validator in the form
        raise ValueError(f"Unsupported file type for story media: .{f_ext}")

    upload_folder = current_app.config.get('STORY_MEDIA_UPLOAD_FOLDER', os.path.join('app', 'static', 'story_media_default'))
    # Construct full path relative to the application's root_path
    media_full_path = os.path.join(current_app.root_path, upload_folder, media_fn)

    # Ensure the target directory exists
    os.makedirs(os.path.dirname(media_full_path), exist_ok=True)

    if media_type == 'image':
        img = Image.open(form_media_file)

        # Define target dimensions for stories (e.g., 9:16 aspect ratio, common for stories)
        # Max width 1080, max height 1920
        output_max_width = 1080
        output_max_height = 1920

        img.thumbnail((output_max_width, output_max_height), Image.Resampling.LANCZOS)
        img.save(media_full_path)
    elif media_type == 'video':
        form_media_file.save(media_full_path)

    return media_fn, media_type


# Helper function for processing hashtags (moved from app/core/routes.py)
def process_hashtags(post_body, post_object):
    # Clear existing hashtags for the post (important for edits)
    post_object.hashtags = []

    # Regex to find hashtags: words starting with #, alphanumeric characters and underscores
    hashtag_regex = r"#([a-zA-Z0-9_]+)"
    found_tags_texts = re.findall(hashtag_regex, post_body)

    for tag_text in set(found_tags_texts): # Use set to avoid duplicate processing for same tag in one post
        normalized_tag = tag_text.lower() # Normalize to lowercase
        # Ensure Hashtag and db are available (they are, via global imports in this file)
        hashtag = Hashtag.query.filter_by(tag_text=normalized_tag).first()
        if not hashtag:
            hashtag = Hashtag(tag_text=normalized_tag)
            db.session.add(hashtag)
            # No commit here yet, will be committed with the post

        if hashtag not in post_object.hashtags: # Ensure not to add duplicates
             post_object.hashtags.append(hashtag)


def process_mentions(text_content: str, owner_object, actor_user: User) -> list[User]:
    """
    Processes text_content to find mentions, creates Mention records,
    and returns a list of users who were mentioned.
    Does NOT commit to db.session.
    """
    mentioned_users_objects = []
    if not text_content:
        return mentioned_users_objects

    # Use func.lower for case-insensitive username matching in query
    # \w matches letters, numbers, and underscore.
    potential_usernames = set(re.findall(r"@(\w+)", text_content))

    for username in potential_usernames:
        tagged_user = User.query.filter(func.lower(User.username) == username.lower()).first()

        if tagged_user:
            # Create Mention record even for self-tags.
            # Notification logic will handle not sending notifications for self-tags.

            mention = Mention(
                user_id=tagged_user.id,
                actor_id=actor_user.id
                # timestamp is default
            )

            if isinstance(owner_object, Post):
                mention.post_id = owner_object.id
            elif isinstance(owner_object, Comment):
                mention.comment_id = owner_object.id
            else:
                # Log warning or raise error if owner_object is not Post or Comment
                current_app.logger.warning(f"process_mentions called with invalid owner_object type: {type(owner_object)}")
                continue # Skip this mention if the owner object is not valid

            db.session.add(mention)
            mentioned_users_objects.append(tagged_user)

    return mentioned_users_objects

# Removed duplicate import of url_for; already imported globally on line 4
from markupsafe import Markup, escape # This import is already present globally

# Ensure User and func are available (they are, from global imports in this file)
# from app.models import User # Already imported globally
# from sqlalchemy import func # Already imported globally

def linkify_mentions(text_content):
    if not text_content:
        return Markup('') # Return Markup empty string

    segments = []
    last_end = 0
    # Regex to find @username patterns: @ followed by word characters
    for match in re.finditer(r"@(\w+)", text_content):
        # Append the text segment before the mention (escaped)
        segments.append(escape(text_content[last_end:match.start()]))

        username_match = match.group(1) # The actual username string, e.g., "john_doe"

        # Query for the user, case-insensitive
        # User and func are available from global imports
        user = User.query.filter(func.lower(User.username) == username_match.lower()).first()

        if user:
            profile_url = url_for('main.profile', username=user.username)
            # Construct the link with properly escaped components. user.username is used for display.
            segments.append(f'<a href="{escape(profile_url)}">@{escape(user.username)}</a>')
        else:
            # If user not found, append the original @mention text (e.g., "@nonexistentuser")
            # This part also needs to be escaped as it's part of the overall text_content.
            segments.append(escape(match.group(0)))

        last_end = match.end()

    # Append the remaining text segment after the last mention (escaped)
    segments.append(escape(text_content[last_end:]))

    return Markup("".join(segments))


# Recommendation Functions

def get_recommendations(user_id):
    """
    Main orchestrator for recommendations.
    Fetches recommendations for posts, users, and groups for a given user.
    """
    user = User.query.get(user_id)
    if not user:
        return {'posts': [], 'users': [], 'groups': []}

    recommended_posts = recommend_posts(user)
    recommended_users = recommend_users(user)
    recommended_groups = recommend_groups(user)

    return {
        'posts': recommended_posts,
        'users': recommended_users,
        'groups': recommended_groups
    }

def recommend_posts(user, limit=5):
    """
    Recommends posts to a user based on hashtags from their liked and commented posts.
    """
    if not user:
        return []

    # Collect hashtags from posts liked by the user
    liked_hashtags_q = db.session.query(distinct(Hashtag.id)).select_from(Reaction)\
        .join(Post, Reaction.post_id == Post.id)\
        .join(Post.hashtags)\
        .filter(Reaction.user_id == user.id, Reaction.reaction_type == 'like') # Consider only 'like' reactions for this logic

    # Collect hashtags from posts commented on by the user
    # Assuming Comment model has a 'post_id' attribute/relationship to Post model
    commented_hashtags_q = db.session.query(distinct(Hashtag.id)).select_from(Comment)\
        .join(Post, Comment.post_id == Post.id) \
        .join(Post.hashtags)\
        .filter(Comment.user_id == user.id)

    user_interest_hashtag_ids = set([h_id for (h_id,) in liked_hashtags_q.all()] + \
                                    [h_id for (h_id,) in commented_hashtags_q.all()])

    if not user_interest_hashtag_ids:
        return []

    # Posts already interacted with by the user
    liked_post_ids = {reaction.post_id for reaction in user.reactions.filter_by(reaction_type='like') if reaction.post_id is not None} # Filter for 'like' reactions
    # Assuming Comment model has 'post_id'
    commented_post_ids = {comment.post_id for comment in user.comments if hasattr(comment, 'post_id') and comment.post_id is not None}
    authored_post_ids = {post.id for post in user.posts if post.id is not None}

    excluded_post_ids = liked_post_ids.union(commented_post_ids).union(authored_post_ids)

    # Subquery to count matching hashtags for each post
    matching_hashtags_subquery = db.session.query(
        Post.id.label('post_id'),
        func.count(distinct(Hashtag.id)).label('score')
    ).join(Post.hashtags).filter(Hashtag.id.in_(user_interest_hashtag_ids)).group_by(Post.id).subquery()

    recommended_posts_query = db.session.query(Post, matching_hashtags_subquery.c.score).\
        join(matching_hashtags_subquery, Post.id == matching_hashtags_subquery.c.post_id).\
        filter(not_(Post.id.in_(excluded_post_ids))).\
        filter(Post.user_id != user.id).\
        order_by(desc(matching_hashtags_subquery.c.score), desc(Post.timestamp))

    final_recommendations = recommended_posts_query.limit(limit).all()

    return [post for post, score in final_recommendations]


def recommend_users(user, limit=5):
    """
    Recommends users based on mutual connections and shared group memberships.
    """
    if not user:
        return []

    suggested_users_scores = {}
    already_followed_ids = {followed.id for followed in user.followed}

    # 1. Mutual Connections (Second-degree connections)
    # Score by the number of users 'user' follows who also follow the suggested user.
    if user.followed: # Check if user follows anyone
        mutual_connections_query = db.session.query(
            User, func.count(followers.c.follower_id).label('mutual_score')
        ).select_from(User).join(followers, User.id == followers.c.followed_id)\
         .filter(followers.c.follower_id.in_([f.id for f in user.followed])) \
         .filter(User.id != user.id) \
         .filter(not_(User.id.in_(already_followed_ids))) \
         .group_by(User.id)

        for u, score in mutual_connections_query.all():
            suggested_users_scores[u.id] = suggested_users_scores.get(u.id, {'user': u, 'score': 0})
            suggested_users_scores[u.id]['score'] += score

    # 2. Shared Group Memberships
    # Score by the number of shared groups.
    user_group_ids = {membership.group_id for membership in user.group_memberships}
    if user_group_ids:
        shared_groups_query = db.session.query(
            User, func.count(distinct(GroupMembership.group_id)).label('shared_group_score')
        ).select_from(User).join(GroupMembership, User.id == GroupMembership.user_id)\
         .filter(GroupMembership.group_id.in_(user_group_ids))\
         .filter(User.id != user.id)\
         .filter(not_(User.id.in_(already_followed_ids))) \
         .group_by(User.id)

        for u, score in shared_groups_query.all():
            suggested_users_scores[u.id] = suggested_users_scores.get(u.id, {'user': u, 'score': 0})
            suggested_users_scores[u.id]['score'] += score

    # Filter out users with zero score if any accidentally got in
    valid_suggestions = [s for s in suggested_users_scores.values() if s['score'] > 0]

    # Sort users by score (desc) and then by username (asc)
    # Python's sort is stable: sort by username first, then by score.
    sorted_suggestions = sorted(valid_suggestions, key=lambda x: x['user'].username)
    sorted_suggestions = sorted(sorted_suggestions, key=lambda x: x['score'], reverse=True)

    return [item['user'] for item in sorted_suggestions[:limit]]


def recommend_groups(user, limit=5):
    """
    Recommends groups based on user's liked post hashtags and groups joined by followed users.
    """
    if not user:
        return []

    suggested_groups_scores = {}
    user_member_of_group_ids = {membership.group_id for membership in user.group_memberships}

    # 1. Interest-Based (Hashtags from liked posts)
    # Score by number of relevant hashtags found in group's posts
    liked_post_hashtags_ids_q = db.session.query(distinct(Hashtag.id)).select_from(Reaction)\
        .join(Post, Reaction.post_id == Post.id)\
        .join(Post.hashtags)\
        .filter(Reaction.user_id == user.id, Reaction.reaction_type == 'like') # Consider only 'like' reactions
    liked_post_hashtags_ids = {h_id for (h_id,) in liked_post_hashtags_ids_q.all()}

    if liked_post_hashtags_ids:
        interest_based_groups_query = db.session.query(
            Group, func.count(distinct(Hashtag.id)).label('interest_score')
        ).select_from(Group).join(Post, Post.group_id == Group.id)\
         .join(Post.hashtags)\
         .filter(Hashtag.id.in_(liked_post_hashtags_ids))\
         .filter(not_(Group.id.in_(user_member_of_group_ids)))\
         .group_by(Group.id)

        for group, score in interest_based_groups_query.all():
            suggested_groups_scores[group.id] = suggested_groups_scores.get(group.id, {'group': group, 'score': 0})
            suggested_groups_scores[group.id]['score'] += score

    # 2. Social-Based (Followed Users' Groups)
    # Score by number of followed users who are members of the group.
    followed_user_ids = {followed.id for followed in user.followed}
    if followed_user_ids:
        social_based_groups_query = db.session.query(
            Group, func.count(distinct(GroupMembership.user_id)).label('social_score')
        ).select_from(Group).join(GroupMembership, Group.id == GroupMembership.group_id)\
         .filter(GroupMembership.user_id.in_(followed_user_ids))\
         .filter(not_(Group.id.in_(user_member_of_group_ids)))\
         .group_by(Group.id)

        for group, score in social_based_groups_query.all():
            suggested_groups_scores[group.id] = suggested_groups_scores.get(group.id, {'group': group, 'score': 0})
            suggested_groups_scores[group.id]['score'] += score

    # Filter out groups with zero score
    valid_suggestions = [s for s in suggested_groups_scores.values() if s['score'] > 0]

    # Sort groups by score (desc) and then by group name (asc)
    sorted_suggestions = sorted(valid_suggestions, key=lambda x: x['group'].name)
    sorted_suggestions = sorted(sorted_suggestions, key=lambda x: x['score'], reverse=True)

    return [item['group'] for item in sorted_suggestions[:limit]]


# Analytics Utility Functions

def award_points(user, action_name, points, related_item=None):
    """
    Awards points to a user, creates an activity log, and checks for/awards new badges.

    This function handles the core logic of point attribution:
    1. Fetches or creates a `UserPoints` record for the specified user.
    2. Increments the user's points.
    3. Creates an `ActivityLog` entry detailing the action, points earned,
       and optionally linking to a related item (e.g., a Post, Comment).
    4. Calls `check_and_award_badges(user)` to evaluate if this action (or the new
       point total) results in the user earning any new badges.

    Important: This function adds new/updated objects (UserPoints, ActivityLog,
    potentially new Badge associations via check_and_award_badges) to the
    database session (`db.session.add()`). However, it does NOT commit the session.
    The calling route or service is responsible for the final `db.session.commit()`
    to ensure atomicity of operations.

    Args:
        user (User): The user object to award points to.
        action_name (str): A string key identifying the action (e.g., 'create_post', 'daily_login').
        points (int): The number of points to award.
        related_item (db.Model, optional): A database model instance related to the
                                           action (e.g., the Post created, the Comment made).
                                           Defaults to None.
    """
    if not user or not user.is_authenticated: # Ensure user is valid and authenticated
        return

    # Get or create UserPoints
    user_points = UserPoints.query.filter_by(user_id=user.id).first()
    if not user_points:
        user_points = UserPoints(user_id=user.id, points=0)
        db.session.add(user_points)

    user_points.points += points

    # Create ActivityLog entry
    activity_log = ActivityLog(
        user_id=user.id,
        activity_type=action_name, # Renamed from 'action' to 'activity_type' to match model
        points_earned=points
    )
    if related_item:
        activity_log.related_id = related_item.id
        # Ensure __tablename__ or a similar attribute is used for type, or __class__.__name__
        activity_log.related_item_type = related_item.__class__.__name__.lower()

    db.session.add(activity_log)
    # db.session.add(user_points) # user_points is already in session if fetched, or added if new

    # After points are updated and activity logged, check for new badges
    check_and_award_badges(user)

def get_historical_engagement(user_id, time_period_str='7days', custom_start_date=None, custom_end_date=None):
    """
    Fetches historical engagement data for a user over a specified time period.
    `time_period_str` can be "7days", "30days", "90days", "all", "custom".
    For "custom", `custom_start_date` and optionally `custom_end_date` should be provided.
    """
    now = datetime.now(timezone.utc)

    # Determine end_date
    if custom_end_date:
        end_date = custom_end_date
    else:
        end_date = now

    # Determine start_date
    if time_period_str == 'all':
        start_date = None # No start date filter means from the beginning
    elif time_period_str == 'custom':
        if custom_start_date:
            start_date = custom_start_date
        else:
            # Default to 'all' if 'custom' is specified but no custom_start_date
            start_date = None
            current_app.logger.warning("get_historical_engagement: 'custom' period without custom_start_date, defaulting to 'all'.")
    else:
        days_map = {
            '7days': 7,
            '30days': 30,
            '90days': 90
        }
        days = days_map.get(time_period_str)
        if days is None: # Default to 7 days if string is invalid and not 'all' or 'custom'
            current_app.logger.warning(f"get_historical_engagement: Invalid time_period_str '{time_period_str}', defaulting to 7 days.")
            days = 7
        start_date = end_date - timedelta(days=days)

    query = HistoricalAnalytics.query.filter_by(user_id=user_id)

    if start_date:
        query = query.filter(HistoricalAnalytics.timestamp >= start_date)

    # Apply end_date filter unless 'all' is chosen AND no custom_end_date is set
    # (meaning 'all' truly means up to now, or up to custom_end_date if specified)
    if not (time_period_str == 'all' and not custom_end_date):
         query = query.filter(HistoricalAnalytics.timestamp <= end_date)

    return query.order_by(HistoricalAnalytics.timestamp.asc()).all()

def get_top_performing_hashtags(user_id, limit=5):
    """
    Identifies top performing hashtags for a user based on likes and comments on their posts.
    Returns a list of dicts: [{'tag_text': ..., 'engagement': ..., 'likes': ..., 'comments': ...}]
    """
    # Subquery for likes per post-hashtag combination for the user's posts
    likes_subquery = db.session.query(
        post_hashtags.c.hashtag_id.label('hashtag_id'),
        func.count(distinct(Reaction.id)).label('likes_count') # Changed Like.id to Reaction.id
    ).select_from(post_hashtags)\
    .join(Post, Post.id == post_hashtags.c.post_id)\
    .outerjoin(Reaction, and_(Reaction.post_id == Post.id, Reaction.reaction_type == 'like'))\
    .filter(Post.user_id == user_id)\
    .group_by(post_hashtags.c.hashtag_id).subquery()

    # Subquery for comments per post-hashtag combination for the user's posts
    comments_subquery = db.session.query(
        post_hashtags.c.hashtag_id.label('hashtag_id'),
        func.count(distinct(Comment.id)).label('comments_count')
    ).select_from(post_hashtags)\
    .join(Post, Post.id == post_hashtags.c.post_id)\
    .outerjoin(Comment, Comment.post_id == Post.id)\
    .filter(Post.user_id == user_id)\
    .group_by(post_hashtags.c.hashtag_id).subquery()

    # Main query to combine results from Hashtag table with subqueries
    results = db.session.query(
        Hashtag.tag_text,
        Hashtag.id, # Keep for potential direct linking or further queries
        func.coalesce(likes_subquery.c.likes_count, 0).label('total_likes'),
        func.coalesce(comments_subquery.c.comments_count, 0).label('total_comments'),
        (func.coalesce(likes_subquery.c.likes_count, 0) + func.coalesce(comments_subquery.c.comments_count, 0)).label('total_engagement')
    ).select_from(Hashtag)\
    .outerjoin(likes_subquery, Hashtag.id == likes_subquery.c.hashtag_id)\
    .outerjoin(comments_subquery, Hashtag.id == comments_subquery.c.hashtag_id)\
    .filter(or_(likes_subquery.c.hashtag_id.isnot(None), comments_subquery.c.hashtag_id.isnot(None)))\
    .order_by(desc('total_engagement'), Hashtag.tag_text)\
    .limit(limit).all()

    return [{'tag_text': r.tag_text, 'hashtag_id': r.id, 'engagement': r.total_engagement, 'likes': r.total_likes, 'comments': r.total_comments} for r in results]


def get_top_performing_groups(user_id, limit=5):
    """
    Identifies top performing groups for a user based on likes and comments on their posts within those groups.
    Returns a list of dicts: [{'group_name': ..., 'group_id': ..., 'engagement': ..., 'likes': ..., 'comments': ...}]
    """
    # Subquery for likes on user's posts, aggregated by group_id
    likes_per_group_sq = db.session.query(
        Post.group_id,
        func.count(distinct(Reaction.id)).label('likes_count') # Changed Like.id to Reaction.id
    ).join(Reaction, and_(Reaction.post_id == Post.id, Reaction.reaction_type == 'like'))\
    .filter(Post.user_id == user_id)\
    .filter(Post.group_id.isnot(None))\
    .group_by(Post.group_id)\
    .subquery()

    # Subquery for comments on user's posts, aggregated by group_id
    comments_per_group_sq = db.session.query(
        Post.group_id,
        func.count(distinct(Comment.id)).label('comments_count')
    ).join(Comment, Comment.post_id == Post.id)\
    .filter(Post.user_id == user_id)\
    .filter(Post.group_id.isnot(None))\
    .group_by(Post.group_id)\
    .subquery()

    # Main query joining Group with aggregated likes and comments
    results = db.session.query(
        Group.id.label('group_id'),
        Group.name.label('group_name'),
        func.coalesce(likes_per_group_sq.c.likes_count, 0).label('total_likes'),
        func.coalesce(comments_per_group_sq.c.comments_count, 0).label('total_comments'),
        (func.coalesce(likes_per_group_sq.c.likes_count, 0) + func.coalesce(comments_per_group_sq.c.comments_count, 0)).label('total_engagement')
    ).select_from(Group)\
    .outerjoin(likes_per_group_sq, Group.id == likes_per_group_sq.c.group_id)\
    .outerjoin(comments_per_group_sq, Group.id == comments_per_group_sq.c.group_id)\
    .filter(or_(likes_per_group_sq.c.group_id.isnot(None), comments_per_group_sq.c.group_id.isnot(None)))\
    .order_by(desc('total_engagement'), Group.name)\
    .limit(limit).all()

    return [{'group_id': r.group_id, 'group_name': r.group_name, 'engagement': r.total_engagement, 'likes': r.total_likes, 'comments': r.total_comments} for r in results]


def save_audio_file(form_audio_file_data, upload_folder_name='audio_uploads'):
    """
    Saves an uploaded audio file to a specified folder.
    Returns the generated filename.
    Assumes 'upload_folder_name' is relative to the 'static' directory base.
    """
    random_hex = secrets.token_hex(12)
    original_filename = secure_filename(form_audio_file_data.filename)
    _, f_ext_with_dot = os.path.splitext(original_filename)

    audio_fn = random_hex + f_ext_with_dot.lower()

    # Get base static upload directory from config
    base_static_dir = current_app.config.get('MEDIA_UPLOAD_BASE_DIR', 'static')
    # Construct full save path directory
    audio_save_dir = os.path.join(current_app.root_path, base_static_dir, upload_folder_name)

    os.makedirs(audio_save_dir, exist_ok=True)

    full_file_path = os.path.join(audio_save_dir, audio_fn)

    form_audio_file_data.save(full_file_path)

    return audio_fn

def get_audio_duration(file_path):
    """
    Extracts the duration of an audio file in seconds using mutagen.
    Returns an integer (duration in seconds) or None if duration cannot be determined.
    'file_path' should be the absolute path to the audio file.
    """
    if not MUTAGEN_AVAILABLE:
        current_app.logger.info("Mutagen library not available, cannot get audio duration.")
        return None

    try:
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        audio = None

        if ext == '.mp3':
            try:
                audio = MP3(file_path)
            except ID3NoHeaderError: # Handle MP3s that might lack a proper header for metadata
                current_app.logger.warning(f"Mutagen ID3NoHeaderError for MP3: {file_path}. Duration might be unavailable.")
                return None
        elif ext == '.wav':
            audio = WAVE(file_path)
        elif ext == '.ogg': # Handles Ogg Vorbis, Ogg Speex, Ogg Opus, Ogg Flac
            audio = OggVorbis(file_path) # OggVorbis can often handle various ogg types
        elif ext == '.aac':
            audio = AAC(file_path)
        elif ext == '.m4a' or ext == '.mp4': # M4A is typically MP4 container
            audio = MP4(file_path)
        elif ext == '.flac':
            audio = FLAC(file_path)
        else:
            current_app.logger.warning(f"Unsupported audio file type for duration check with mutagen: {ext} for file {file_path}")
            return None

        if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
            return int(audio.info.length)
        else:
            current_app.logger.warning(f"Could not extract duration info from {file_path} (type: {ext}). Audio info: {audio.info if audio else 'N/A'}")
            return None

    except Exception as e:
        current_app.logger.error(f"Error getting duration for {file_path} with mutagen: {e}")
        return None

def generate_ics_file(event_obj: AppEvent) -> bytes:
    """
    Generates an iCalendar (.ics) file content for a given Event object.
    """
    cal = Calendar()
    cal.add('prodid', '-//My App//Event Calendar//EN')
    cal.add('version', '2.0')

    ics_event = IcsEvent()
    ics_event.add('uid', event_obj.calendar_uid)
    ics_event.add('summary', event_obj.name)

    if event_obj.description:
        ics_event.add('description', event_obj.description)

    # Ensure dtstart and dtend are timezone-aware (UTC)
    # If naive, assume UTC. If aware, ensure it's UTC (icalendar might handle this, but explicit is better)
    dtstart = event_obj.start_datetime
    if dtstart.tzinfo is None:
        dtstart = dtstart.replace(tzinfo=timezone.utc)
    else:
        dtstart = dtstart.astimezone(timezone.utc) # Convert to UTC if already aware but different timezone

    dtend = event_obj.end_datetime
    if dtend.tzinfo is None:
        dtend = dtend.replace(tzinfo=timezone.utc)
    else:
        dtend = dtend.astimezone(timezone.utc) # Convert to UTC

    ics_event.add('dtstart', dtstart)
    ics_event.add('dtend', dtend)
    ics_event.add('dtstamp', datetime.now(timezone.utc)) # Timestamp for when the iCalendar object was created

    if event_obj.location:
        ics_event.add('location', event_obj.location)

    cal.add_component(ics_event)
    return cal.to_ical()


def is_user_subscribed_to_creator(user, creator_id):
    """
    Checks if a given user has an active subscription to any plan
    offered by the specified creator.

    :param user: The User object (subscriber).
    :param creator_id: The ID of the content creator.
    :return: True if an active subscription exists, False otherwise.
    """
    if not user or not user.is_authenticated: # user.is_authenticated might not be available on a raw User object if not from flask_login.current_user
        return False # Consider if 'user' is always a Flask-Login current_user proxy or a direct User model.
                     # If direct User model, user.is_authenticated check might not be appropriate or available.
                     # Assuming 'user' can be current_user or a User model instance that might not have is_authenticated.
                     # A simple check 'if not user:' might be enough if it's always a User instance.
                     # For now, keeping it as is, assuming 'user' could be flask_login's current_user.

    # Ensure user object has an id attribute and it's not None
    if not hasattr(user, 'id') or user.id is None:
        return False

    active_subscription = UserSubscription.query \
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id) \
        .filter(
            UserSubscription.subscriber_id == user.id,
            SubscriptionPlan.creator_id == creator_id,
            UserSubscription.status == 'active' # Assuming 'active' is the status string for active subscriptions
        ).first()

    return active_subscription is not None


def subscription_required(creator_id_param_name='user_id', creator_model=None, creator_model_param_name=None):
    """
    Decorator to ensure the current user is actively subscribed to the content creator.
    Can fetch creator_id directly from a route variable (using creator_id_param_name)
    OR by fetching a model (e.g., Post, Article) using creator_model_param_name,
    and then accessing its user_id attribute.

    :param creator_id_param_name: The name of the route variable holding the creator's user ID.
    :param creator_model: The SQLAlchemy model (e.g., Post) to fetch if creator_id is on a related object.
    :param creator_model_param_name: The name of the route variable holding the ID for creator_model (e.g., 'post_id').
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            target_creator_id = None

            if creator_model and creator_model_param_name:
                model_id = kwargs.get(creator_model_param_name)
                if model_id:
                    item = creator_model.query.get_or_404(model_id) # This will abort if not found
                    if hasattr(item, 'user_id'):
                        target_creator_id = item.user_id
                    elif hasattr(item, 'author_id'):
                         target_creator_id = item.author_id
                    elif hasattr(item, 'creator_id'): # For SubscriptionPlan itself, or similar
                         target_creator_id = item.creator_id
                    elif isinstance(item, User): # If the item itself is a User profile
                        target_creator_id = item.id
                    else:
                        current_app.logger.error(f"Subscription check failed: Could not determine creator attribute for {creator_model.__name__} ID {model_id}")
                        flash('Content creator could not be determined for subscription check.', 'danger')
                        return redirect(url_for('main.index'))
                else:
                    # This case means creator_model_param_name was not found in kwargs,
                    # which might be an issue with route variable naming or decorator setup.
                    current_app.logger.warning(f"Subscription check: model_id not found in kwargs using creator_model_param_name '{creator_model_param_name}'.")
                    # Fall through to try creator_id_param_name directly.
                    pass

            if not target_creator_id and creator_id_param_name:
                raw_id = kwargs.get(creator_id_param_name)
                if raw_id is not None:
                    try:
                        target_creator_id = int(raw_id)
                    except ValueError:
                        current_app.logger.error(f"Subscription check: Could not convert '{raw_id}' to int for creator_id.")
                        flash('Invalid creator identifier.', 'danger')
                        return redirect(url_for('main.index'))
                # else: creator_id_param_name not in kwargs. This will be caught by the None check below.

            if target_creator_id is None:
                current_app.logger.error("Subscription check: target_creator_id could not be determined from route parameters.")
                flash('Creator ID not found for subscription check.', 'danger')
                return redirect(url_for('main.index'))

            # Allow access if the current user is the creator
            if current_user.is_authenticated and current_user.id == target_creator_id:
                return f(*args, **kwargs)

            if not is_user_subscribed_to_creator(current_user, target_creator_id):
                flash('You must be actively subscribed to this creator to view this content.', 'warning')
                # Try to redirect to creator's profile if possible.
                # Need to ensure the creator_id can be used to find a username or a profile route.
                # For simplicity, if we have target_creator_id, we can try to find the user to get username for profile URL.
                creator_user = User.query.get(target_creator_id)
                if creator_user:
                    return redirect(url_for('main.profile', username=creator_user.username))
                else:
                    # Fallback if creator user not found (e.g. creator_id was from a deleted user's content)
                    return redirect(url_for('main.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
