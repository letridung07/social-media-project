import unittest
import os
from app import create_app, db
from app.utils.helpers import save_picture, save_media_file # Changed save_post_image to save_media_file
from PIL import Image
from io import BytesIO
from flask import current_app

class ImageUtilsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_class='config.TestingConfig')
        self.app_context = self.app.app_context()
        self.app_context.push()
        # No db needed for these utils usually, but good practice if utils might evolve
        # db.create_all()

        # Ensure upload directories exist
        self.profile_pic_dir = os.path.join(current_app.root_path, 'static/images')
        self.post_image_dir = os.path.join(current_app.root_path, current_app.config.get('POST_IMAGES_UPLOAD_FOLDER'))
        os.makedirs(self.profile_pic_dir, exist_ok=True)
        os.makedirs(self.post_image_dir, exist_ok=True)

        self.saved_files = [] # To keep track of files to delete

    def tearDown(self):
        for f_path in self.saved_files:
            if os.path.exists(f_path):
                os.remove(f_path)
        # db.session.remove()
        # db.drop_all()
        self.app_context.pop()

    def _create_dummy_image(self, width, height, filename="test.png", img_format="PNG"):
        """Helper to create an in-memory image for testing uploads."""
        file_stream = BytesIO()
        image = Image.new('RGB', (width, height), color = 'red')
        image.save(file_stream, img_format)
        file_stream.seek(0)
        # To simulate a FileStorage object from Flask/WTForms
        class DummyFileStorage:
            def __init__(self, stream, filename):
                self.stream = stream
                self.filename = filename
            def save(self, dst):
                with open(dst, 'wb') as f:
                    f.write(self.stream.read())
            def __getattr__(self, name):
                # Delegate other attribute access to the stream
                return getattr(self.stream, name)

        return DummyFileStorage(file_stream, filename)

    def test_save_picture_profile(self):
        dummy_image_file = self._create_dummy_image(500, 500, "profile_test.jpg", "JPEG")

        filename = save_picture(dummy_image_file)
        self.assertIsNotNone(filename)
        saved_path = os.path.join(self.profile_pic_dir, filename)
        self.saved_files.append(saved_path)
        self.assertTrue(os.path.exists(saved_path))

        # Check dimensions
        saved_img = Image.open(saved_path)
        self.assertEqual(saved_img.size, (256, 256)) # Resized to 256x256
        saved_img.close()

        # Check file size (very rough check for compression)
        # This is tricky as "small" is relative and depends on many factors.
        # For a 256x256 red JPEG at quality 85, it should be fairly small.
        # Let's say under 50KB as a very loose upper bound.
        file_size_kb = os.path.getsize(saved_path) / 1024
        self.assertLess(file_size_kb, 50, "Profile picture file size seems too large.")


    def test_save_post_image_resizing(self):
        # Test image larger than max width (1200px defined in save_media_file for images)
        dummy_large_image = self._create_dummy_image(1500, 1000, "large_post_test.png", "PNG")

        # save_media_file expects the upload_folder_name which is relative to app.root_path
        # e.g. 'static/post_images' or directly the config key name if save_media_file uses it.
        # current_app.config.get('POST_IMAGES_UPLOAD_FOLDER') should provide 'static/post_images'
        upload_folder_name = current_app.config.get('POST_IMAGES_UPLOAD_FOLDER', 'static/post_images_default_test')


        filename, media_type = save_media_file(dummy_large_image, upload_folder_name)
        self.assertIsNotNone(filename)
        self.assertEqual(media_type, 'image')
        # self.post_image_dir is already the full path: os.path.join(current_app.root_path, upload_folder_name)
        saved_path = os.path.join(upload_folder_name, filename) # Path relative to root for checking
        saved_path_abs = os.path.join(current_app.root_path, saved_path)
        self.saved_files.append(saved_path)
        self.saved_files.append(saved_path_abs) # Store absolute path for cleanup
        self.assertTrue(os.path.exists(saved_path_abs))

        saved_img = Image.open(saved_path_abs)
        # Original aspect ratio 1500/1000 = 3/2.
        # If width is resized to 1200 (max_width in save_media_file), height should be 1200 * (2/3) = 800.
        self.assertEqual(saved_img.width, 1200)
        self.assertEqual(saved_img.height, 800)
        saved_img.close()

        file_size_kb = os.path.getsize(saved_path_abs) / 1024
        # For an 1200x800 PNG converted to RGB (likely saved as JPEG by PIL's default if not specified or as PNG if original format kept)
        # This is a rough check. Quality 85.
        self.assertLess(file_size_kb, 250, "Resized post image file size seems too large.")


    def test_save_post_image_no_resizing(self):
        # Test image smaller than max width
        dummy_small_image = self._create_dummy_image(600, 400, "small_post_test.jpeg", "JPEG")
        upload_folder_name = current_app.config.get('POST_IMAGES_UPLOAD_FOLDER', 'static/post_images_default_test')

        filename, media_type = save_media_file(dummy_small_image, upload_folder_name)
        self.assertIsNotNone(filename)
        self.assertEqual(media_type, 'image')

        saved_path_abs = os.path.join(current_app.root_path, upload_folder_name, filename)
        self.saved_files.append(saved_path_abs)
        self.assertTrue(os.path.exists(saved_path_abs))

        saved_img = Image.open(saved_path_abs)
        # Dimensions should remain the same as original
        self.assertEqual(saved_img.width, 600)
        self.assertEqual(saved_img.height, 400)
        saved_img.close()

if __name__ == '__main__':
    unittest.main()
