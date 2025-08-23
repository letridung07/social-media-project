import os
import secrets
from functools import wraps
from flask import current_app, redirect, url_for, flash, abort
from PIL import Image
from werkzeug.utils import secure_filename
import re
import magic
import clamd

try:
    from mutagen.mp3 import MP3
    from mutagen.wave import WAVE
    from mutagen.oggvorbis import OggVorbis
    from mutagen.aac import AAC
    from mutagen.mp4 import MP4
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3NoHeaderError
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from sqlalchemy import func, desc, not_, and_, or_, distinct
from app import db
from app.core.models import User, Post, Reaction, Comment, Hashtag, Group, GroupMembership, followers, Mention, HistoricalAnalytics, post_hashtags, Article, Event as AppEvent, UserSubscription, SubscriptionPlan, UserPoints, ActivityLog
from datetime import datetime, timedelta, timezone
from app.utils.gamification_utils import check_and_award_badges, update_user_level
from icalendar import Calendar, Event as IcsEvent

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'aac'}

def _check_file_size(file_storage, max_bytes):
    file_storage.seek(0, os.SEEK_END)
    file_size = file_storage.tell()
    file_storage.seek(0)
    if file_size > max_bytes or file_size == 0:
        raise ValueError(f"Invalid file size: {file_size} bytes. Must be between 1 and {max_bytes} bytes.")

def _check_file_type(file_storage, allowed_mimes):
    file_header = file_storage.read(2048)
    file_storage.seek(0)
    mime_type = magic.from_buffer(file_header, mime=True)
    if mime_type not in allowed_mimes:
        raise ValueError(f"Invalid file type: {mime_type}. Allowed types: {', '.join(allowed_mimes)}")
    return mime_type

def _scan_for_virus(file_storage):
    try:
        cd = clamd.ClamdNetworkSocket(
            host=current_app.config['CLAMAV_HOST'],
            port=current_app.config['CLAMAV_PORT'],
            timeout=current_app.config['CLAMAV_TIMEOUT']
        )
        scan_result = cd.instream(file_storage)
        file_storage.seek(0)
        if scan_result and scan_result['stream'][0] == 'FOUND':
            virus_name = scan_result['stream'][1]
            raise ValueError(f"Virus detected: {virus_name}.")
    except clamd.ConnectionError:
        current_app.logger.error("ClamAV connection failed. File scanning is bypassed.")
    except ValueError as e:
        raise e
    except Exception as e:
        current_app.logger.error(f"ClamAV unexpected error: {e}")
        raise IOError("Virus scan failed unexpectedly.")

def save_picture(form_picture_field):
    try:
        _check_file_size(form_picture_field, current_app.config['MAX_IMAGE_SIZE'])
        _check_file_type(form_picture_field, ['image/jpeg', 'image/png', 'image/gif'])
        _scan_for_virus(form_picture_field)

        random_hex = secrets.token_hex(8)
        original_filename = secure_filename(form_picture_field.filename)
        _, f_ext = os.path.splitext(original_filename)
        picture_fn = random_hex + f_ext
        picture_path = os.path.join(current_app.root_path, 'static/images', picture_fn)

        output_size = (256, 256)
        i = Image.open(form_picture_field)
        i.thumbnail(output_size)
        if i.mode in ("P", "RGBA"):
            i = i.convert("RGB")
        i.save(picture_path, optimize=True, quality=85)

        return picture_fn
    except (ValueError, IOError) as e:
        raise e

def save_media_file(form_media_file, upload_folder_name='media_items'):
    original_filename = secure_filename(form_media_file.filename)
    _, f_ext_with_dot = os.path.splitext(original_filename)
    f_ext = f_ext_with_dot.lower().lstrip('.')

    media_type = None
    if f_ext in ALLOWED_IMAGE_EXTENSIONS:
        media_type = 'image'
        max_size = current_app.config['MAX_IMAGE_SIZE']
        allowed_mimes = ['image/jpeg', 'image/png', 'image/gif']
    elif f_ext in ALLOWED_VIDEO_EXTENSIONS:
        media_type = 'video'
        max_size = current_app.config['MAX_VIDEO_SIZE']
        allowed_mimes = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska']
    else:
        raise ValueError(f"Unsupported file type based on extension: '.{f_ext}'.")

    _check_file_size(form_media_file, max_size)
    actual_mime_type = _check_file_type(form_media_file, allowed_mimes)
    _scan_for_virus(form_media_file)

    if actual_mime_type.startswith('image/'):
        media_type = 'image'
    elif actual_mime_type.startswith('video/'):
        media_type = 'video'

    random_hex = secrets.token_hex(12)
    saved_filename = random_hex + f_ext_with_dot.lower()
    full_save_path_dir = os.path.join(current_app.root_path, 'static', upload_folder_name)
    os.makedirs(full_save_path_dir, exist_ok=True)
    full_file_path = os.path.join(full_save_path_dir, saved_filename)

    if media_type == 'image':
        img = Image.open(form_media_file)
        output_max_width = 1200
        if img.width > output_max_width:
            aspect_ratio = img.height / img.width
            new_height = int(output_max_width * aspect_ratio)
            img = img.resize((output_max_width, new_height), Image.Resampling.LANCZOS)

        if img.mode in ("P", "RGBA"):
            img = img.convert("RGB")
        img.save(full_file_path, optimize=True, quality=85)
    elif media_type == 'video':
        form_media_file.save(full_file_path)

    return saved_filename, media_type

def save_group_image(form_image_field):
    try:
        _check_file_size(form_image_field, current_app.config['MAX_IMAGE_SIZE'])
        _check_file_type(form_image_field, ['image/jpeg', 'image/png', 'image/gif'])
        _scan_for_virus(form_image_field)

        random_hex = secrets.token_hex(10)
        original_filename = secure_filename(form_image_field.filename)
        _, f_ext = os.path.splitext(original_filename)
        image_fn = random_hex + f_ext

        upload_path_from_config = current_app.config.get('UPLOAD_FOLDER_GROUP_IMAGES', 'app/static/group_images_default')
        picture_path = os.path.join(current_app.root_path, upload_path_from_config, image_fn)
        os.makedirs(os.path.dirname(picture_path), exist_ok=True)

        output_size = (400, 400)
        img = Image.open(form_image_field)
        img.thumbnail(output_size, Image.Resampling.LANCZOS)
        img.save(picture_path)
        return image_fn
    except (ValueError, IOError) as e:
        raise e

def save_story_media(form_media_file):
    original_filename = secure_filename(form_media_file.filename)
    _, f_ext_with_dot = os.path.splitext(original_filename)
    f_ext = f_ext_with_dot.lower().lstrip('.')

    media_type = None
    if f_ext in ALLOWED_IMAGE_EXTENSIONS:
        media_type = 'image'
        max_size = current_app.config['MAX_IMAGE_SIZE']
        allowed_mimes = ['image/jpeg', 'image/png', 'image/gif']
    elif f_ext in ALLOWED_VIDEO_EXTENSIONS:
        media_type = 'video'
        max_size = current_app.config['MAX_VIDEO_SIZE']
        allowed_mimes = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska']
    else:
        raise ValueError(f"Unsupported file type for story media: .{f_ext}")

    _check_file_size(form_media_file, max_size)
    actual_mime_type = _check_file_type(form_media_file, allowed_mimes)
    _scan_for_virus(form_media_file)

    if actual_mime_type.startswith('image/'):
        media_type = 'image'
    elif actual_mime_type.startswith('video/'):
        media_type = 'video'

    random_hex = secrets.token_hex(12)
    media_fn = random_hex + f_ext_with_dot.lower()
    upload_folder = current_app.config.get('STORY_MEDIA_UPLOAD_FOLDER', os.path.join('app', 'static', 'story_media_default'))
    media_full_path = os.path.join(current_app.root_path, upload_folder, media_fn)
    os.makedirs(os.path.dirname(media_full_path), exist_ok=True)

    if media_type == 'image':
        img = Image.open(form_media_file)
        output_max_width = 1080
        output_max_height = 1920
        img.thumbnail((output_max_width, output_max_height), Image.Resampling.LANCZOS)
        img.save(media_full_path)
    elif media_type == 'video':
        form_media_file.save(media_full_path)

    return media_fn, media_type

def save_audio_file(form_audio_file_data, upload_folder_name='audio_uploads'):
    try:
        max_size = current_app.config['MAX_AUDIO_SIZE']
        allowed_mimes = ['audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/aac']
        _check_file_size(form_audio_file_data, max_size)
        _check_file_type(form_audio_file_data, allowed_mimes)
        _scan_for_virus(form_audio_file_data)

        random_hex = secrets.token_hex(12)
        original_filename = secure_filename(form_audio_file_data.filename)
        _, f_ext_with_dot = os.path.splitext(original_filename)

        audio_fn = random_hex + f_ext_with_dot.lower()

        base_static_dir = current_app.config.get('MEDIA_UPLOAD_BASE_DIR', 'static')
        audio_save_dir = os.path.join(current_app.root_path, base_static_dir, upload_folder_name)
        os.makedirs(audio_save_dir, exist_ok=True)
        full_file_path = os.path.join(audio_save_dir, audio_fn)

        form_audio_file_data.save(full_file_path)

        return audio_fn
    except (ValueError, IOError) as e:
        raise e

# ... (the rest of the file remains the same)
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

from flask_login import current_user
from app.core.models import Notification
from app.core.forms import SearchForm

def inject_unread_notification_count():
    if current_user.is_authenticated:
        count = Notification.query.filter_by(recipient_id=current_user.id, is_read=False).count()
    else:
        count = 0
    return {'unread_notification_count': count}

def inject_search_form():
    form = SearchForm()
    return {'search_form': form}

def process_hashtags(post_body, post_object):
    post_object.hashtags = []
    hashtag_regex = r"#([a-zA-Z0-9_]+)"
    found_tags_texts = re.findall(hashtag_regex, post_body)

    for tag_text in set(found_tags_texts):
        normalized_tag = tag_text.lower()
        hashtag = Hashtag.query.filter_by(tag_text=normalized_tag).first()
        if not hashtag:
            hashtag = Hashtag(tag_text=normalized_tag)
            db.session.add(hashtag)
            db.session.flush()

        if hashtag not in post_object.hashtags:
             post_object.hashtags.append(hashtag)

        usage = HashtagUsage(hashtag_id=hashtag.id)
        db.session.add(usage)

def process_mentions(text_content: str, owner_object, actor_user: User) -> list[User]:
    mentioned_users_objects = []
    if not text_content:
        return mentioned_users_objects

    potential_usernames = set(re.findall(r"@(\w+)", text_content))

    for username in potential_usernames:
        tagged_user = User.query.filter(func.lower(User.username) == username.lower()).first()

        if tagged_user:
            mention = Mention(
                user_id=tagged_user.id,
                actor_id=actor_user.id
            )

            if isinstance(owner_object, Post):
                mention.post_id = owner_object.id
            elif isinstance(owner_object, Comment):
                mention.comment_id = owner_object.id
            else:
                current_app.logger.warning(f"process_mentions called with invalid owner_object type: {type(owner_object)}")
                continue

            db.session.add(mention)
            mentioned_users_objects.append(tagged_user)

    return mentioned_users_objects

from markupsafe import Markup, escape

def linkify_mentions(text_content):
    if not text_content:
        return Markup('')

    segments = []
    last_end = 0
    for match in re.finditer(r"@(\w+)", text_content):
        segments.append(escape(text_content[last_end:match.start()]))

        username_match = match.group(1)
        user = User.query.filter(func.lower(User.username) == username_match.lower()).first()

        if user:
            profile_url = url_for('main.profile', username=user.username)
            segments.append(f'<a href="{escape(profile_url)}">@{escape(user.username)}</a>')
        else:
            segments.append(escape(match.group(0)))

        last_end = match.end()

    segments.append(escape(text_content[last_end:]))

    return Markup("".join(segments))

def get_recommendations(user_id):
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
    if not user:
        return []

    liked_hashtags_q = db.session.query(distinct(Hashtag.id)).select_from(Reaction)\
        .join(Post, Reaction.post_id == Post.id)\
        .join(Post.hashtags)\
        .filter(Reaction.user_id == user.id, Reaction.reaction_type == 'like')

    commented_hashtags_q = db.session.query(distinct(Hashtag.id)).select_from(Comment)\
        .join(Post, Comment.post_id == Post.id) \
        .join(Post.hashtags)\
        .filter(Comment.user_id == user.id)

    user_interest_hashtag_ids = set([h_id for (h_id,) in liked_hashtags_q.all()] + \
                                    [h_id for (h_id,) in commented_hashtags_q.all()])

    if not user_interest_hashtag_ids:
        return []

    liked_post_ids = {reaction.post_id for reaction in user.reactions.filter_by(reaction_type='like') if reaction.post_id is not None}
    commented_post_ids = {comment.post_id for comment in user.comments if hasattr(comment, 'post_id') and comment.post_id is not None}
    authored_post_ids = {post.id for post in user.posts if post.id is not None}

    excluded_post_ids = liked_post_ids.union(commented_post_ids).union(authored_post_ids)

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
    if not user:
        return []

    suggested_users_scores = {}
    already_followed_ids = {followed.id for followed in user.followed}

    if user.followed:
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

    valid_suggestions = [s for s in suggested_users_scores.values() if s['score'] > 0]

    sorted_suggestions = sorted(valid_suggestions, key=lambda x: x['user'].username)
    sorted_suggestions = sorted(sorted_suggestions, key=lambda x: x['score'], reverse=True)

    return [item['user'] for item in sorted_suggestions[:limit]]

def recommend_groups(user, limit=5):
    if not user:
        return []

    suggested_groups_scores = {}
    user_member_of_group_ids = {membership.group_id for membership in user.group_memberships}

    liked_post_hashtags_ids_q = db.session.query(distinct(Hashtag.id)).select_from(Reaction)\
        .join(Post, Reaction.post_id == Post.id)\
        .join(Post.hashtags)\
        .filter(Reaction.user_id == user.id, Reaction.reaction_type == 'like')
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

    valid_suggestions = [s for s in suggested_groups_scores.values() if s['score'] > 0]

    sorted_suggestions = sorted(valid_suggestions, key=lambda x: x['group'].name)
    sorted_suggestions = sorted(sorted_suggestions, key=lambda x: x['score'], reverse=True)

    return [item['group'] for item in sorted_suggestions[:limit]]

def award_points(user, action_name, points, related_item=None):
    if not user or not user.is_authenticated:
        return

    user_points = UserPoints.query.filter_by(user_id=user.id).first()
    if not user_points:
        user_points = UserPoints(user_id=user.id, points=0)
        db.session.add(user_points)

    user_points.points += points

    activity_log = ActivityLog(
        user_id=user.id,
        activity_type=action_name,
        points_earned=points
    )
    if related_item:
        activity_log.related_id = related_item.id
        activity_log.related_item_type = related_item.__class__.__name__.lower()

    db.session.add(activity_log)
    leveled_up = update_user_level(user_points)
    check_and_award_badges(user)

def get_historical_engagement(user_id, time_period_str='7days', custom_start_date=None, custom_end_date=None):
    now = datetime.now(timezone.utc)
    if custom_end_date:
        end_date = custom_end_date
    else:
        end_date = now

    if time_period_str == 'all':
        start_date = None
    elif time_period_str == 'custom':
        if custom_start_date:
            start_date = custom_start_date
        else:
            start_date = None
            current_app.logger.warning("get_historical_engagement: 'custom' period without custom_start_date, defaulting to 'all'.")
    else:
        days_map = {
            '7days': 7,
            '30days': 30,
            '90days': 90
        }
        days = days_map.get(time_period_str, 7)
        start_date = end_date - timedelta(days=days)

    query = HistoricalAnalytics.query.filter_by(user_id=user_id)

    if start_date:
        query = query.filter(HistoricalAnalytics.timestamp >= start_date)

    if not (time_period_str == 'all' and not custom_end_date):
         query = query.filter(HistoricalAnalytics.timestamp <= end_date)

    return query.order_by(HistoricalAnalytics.timestamp.asc()).all()

def get_top_performing_hashtags(user_id, limit=5):
    likes_subquery = db.session.query(
        post_hashtags.c.hashtag_id.label('hashtag_id'),
        func.count(distinct(Reaction.id)).label('likes_count')
    ).select_from(post_hashtags)\
    .join(Post, Post.id == post_hashtags.c.post_id)\
    .outerjoin(Reaction, and_(Reaction.post_id == Post.id, Reaction.reaction_type == 'like'))\
    .filter(Post.user_id == user_id)\
    .group_by(post_hashtags.c.hashtag_id).subquery()

    comments_subquery = db.session.query(
        post_hashtags.c.hashtag_id.label('hashtag_id'),
        func.count(distinct(Comment.id)).label('comments_count')
    ).select_from(post_hashtags)\
    .join(Post, Post.id == post_hashtags.c.post_id)\
    .outerjoin(Comment, Comment.post_id == Post.id)\
    .filter(Post.user_id == user_id)\
    .group_by(post_hashtags.c.hashtag_id).subquery()

    results = db.session.query(
        Hashtag.tag_text,
        Hashtag.id,
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
    likes_per_group_sq = db.session.query(
        Post.group_id,
        func.count(distinct(Reaction.id)).label('likes_count')
    ).join(Reaction, and_(Reaction.post_id == Post.id, Reaction.reaction_type == 'like'))\
    .filter(Post.user_id == user_id)\
    .filter(Post.group_id.isnot(None))\
    .group_by(Post.group_id)\
    .subquery()

    comments_per_group_sq = db.session.query(
        Post.group_id,
        func.count(distinct(Comment.id)).label('comments_count')
    ).join(Comment, Comment.post_id == Post.id)\
    .filter(Post.user_id == user_id)\
    .filter(Post.group_id.isnot(None))\
    .group_by(Post.group_id)\
    .subquery()

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

def get_audio_duration(file_path):
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
            except ID3NoHeaderError:
                current_app.logger.warning(f"Mutagen ID3NoHeaderError for MP3: {file_path}. Duration might be unavailable.")
                return None
        elif ext == '.wav':
            audio = WAVE(file_path)
        elif ext == '.ogg':
            audio = OggVorbis(file_path)
        elif ext == '.aac':
            audio = AAC(file_path)
        elif ext == '.m4a' or ext == '.mp4':
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
    cal = Calendar()
    cal.add('prodid', '-//My App//Event Calendar//EN')
    cal.add('version', '2.0')

    ics_event = IcsEvent()
    ics_event.add('uid', event_obj.calendar_uid)
    ics_event.add('summary', event_obj.name)

    if event_obj.description:
        ics_event.add('description', event_obj.description)

    dtstart = event_obj.start_datetime
    if dtstart.tzinfo is None:
        dtstart = dtstart.replace(tzinfo=timezone.utc)
    else:
        dtstart = dtstart.astimezone(timezone.utc)

    dtend = event_obj.end_datetime
    if dtend.tzinfo is None:
        dtend = dtend.replace(tzinfo=timezone.utc)
    else:
        dtend = dtend.astimezone(timezone.utc)

    ics_event.add('dtstart', dtstart)
    ics_event.add('dtend', dtend)
    ics_event.add('dtstamp', datetime.now(timezone.utc))

    if event_obj.location:
        ics_event.add('location', event_obj.location)

    cal.add_component(ics_event)
    return cal.to_ical()

def is_user_subscribed_to_creator(user, creator_id):
    if not user or not user.is_authenticated:
        return False

    if not hasattr(user, 'id') or user.id is None:
        return False

    active_subscription = UserSubscription.query \
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id) \
        .filter(
            UserSubscription.subscriber_id == user.id,
            SubscriptionPlan.creator_id == creator_id,
            UserSubscription.status == 'active'
        ).first()

    return active_subscription is not None

def subscription_required(creator_id_param_name='user_id', creator_model=None, creator_model_param_name=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            target_creator_id = None

            if creator_model and creator_model_param_name:
                model_id = kwargs.get(creator_model_param_name)
                if model_id:
                    item = creator_model.query.get_or_404(model_id)
                    if hasattr(item, 'user_id'):
                        target_creator_id = item.user_id
                    elif hasattr(item, 'author_id'):
                         target_creator_id = item.author_id
                    elif hasattr(item, 'creator_id'):
                         target_creator_id = item.creator_id
                    elif isinstance(item, User):
                        target_creator_id = item.id
                    else:
                        current_app.logger.error(f"Subscription check failed: Could not determine creator attribute for {creator_model.__name__} ID {model_id}")
                        flash('Content creator could not be determined for subscription check.', 'danger')
                        return redirect(url_for('main.index'))
                else:
                    current_app.logger.warning(f"Subscription check: model_id not found in kwargs using creator_model_param_name '{creator_model_param_name}'.")
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

            if target_creator_id is None:
                current_app.logger.error("Subscription check: target_creator_id could not be determined from route parameters.")
                flash('Creator ID not found for subscription check.', 'danger')
                return redirect(url_for('main.index'))

            if current_user.is_authenticated and current_user.id == target_creator_id:
                return f(*args, **kwargs)

            if not is_user_subscribed_to_creator(current_user, target_creator_id):
                flash('You must be actively subscribed to this creator to view this content.', 'warning')
                creator_user = User.query.get(target_creator_id)
                if creator_user:
                    return redirect(url_for('main.profile', username=creator_user.username))
                else:
                    return redirect(url_for('main.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
