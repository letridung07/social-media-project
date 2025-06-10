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
