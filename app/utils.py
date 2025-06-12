import os
import secrets
from flask import current_app
from PIL import Image # For image resizing - will need to install Pillow

def save_picture(form_picture_field):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture_field.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static/images', picture_fn)

    # Output size for resizing
    output_size = (150, 150) # Thumbnail size
    i = Image.open(form_picture_field)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn

def save_post_image(form_image_field):
    random_hex = secrets.token_hex(12) # Potentially more images, so longer hex for less collision chance
    _, f_ext = os.path.splitext(form_image_field.filename)
    image_fn = random_hex + f_ext

    # Use the configuration variable for the upload path
    # POST_IMAGES_UPLOAD_FOLDER is 'app/static/post_images'
    # current_app.root_path is the project root directory
    upload_path_from_config = current_app.config.get('POST_IMAGES_UPLOAD_FOLDER', 'app/static/post_images_default') # Default fallback
    picture_path = os.path.join(current_app.root_path, upload_path_from_config, image_fn)

    # Ensure the target directory exists
    # The directory path to create is os.path.dirname(picture_path)
    # which would be project_root/app/static/post_images
    os.makedirs(os.path.dirname(picture_path), exist_ok=True)

    # Define output size or processing for post images.
    # For posts, we might want larger images than profile thumbnails.
    # Let's say max width of 800px, height auto-scaled to maintain aspect ratio.
    output_max_width = 800
    img = Image.open(form_image_field)

    if img.width > output_max_width:
        aspect_ratio = img.height / img.width
        new_height = int(output_max_width * aspect_ratio)
        img = img.resize((output_max_width, new_height), Image.Resampling.LANCZOS) # Use LANCZOS for quality

    img.save(picture_path)
    return image_fn

def save_post_video(form_video_file):
    random_hex = secrets.token_hex(12)
    _, f_ext = os.path.splitext(form_video_file.filename)
    video_fn = random_hex + f_ext

    # Use the configuration variable for the upload path
    upload_path_from_config = current_app.config.get('VIDEO_UPLOAD_FOLDER', 'app/static/videos_default') # Default fallback
    video_full_path = os.path.join(current_app.root_path, upload_path_from_config, video_fn)

    # Ensure the target directory exists
    os.makedirs(os.path.dirname(video_full_path), exist_ok=True)

    form_video_file.save(video_full_path)
    return video_fn

def save_group_image(form_image_field):
    random_hex = secrets.token_hex(10) # Using 10 hex characters
    _, f_ext = os.path.splitext(form_image_field.filename)
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
from app.models import Notification
from app.forms import SearchForm # Import SearchForm

def inject_unread_notification_count():
    if current_user.is_authenticated:
        count = Notification.query.filter_by(recipient_id=current_user.id, is_read=False).count()
    else:
        count = 0
    return {'unread_notification_count': count}

def inject_search_form():
    form = SearchForm()
    return {'search_form': form}

# Define allowed extensions more comprehensively at the top or import from a config
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'} # Added mkv as it's common

def save_story_media(form_media_file):
    random_hex = secrets.token_hex(12)
    original_filename = form_media_file.filename
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

        # Resize while maintaining aspect ratio if it exceeds either dimension
        # PIL's thumbnail method is good for this, it resizes in place
        # It ensures the image fits within the (width, height) box.
        img.thumbnail((output_max_width, output_max_height), Image.Resampling.LANCZOS)

        # Could add logic here to convert to a specific format like WebP or optimize JPEG/PNG
        # For now, save in original format (or PIL's default for the mode if conversion happened)
        img.save(media_full_path)
    elif media_type == 'video':
        form_media_file.save(media_full_path)

    return media_fn, media_type
