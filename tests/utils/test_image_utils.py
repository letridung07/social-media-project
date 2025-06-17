import unittest
import os
from app import create_app, db
from app.utils.helpers import save_picture, save_post_image # save_post_image might not exist here
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
        # Test image larger than max width (800px defined in save_post_image)
        dummy_large_image = self._create_dummy_image(1200, 900, "large_post_test.png", "PNG")

        filename = save_post_image(dummy_large_image)
        self.assertIsNotNone(filename)
        saved_path = os.path.join(self.post_image_dir, filename)
        self.saved_files.append(saved_path)
        self.assertTrue(os.path.exists(saved_path))

        saved_img = Image.open(saved_path)
        # Original aspect ratio 1200/900 = 4/3.
        # If width is resized to 800, height should be 800 * (3/4) = 600.
        self.assertEqual(saved_img.width, 800)
        self.assertEqual(saved_img.height, 600)
        saved_img.close()

        file_size_kb = os.path.getsize(saved_path) / 1024
        # For an 800x600 PNG converted to JPEG (default if not specified) at quality 85...
        # Let's say under 150KB. PNGs might be larger.
        # The save_post_image converts to RGB, implying JPEG if original was PNG.
        self.assertLess(file_size_kb, 150, "Resized post image file size seems too large.")


    def test_save_post_image_no_resizing(self):
        # Test image smaller than max width
        dummy_small_image = self._create_dummy_image(600, 400, "small_post_test.jpeg", "JPEG")

        filename = save_post_image(dummy_small_image)
        self.assertIsNotNone(filename)
        saved_path = os.path.join(self.post_image_dir, filename)
        self.saved_files.append(saved_path)
        self.assertTrue(os.path.exists(saved_path))

        saved_img = Image.open(saved_path)
        # Dimensions should remain the same as original
        self.assertEqual(saved_img.width, 600)
        self.assertEqual(saved_img.height, 400)
        saved_img.close()

if __name__ == '__main__':
    unittest.main()
