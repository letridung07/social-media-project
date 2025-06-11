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
