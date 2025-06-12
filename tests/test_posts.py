# tests/test_posts.py
import unittest
import os
import io # For creating mock files
from flask import current_app
from app import create_app, db
from app.models import User, Post, Mention, Comment, Notification # Added Mention, Comment, Notification
from app.utils import process_mentions, linkify_mentions # Added process_mentions and linkify_mentions
from config import TestingConfig # Using TestingConfig for tests
from werkzeug.datastructures import FileStorage # For creating mock FileStorage object
from datetime import datetime, timedelta
import base64 # For decoding the dummy image

class PostModelCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create a test user
        self.user1 = User(username='john', email='john@example.com')
        self.user1.set_password('cat')
        db.session.add(self.user1)
        db.session.commit()

        # Path for post images - ensure it's cleaned up
        self.post_images_path = os.path.join(current_app.root_path, current_app.config['POST_IMAGES_UPLOAD_FOLDER'])
        # Path for post videos
        self.post_videos_path = os.path.join(current_app.root_path, current_app.config.get('VIDEO_UPLOAD_FOLDER', 'app/static/videos_test')) # Using a default for safety
        os.makedirs(self.post_videos_path, exist_ok=True) # Ensure it exists for tests


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

        # Clean up post_images directory
        if os.path.exists(self.post_images_path):
            for f in os.listdir(self.post_images_path):
                try:
                    os.remove(os.path.join(self.post_images_path, f))
                except OSError:
                    pass # Ignore if file is already removed or other issues
            if not os.listdir(self.post_images_path):
                 os.rmdir(self.post_images_path)

        # Clean up post_videos directory
        if os.path.exists(self.post_videos_path):
            for f in os.listdir(self.post_videos_path):
                try:
                    os.remove(os.path.join(self.post_videos_path, f))
                except OSError:
                    pass # Ignore
            if not os.listdir(self.post_videos_path):
                os.rmdir(self.post_videos_path)


    def _login(self, email, password):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_create_text_only_post(self): # Explicitly for text-only
        self._login('john@example.com', 'cat')
        response = self.client.post('/create_post', data={'body': 'This is a text-only post!'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        post = Post.query.filter_by(body='This is a text-only post!').first()
        self.assertIsNotNone(post)
        self.assertIsNone(post.image_filename) # Ensure no image

        # Check if the post appears on the index page (where redirect goes)
        self.assertIn(b'This is a text-only post!', response.data)
        self.assertNotIn(b'/static/post_images/', response.data) # Check that no post-specific image is shown

        # Check profile page as well
        response_profile = self.client.get(f'/user/{self.user1.username}')
        self.assertIn(b'This is a text-only post!', response_profile.data)
        self.assertNotIn(b'/static/post_images/', response_profile.data) # Check that no post-specific image is shown
        self._logout()

    def test_create_post_with_image(self):
        self._login('john@example.com', 'cat')

        # Create a mock image file (1x1 transparent PNG)
        # Base64 encoded: R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        mock_image_data = io.BytesIO(base64.b64decode(png_b64))
        mock_file = FileStorage(stream=mock_image_data, filename="test_image.png", content_type="image/png")

        post_body_text = "This is a post with an image!"
        alt_text_for_image = "This is the alt text for the test image."
        response = self.client.post('/create_post', data={
            'body': post_body_text,
            'image_file': mock_file,
            'alt_text': alt_text_for_image
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your post is now live!', response.data)

        post = Post.query.filter_by(body=post_body_text).first()
        self.assertIsNotNone(post)
        self.assertIsNotNone(post.image_filename) # Check filename is stored
        self.assertEqual(post.alt_text, alt_text_for_image)

        # Verify image file exists
        expected_image_path = os.path.join(self.post_images_path, post.image_filename)
        self.assertTrue(os.path.exists(expected_image_path))

        # Verify image is displayed on index page (where redirect goes)
        expected_img_tag_html = f'<img src="/static/post_images/{post.image_filename}" alt="{alt_text_for_image}"'
        self.assertIn(expected_img_tag_html.encode(), response.data)
        self.assertIn(post_body_text.encode(), response.data)
        self._logout()

        # Test case for image without alt text
        self._login('john@example.com', 'cat')
        mock_image_data_no_alt = io.BytesIO(base64.b64decode(png_b64)) # Recreate stream
        mock_file_no_alt = FileStorage(stream=mock_image_data_no_alt, filename="test_image_no_alt.png", content_type="image/png")
        post_body_no_alt = "Image post without alt text"
        response_no_alt = self.client.post('/create_post', data={
            'body': post_body_no_alt,
            'image_file': mock_file_no_alt
            # No alt_text provided
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response_no_alt.status_code, 200)
        post_no_alt = Post.query.filter_by(body=post_body_no_alt).first()
        self.assertIsNotNone(post_no_alt)
        self.assertIsNone(post_no_alt.alt_text) # Should be None or empty

        # Verify fallback alt text in rendered HTML
        fallback_alt_text = f'Image for post by {self.user1.username}'
        expected_img_tag_no_alt_html = f'<img src="/static/post_images/{post_no_alt.image_filename}" alt="{fallback_alt_text}"'
        self.assertIn(expected_img_tag_no_alt_html.encode(), response_no_alt.data)
        self._logout()


    def test_create_post_with_video(self):
        self._login('john@example.com', 'cat')

        # Create a mock video file
        video_data = io.BytesIO(b"dummy video content for a fake mp4")
        mock_video_file = FileStorage(stream=video_data, filename="test_video.mp4", content_type="video/mp4")

        post_body_text = "This is a post with a video!"
        alt_text_for_video = "This is the alt text for the test video."
        response = self.client.post('/create_post', data={
            'body': post_body_text,
            'video_file': mock_video_file,
            'alt_text': alt_text_for_video
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your post is now live!', response.data)

        post = Post.query.filter_by(body=post_body_text).first()
        self.assertIsNotNone(post)
        self.assertIsNotNone(post.video_filename)
        self.assertTrue(post.video_filename.endswith('.mp4'))
        self.assertEqual(post.alt_text, alt_text_for_video)
        self.assertIsNone(post.image_filename) # Ensure no image was inadvertently picked up

        # Verify video file exists in the correct test upload folder
        expected_video_path = os.path.join(self.post_videos_path, post.video_filename)
        self.assertTrue(os.path.exists(expected_video_path))

        # Verify video is displayed with alt text on index page
        expected_video_tag_html = f'<video width="100%" controls aria-describedby="video-alt-text-{post.id}"'
        self.assertIn(expected_video_tag_html.encode(), response.data)
        expected_alt_text_p_html = f'<p id="video-alt-text-{post.id}" class="visually-hidden">{alt_text_for_video}</p>'
        self.assertIn(expected_alt_text_p_html.encode(), response.data)
        self.assertIn(post_body_text.encode(), response.data)
        self._logout()

        # Test case for video without alt text
        self._login('john@example.com', 'cat')
        video_data_no_alt = io.BytesIO(b"dummy video content no alt")
        mock_video_file_no_alt = FileStorage(stream=video_data_no_alt, filename="test_video_no_alt.mp4", content_type="video/mp4")
        post_body_no_alt_video = "Video post without alt text"
        response_no_alt_video = self.client.post('/create_post', data={
            'body': post_body_no_alt_video,
            'video_file': mock_video_file_no_alt
            # No alt_text
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response_no_alt_video.status_code, 200)
        post_no_alt_video_db = Post.query.filter_by(body=post_body_no_alt_video).first()
        self.assertIsNotNone(post_no_alt_video_db)
        self.assertIsNone(post_no_alt_video_db.alt_text)

        # Verify video tag does not have aria-describedby and no hidden p for alt text
        self.assertNotIn(b'aria-describedby="video-alt-text-', response_no_alt_video.data)
        self.assertNotIn(f'class="visually-hidden">{alt_text_for_video}'.encode(), response_no_alt_video.data)
        # Ensure the video tag itself is there
        self.assertIn(f'<video width="100%" controls'.encode(), response_no_alt_video.data)
        self.assertIn(post_no_alt_video_db.video_filename.encode(), response_no_alt_video.data)
        self._logout()


    def test_create_post_with_invalid_file_type(self):
        self._login('john@example.com', 'cat')

        # Ensure post_images_path exists for listdir, or create it if it might not
        if not os.path.exists(self.post_images_path):
            os.makedirs(self.post_images_path)

        mock_invalid_file_data = io.BytesIO(b"this is not an image")
        mock_file = FileStorage(stream=mock_invalid_file_data, filename="test.txt", content_type="text/plain")

        response = self.client.post('/create_post', data={
            'body': 'Trying to upload a text file.',
            'image_file': mock_file
        }, content_type='multipart/form-data', follow_redirects=True) # Test with follow_redirects=False first if issues with form error display

        self.assertEqual(response.status_code, 200)
        # Assuming FileAllowed validator stops processing before route attempts to save file,
        # and re-renders the 'create_post.html' page with the form error.
        # The create_post.html template needs to display form.image_file.errors for this to be visible.
        # For now, we'll check for the flash message that the route *would* produce if an error happened during save_post_image
        # OR we check that the post wasn't created.
        # The FileAllowed validator error should be displayed by the form rendering logic.
        # If create_post.html doesn't render form.image_file.errors, this specific assertIn might fail.
        # However, the core logic is that the post should not be created with an invalid file.
        self.assertIn(b'Images only!', response.data) # This expects the error to be in the response data

        post = Post.query.filter_by(body='Trying to upload a text file.').first()
        self.assertIsNone(post) # Post should not be created

        # Check that no files were saved to post_images
        self.assertEqual(len(os.listdir(self.post_images_path)), 0, "A file was saved despite invalid type")

        self._logout()

    def test_view_posts_on_profile_and_index(self):
        # Create posts for user1
        p1 = Post(body='Post 1 by John', author=self.user1, timestamp=datetime.utcnow() + timedelta(seconds=1))
        p2 = Post(body='Post 2 by John', author=self.user1, timestamp=datetime.utcnow() + timedelta(seconds=2))
        db.session.add_all([p1, p2])

        # Create another user and their post
        user2 = User(username='susan', email='susan@example.com')
        user2.set_password('dog')
        db.session.add(user2)
        db.session.commit() # Commit user2 first
        p3 = Post(body='Post by Susan', author=user2, timestamp=datetime.utcnow() + timedelta(seconds=3))
        db.session.add(p3)
        db.session.commit()

        # Test John's profile page
        response_john_profile = self.client.get(f'/user/{self.user1.username}')
        self.assertIn(b'Post 1 by John', response_john_profile.data)
        self.assertIn(b'Post 2 by John', response_john_profile.data)
        self.assertNotIn(b'Post by Susan', response_john_profile.data)

        # Test Susan's profile page
        response_susan_profile = self.client.get(f'/user/{user2.username}')
        self.assertIn(b'Post by Susan', response_susan_profile.data)
        self.assertNotIn(b'Post 1 by John', response_susan_profile.data)

        # Test index page (should show all posts)
        # Login to see create post link, though posts are visible without login
        self._login('john@example.com', 'cat')
        response_index = self.client.get('/')
        self.assertIn(b'Post 1 by John', response_index.data)
        self.assertIn(b'Post 2 by John', response_index.data)
        self.assertNotIn(b'Post by Susan', response_index.data) # John is not following Susan
        self.assertIn(b'john', response_index.data) # Author username
        # self.assertIn(b'susan', response_index.data) # Susan's username should not be on John's feed if not followed
        self._logout()

    def test_create_post_requires_login(self):
        response = self.client.get('/create_post', follow_redirects=True)
        # Should redirect to login page
        self.assertTrue(response.request.path.startswith('/login')) # Check redirection path

        response_post = self.client.post('/create_post', data={
            'body': 'Trying to post without login'
        }, follow_redirects=True)
        self.assertTrue(response_post.request.path.startswith('/login'))

        post = Post.query.filter_by(body='Trying to post without login').first()
        self.assertIsNone(post)

    def test_view_post_with_video_on_index_and_profile(self):
        # Log in user
        self._login('john@example.com', 'cat')

        # Create a post with a video
        video_data = io.BytesIO(b"dummy video content for test_view")
        video_file = FileStorage(stream=video_data, filename="view_test_video.mp4", content_type="video/mp4")
        post_body = "Video post for viewing test"

        self.client.post('/create_post', data={
            'body': post_body,
            'video_file': video_file
        }, content_type='multipart/form-data', follow_redirects=True)

        # Retrieve the post from DB to get video_filename
        post = Post.query.filter_by(body=post_body).first()
        self.assertIsNotNone(post)
        self.assertIsNotNone(post.video_filename)

        # Test index page
        response_index = self.client.get('/')
        self.assertEqual(response_index.status_code, 200)
        self.assertIn(post.video_filename.encode(), response_index.data)
        self.assertIn(b'<video', response_index.data) # Check for <video tag
        self.assertIn(b'controls', response_index.data) # Check for controls attribute
        self.assertIn(f'src="/static/videos/{post.video_filename}"'.encode(), response_index.data)

        # Test user's profile page
        response_profile = self.client.get(f'/user/{self.user1.username}')
        self.assertEqual(response_profile.status_code, 200)
        self.assertIn(post.video_filename.encode(), response_profile.data)
        self.assertIn(b'<video', response_profile.data)
        self.assertIn(f'src="/static/videos/{post.video_filename}"'.encode(), response_profile.data)

        self._logout()
        # Video file cleanup is handled by tearDown

    def test_edit_post_alt_text(self):
        self._login('john@example.com', 'cat')

        # Setup: Create an initial post with an image but without alt_text
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        mock_image_data = io.BytesIO(base64.b64decode(png_b64))
        mock_file = FileStorage(stream=mock_image_data, filename="edit_test_image.png", content_type="image/png")
        initial_post_body = "Post for alt text editing test"

        create_response = self.client.post('/create_post', data={
            'body': initial_post_body,
            'image_file': mock_file
            # No alt_text initially
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(create_response.status_code, 200)

        initial_post = Post.query.filter_by(body=initial_post_body).first()
        self.assertIsNotNone(initial_post)
        self.assertIsNone(initial_post.alt_text)
        self.assertIsNotNone(initial_post.image_filename) # Ensure image was saved

        initial_alt_text = "Initial alt text for edit test."
        updated_alt_text = "Updated alt text after editing."

        # First Edit (Add alt_text)
        edit_response_1 = self.client.post(f'/edit_post/{initial_post.id}', data={
            'body': initial_post_body, # Keep the body same or change if needed for test scope
            'alt_text': initial_alt_text
            # No image_file means we are not changing the image itself
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(edit_response_1.status_code, 200)
        self.assertIn(b'Your post has been updated!', edit_response_1.data)

        db.session.refresh(initial_post) # Refresh from DB
        self.assertEqual(initial_post.alt_text, initial_alt_text)

        # Second Edit (Change alt_text)
        edit_response_2 = self.client.post(f'/edit_post/{initial_post.id}', data={
            'body': initial_post_body,
            'alt_text': updated_alt_text
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(edit_response_2.status_code, 200)
        self.assertIn(b'Your post has been updated!', edit_response_2.data)

        db.session.refresh(initial_post)
        self.assertEqual(initial_post.alt_text, updated_alt_text)

        # Verify Rendered HTML on user's profile page
        profile_response = self.client.get(f'/user/{self.user1.username}')
        self.assertEqual(profile_response.status_code, 200)

        # Ensure the specific post's image is rendered with the updated alt text
        # The image filename is initial_post.image_filename
        expected_img_tag_html = f'<img src="/static/post_images/{initial_post.image_filename}" alt="{updated_alt_text}"'
        self.assertIn(expected_img_tag_html.encode(), profile_response.data)

        self._logout()

    # --- Tests for process_mentions utility ---
    def test_process_mentions_valid(self):
        with self.app.app_context(): # Ensure app context for DB operations
            user_a = User(username='user_a', email='usera@example.com')
            user_b = User(username='user_b', email='userb@example.com')
            actor_user = self.user1 # Re-use existing user1 as actor
            db.session.add_all([user_a, user_b])
            db.session.commit()

            mock_post = Post(body="Test post for mentions", author=actor_user)
            db.session.add(mock_post)
            db.session.commit() # Commit post to get an ID

            mentioned_users = process_mentions("Hello @user_a and @user_b check this out", mock_post, actor_user)
            db.session.commit() # process_mentions adds to session, commit to save Mentions

            self.assertEqual(len(mentioned_users), 2)
            self.assertIn(user_a, mentioned_users)
            self.assertIn(user_b, mentioned_users)

            mentions = Mention.query.filter_by(post_id=mock_post.id).all()
            self.assertEqual(len(mentions), 2)
            mention_user_ids = {m.user_id for m in mentions}
            self.assertIn(user_a.id, mention_user_ids)
            self.assertIn(user_b.id, mention_user_ids)
            for m in mentions:
                self.assertEqual(m.actor_id, actor_user.id)

    def test_process_mentions_invalid(self):
        with self.app.app_context():
            actor_user = self.user1
            mock_post = Post(body="Test post for invalid mentions", author=actor_user)
            db.session.add(mock_post)
            db.session.commit()

            mentioned_users = process_mentions("Hello @nonexistent_user, how are you?", mock_post, actor_user)
            db.session.commit()

            self.assertEqual(len(mentioned_users), 0)
            mentions = Mention.query.filter_by(post_id=mock_post.id).all()
            self.assertEqual(len(mentions), 0)

    def test_process_mentions_self_mention(self):
        with self.app.app_context():
            actor_user = self.user1 # username is 'john'
            mock_post = Post(body="Test post for self-mention", author=actor_user)
            db.session.add(mock_post)
            db.session.commit()

            mentioned_users = process_mentions(f"Hello @{actor_user.username}, this is me.", mock_post, actor_user)
            db.session.commit()

            self.assertEqual(len(mentioned_users), 1)
            self.assertIn(actor_user, mentioned_users)

            mentions = Mention.query.filter_by(post_id=mock_post.id).all()
            self.assertEqual(len(mentions), 1)
            self.assertEqual(mentions[0].user_id, actor_user.id)
            self.assertEqual(mentions[0].actor_id, actor_user.id)

    def test_process_mentions_mixed_valid_invalid(self):
        with self.app.app_context():
            user_a = User(username='mention_user_a', email='mentionusera@example.com')
            actor_user = self.user1
            db.session.add(user_a)
            db.session.commit()

            mock_post = Post(body="Test post for mixed mentions", author=actor_user)
            db.session.add(mock_post)
            db.session.commit()

            mentioned_users = process_mentions("Hi @mention_user_a and @nonexistent_friend", mock_post, actor_user)
            db.session.commit()

            self.assertEqual(len(mentioned_users), 1)
            self.assertIn(user_a, mentioned_users)

            mentions = Mention.query.filter_by(post_id=mock_post.id).all()
            self.assertEqual(len(mentions), 1)
            self.assertEqual(mentions[0].user_id, user_a.id)
            self.assertEqual(mentions[0].actor_id, actor_user.id)

    def test_process_mentions_no_mentions(self):
        with self.app.app_context():
            actor_user = self.user1
            mock_post = Post(body="A post with no mentions.", author=actor_user)
            db.session.add(mock_post)
            db.session.commit()

            mentioned_users = process_mentions("Just a regular text here.", mock_post, actor_user)
            db.session.commit()

            self.assertEqual(len(mentioned_users), 0)
            mentions = Mention.query.filter_by(post_id=mock_post.id).all()
            self.assertEqual(len(mentions), 0)

    def test_process_mentions_case_insensitivity(self):
        with self.app.app_context():
            user_caps = User(username='UserCaps', email='usercaps@example.com')
            actor_user = self.user1
            db.session.add(user_caps)
            db.session.commit()

            mock_post = Post(body="Test for case insensitive mention", author=actor_user)
            db.session.add(mock_post)
            db.session.commit()

            mentioned_users = process_mentions("Hello @usercaps check this out", mock_post, actor_user)
            db.session.commit()

            self.assertEqual(len(mentioned_users), 1)
            self.assertIn(user_caps, mentioned_users)

            mentions = Mention.query.filter_by(post_id=mock_post.id).all()
            self.assertEqual(len(mentions), 1)
            self.assertEqual(mentions[0].user_id, user_caps.id)

    def test_process_mentions_in_comment(self):
        with self.app.app_context():
            user_c = User(username='user_c', email='userc@example.com')
            comment_author = self.user1
            post_author = User(username='post_author_for_comment_test', email='pafct@example.com')
            db.session.add_all([user_c, post_author])
            db.session.commit()

            parent_post = Post(body="Parent post for comment mention test", author=post_author)
            db.session.add(parent_post)
            db.session.commit()

            mock_comment = Comment(body="Hey @user_c, nice post!", author=comment_author, post_id=parent_post.id)
            db.session.add(mock_comment)
            db.session.commit()

            mentioned_users = process_mentions(mock_comment.body, mock_comment, comment_author)
            db.session.commit()

            self.assertEqual(len(mentioned_users), 1)
            self.assertIn(user_c, mentioned_users)

            mentions = Mention.query.filter_by(comment_id=mock_comment.id).all()
            self.assertEqual(len(mentions), 1)
            self.assertEqual(mentions[0].user_id, user_c.id)
            self.assertEqual(mentions[0].actor_id, comment_author.id)
            self.assertIsNone(mentions[0].post_id) # Should be linked to comment, not post directly

    # --- Tests for Mention creation and Notifications in Routes ---
    def test_create_post_route_with_mention_and_notification(self):
        self._login('john@example.com', 'cat') # self.user1 is 'john'

        tagged_user = User(username='tagged_in_post', email='taggedpost@example.com')
        db.session.add(tagged_user)
        db.session.commit()

        post_body = "Hello @tagged_in_post, check this new post!"
        response = self.client.post('/create_post', data={'body': post_body}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Verify Post
        post = Post.query.filter_by(user_id=self.user1.id).order_by(Post.timestamp.desc()).first()
        self.assertIsNotNone(post)
        self.assertEqual(post.body, post_body)

        # Verify Mention
        mention = Mention.query.filter_by(post_id=post.id, user_id=tagged_user.id, actor_id=self.user1.id).first()
        self.assertIsNotNone(mention)

        # Verify Notification
        notification = Notification.query.filter_by(
            recipient_id=tagged_user.id,
            actor_id=self.user1.id,
            type='mention',
            related_post_id=post.id,
            related_mention_id=mention.id
        ).first()
        self.assertIsNotNone(notification)
        self._logout()

    def test_edit_post_route_with_mention_and_notification(self):
        # user1 (john) creates a post
        self._login('john@example.com', 'cat')
        initial_post_body = "Initial content, no mentions."
        create_response = self.client.post('/create_post', data={'body': initial_post_body}, follow_redirects=True)
        self.assertEqual(create_response.status_code, 200)
        post = Post.query.filter_by(user_id=self.user1.id).order_by(Post.timestamp.desc()).first()
        self.assertIsNotNone(post)

        # Create another user to be tagged
        tagged_user_edit = User(username='tagged_in_edit', email='taggededit@example.com')
        db.session.add(tagged_user_edit)
        db.session.commit()

        # Edit the post to include a mention
        edited_post_body = f"Edited content now mentions @{tagged_user_edit.username}."
        edit_response = self.client.post(f'/edit_post/{post.id}', data={'body': edited_post_body}, follow_redirects=True)
        self.assertEqual(edit_response.status_code, 200)
        self.assertIn(b'Your post has been updated!', edit_response.data)

        db.session.refresh(post) # Refresh post from DB
        self.assertEqual(post.body, edited_post_body)

        # Verify Mention
        mention = Mention.query.filter_by(post_id=post.id, user_id=tagged_user_edit.id, actor_id=self.user1.id).first()
        self.assertIsNotNone(mention)

        # Verify Notification
        notification = Notification.query.filter_by(
            recipient_id=tagged_user_edit.id,
            actor_id=self.user1.id,
            type='mention',
            related_post_id=post.id,
            related_mention_id=mention.id
        ).first()
        self.assertIsNotNone(notification)
        self._logout()

    def test_add_comment_route_with_mention_and_notification(self):
        # user1 (john) creates a post
        self._login('john@example.com', 'cat')
        post_response = self.client.post('/create_post', data={'body': "A post to be commented on."}, follow_redirects=True)
        self.assertEqual(post_response.status_code, 200)
        parent_post = Post.query.filter_by(user_id=self.user1.id).order_by(Post.timestamp.desc()).first()
        self.assertIsNotNone(parent_post)
        self._logout() # Log out user1

        # user2 (commenter) logs in
        commenter_user = User(username='commenter', email='commenter@example.com')
        commenter_user.set_password('secure')
        db.session.add(commenter_user)
        db.session.commit()
        self._login('commenter@example.com', 'secure')

        # Create a user to be tagged in the comment
        tagged_user_comment = User(username='tagged_in_comment', email='taggedcomment@example.com')
        db.session.add(tagged_user_comment)
        db.session.commit()

        comment_body = f"This is a comment, and I mention @{tagged_user_comment.username}."
        comment_response = self.client.post(f'/post/{parent_post.id}/comment', data={'body': comment_body}, follow_redirects=True)
        self.assertEqual(comment_response.status_code, 200)
        self.assertIn(b'Your comment has been added!', comment_response.data)

        # Verify Comment
        comment = Comment.query.filter_by(post_id=parent_post.id, user_id=commenter_user.id).order_by(Comment.timestamp.desc()).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.body, comment_body)

        # Verify Mention in Comment
        mention = Mention.query.filter_by(comment_id=comment.id, user_id=tagged_user_comment.id, actor_id=commenter_user.id).first()
        self.assertIsNotNone(mention)

        # Verify Notification
        notification = Notification.query.filter_by(
            recipient_id=tagged_user_comment.id,
            actor_id=commenter_user.id,
            type='mention',
            related_post_id=parent_post.id, # Notification should link to the parent post
            related_mention_id=mention.id
        ).first()
        self.assertIsNotNone(notification)
        self._logout()


    def test_create_post_route_self_mention_no_notification(self):
        self._login('john@example.com', 'cat') # self.user1 is 'john'

        post_body = f"I am talking about myself, @{self.user1.username}."
        response = self.client.post('/create_post', data={'body': post_body}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        post = Post.query.filter_by(user_id=self.user1.id).order_by(Post.timestamp.desc()).first()
        self.assertIsNotNone(post)

        # Verify Mention is created
        mention = Mention.query.filter_by(post_id=post.id, user_id=self.user1.id, actor_id=self.user1.id).first()
        self.assertIsNotNone(mention)

        # Verify NO Notification is created for self-mention
        notification = Notification.query.filter_by(
            recipient_id=self.user1.id,
            actor_id=self.user1.id,
            type='mention',
            related_mention_id=mention.id
        ).first()
        self.assertIsNone(notification)
        self._logout()

    # --- Test for linkify_mentions template filter ---
    def test_linkify_mentions_filter(self):
        with self.app.app_context():
            existing_user = User(username='existing_user', email='existing@example.com')
            db.session.add(existing_user)
            db.session.commit()

            # Test case 1: Mix of existing and non-existing users
            text_content1 = "Hello @existing_user and @fake_user. How about @Existing_User?"
            # Expected: existing_user linked (case-insensitively), fake_user not.
            # Note: The link text should use the DB casing 'existing_user'.
            # The match for '@Existing_User' should also link to 'existing_user'.
            linked_text1 = linkify_mentions(text_content1)

            expected_link_existing = f'<a href="/user/existing_user">@existing_user</a>'

            self.assertIn(expected_link_existing, str(linked_text1))
            # Check that @fake_user remains plain text
            self.assertIn("@fake_user", str(linked_text1))
            # Check how many times the link appears - should be twice due to case insensitivity
            self.assertEqual(str(linked_text1).count(expected_link_existing), 2)


            # Test case 2: No mentions
            text_content2 = "Hello world, no mentions here."
            linked_text2 = linkify_mentions(text_content2)
            self.assertEqual(str(linked_text2), text_content2)

            # Test case 3: Only invalid mentions
            text_content3 = "Hello @nope and @another_fake."
            linked_text3 = linkify_mentions(text_content3)
            self.assertEqual(str(linked_text3), text_content3)

            # Test case 4: Mention at the beginning or end
            text_content4 = "@existing_user what's up?"
            linked_text4 = linkify_mentions(text_content4)
            self.assertTrue(str(linked_text4).startswith(expected_link_existing))

            text_content5 = "It's me, @existing_user"
            linked_text5 = linkify_mentions(text_content5)
            self.assertTrue(str(linked_text5).endswith(expected_link_existing))

            # Test case 6: Username with underscores
            user_with_underscore = User(username='user_with_underscore', email='underscore@example.com')
            db.session.add(user_with_underscore)
            db.session.commit()
            text_content6 = "Mentioning @user_with_underscore here."
            linked_text6 = linkify_mentions(text_content6)
            expected_link_underscore = f'<a href="/user/user_with_underscore">@user_with_underscore</a>'
            self.assertIn(expected_link_underscore, str(linked_text6))

    # --- Test for /users/search_mentions autocomplete endpoint ---
    def test_search_mentions_autocomplete_endpoint(self):
        with self.app.app_context():
            # Create users for testing autocomplete
            user_test_alpha = User(username='test_alpha', email='alpha@example.com', profile_picture_url='alpha.jpg')
            user_test_beta = User(username='test_beta', email='beta@example.com') # No profile pic
            user_another = User(username='another_user', email='another@example.com')
            db.session.add_all([user_test_alpha, user_test_beta, user_another, self.user1]) # self.user1 is 'john'
            db.session.commit()

            # Log in a user to access the endpoint
            self._login('john@example.com', 'cat')

            # Test case 1: Query matching multiple users
            response1 = self.client.get('/users/search_mentions?q=test_')
            self.assertEqual(response1.status_code, 200)
            self.assertEqual(response1.content_type, 'application/json')
            data1 = response1.get_json()
            self.assertIn('users', data1)
            self.assertEqual(len(data1['users']), 2)
            usernames_found1 = {u['username'] for u in data1['users']}
            self.assertIn('test_alpha', usernames_found1)
            self.assertIn('test_beta', usernames_found1)

            for u_data in data1['users']:
                if u_data['username'] == 'test_alpha':
                    self.assertTrue(u_data['profile_picture_url'].endswith('images/alpha.jpg'))
                elif u_data['username'] == 'test_beta':
                    self.assertTrue(u_data['profile_picture_url'].endswith('images/default_profile_pic.png'))


            # Test case 2: Query matching one user (case-insensitive)
            response2 = self.client.get('/users/search_mentions?q=TEST_alp')
            self.assertEqual(response2.status_code, 200)
            data2 = response2.get_json()
            self.assertEqual(len(data2['users']), 1)
            self.assertEqual(data2['users'][0]['username'], 'test_alpha')

            # Test case 3: Query matching no users
            response3 = self.client.get('/users/search_mentions?q=xyz_nonexistent')
            self.assertEqual(response3.status_code, 200)
            data3 = response3.get_json()
            self.assertEqual(len(data3['users']), 0)

            # Test case 4: Empty query string
            response4 = self.client.get('/users/search_mentions?q=')
            self.assertEqual(response4.status_code, 200)
            data4 = response4.get_json()
            self.assertEqual(len(data4['users']), 0)

            # Test case 5: Query too short (if there was a min length, e.g. < 1, already handled by route returning empty)
            # Current route logic returns empty for 0 length, and searches for 1 char.
            # If query "a" matches 'test_alpha' and 'another_user'
            response5 = self.client.get('/users/search_mentions?q=a')
            self.assertEqual(response5.status_code, 200)
            data5 = response5.get_json()
            usernames_found5 = {u['username'] for u in data5['users']}
            self.assertIn('test_alpha', usernames_found5) # Starts with 'a' if we consider 'test_alpha'
            self.assertIn('another_user', usernames_found5) # Starts with 'a'
            # The query User.username.ilike(f"{query}%") might behave differently based on DB collation for case.
            # For 'a', it should match 'alpha' and 'another'.
            # Let's refine the users for this test to be clearer.
            # user_apple = User(username='apple', email='apple@example.com')
            # user_apricot = User(username='apricot', email='apricot@example.com')
            # db.session.add_all([user_apple, user_apricot])
            # db.session.commit()
            # response_ap = self.client.get('/users/search_mentions?q=ap')
            # data_ap = response_ap.get_json()
            # self.assertEqual(len(data_ap['users']), 2) # apple, apricot

            self._logout()

if __name__ == '__main__':
    unittest.main(verbosity=2)
