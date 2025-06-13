# tests/test_posts.py
import unittest
import os
import io # For creating mock files
from flask import current_app
from app import create_app, db
from app.models import User, Post, MediaItem, Mention, Comment, Notification # Added MediaItem
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

        # Path for media items - ensure it's cleaned up
        # Assuming TestingConfig defines MEDIA_ITEMS_UPLOAD_FOLDER
        # e.g., MEDIA_ITEMS_UPLOAD_FOLDER = 'app/static/media_items_test'
        self.media_items_upload_folder_config = current_app.config.get('MEDIA_ITEMS_UPLOAD_FOLDER', 'static/media_items_test')
        self.media_items_path = os.path.join(current_app.root_path, self.media_items_upload_folder_config)
        os.makedirs(self.media_items_path, exist_ok=True)


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

        # Clean up media_items_test directory
        if os.path.exists(self.media_items_path):
            for f in os.listdir(self.media_items_path):
                try:
                    os.remove(os.path.join(self.media_items_path, f))
                except OSError:
                    pass # Ignore if file is already removed or other issues
            # Only remove if empty, to avoid error if another process/test has files there.
            # However, for isolated tests, it should be empty.
            if not os.listdir(self.media_items_path):
                 os.rmdir(self.media_items_path)


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
        self.assertIsNone(post.media_items.first()) # Ensure no media items

        # Check if the post appears on the index page (where redirect goes)
        self.assertIn(b'This is a text-only post!', response.data)
        self.assertNotIn(b'media-gallery', response.data) # Check that no gallery is shown

        # Check profile page as well
        response_profile = self.client.get(f'/user/{self.user1.username}')
        self.assertIn(b'This is a text-only post!', response_profile.data)
        self.assertNotIn(b'media-gallery', response_profile.data)
        self._logout()

    def test_create_post_with_media_items(self):
        self._login('john@example.com', 'cat')

        # Create mock image and video files
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        mock_image_data = io.BytesIO(base64.b64decode(png_b64))
        mock_image_file = FileStorage(stream=mock_image_data, filename="test_image.png", content_type="image/png")

        mock_video_data = io.BytesIO(b"dummy video data")
        mock_video_file = FileStorage(stream=mock_video_data, filename="test_video.mp4", content_type="video/mp4")

        post_caption = "This is an album post with one image and one video!"

        response = self.client.post('/create_post', data={
            'body': post_caption,
            'media_files': [mock_image_file, mock_video_file]
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your post is now live!', response.data)

        post = Post.query.filter_by(body=post_caption).first()
        self.assertIsNotNone(post)
        self.assertEqual(post.body, post_caption)

        # Verify MediaItems
        media_items = post.media_items.all()
        self.assertEqual(len(media_items), 2)

        image_item = next((item for item in media_items if item.media_type == 'image'), None)
        video_item = next((item for item in media_items if item.media_type == 'video'), None)

        self.assertIsNotNone(image_item)
        self.assertTrue(image_item.filename.endswith('.png'))
        expected_image_path = os.path.join(self.media_items_path, image_item.filename)
        self.assertTrue(os.path.exists(expected_image_path))
        self.assertIsNone(image_item.alt_text) # Alt text is not handled per item in create form yet

        self.assertIsNotNone(video_item)
        self.assertTrue(video_item.filename.endswith('.mp4'))
        expected_video_path = os.path.join(self.media_items_path, video_item.filename)
        self.assertTrue(os.path.exists(expected_video_path))
        self.assertIsNone(video_item.alt_text)

        # Verify gallery is displayed on index page (where redirect goes)
        self.assertIn(b'<div class="media-gallery', response.data)
        self.assertIn(f'src="/static/{self.media_items_upload_folder_config}/{image_item.filename}"'.encode(), response.data)
        self.assertIn(f'src="/static/{self.media_items_upload_folder_config}/{video_item.filename}"'.encode(), response.data)
        self.assertIn(post_caption.encode(), response.data)

        # Check for carousel class if multiple items
        if len(media_items) > 1:
            self.assertIn(b'media-gallery mb-3 carousel', response.data) # Check for carousel class
            self.assertIn(b'carousel-nav', response.data) # Check for nav buttons structure

        self._logout()

    def test_create_post_with_invalid_media_file_type(self):
        self._login('john@example.com', 'cat')

        if not os.path.exists(self.media_items_path):
            os.makedirs(self.media_items_path)

        mock_invalid_file_data = io.BytesIO(b"this is not an image or video")
        mock_file = FileStorage(stream=mock_invalid_file_data, filename="test.txt", content_type="text/plain")

        response = self.client.post('/create_post', data={
            'body': 'Trying to upload a text file to media_files.',
            'media_files': [mock_file]
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response.status_code, 200) # Form re-renders with error
        # Check for the error message from FileAllowed validator
        self.assertIn(b'Images or videos only!', response.data)

        post = Post.query.filter_by(body='Trying to upload a text file to media_files.').first()
        self.assertIsNone(post) # Post should not be created

        self.assertEqual(len(os.listdir(self.media_items_path)), 0, "A file was saved despite invalid type")
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
        # Assuming default privacy is public or John follows Susan for this to pass for Susan's post
        # For this test, let's assume public posts from non-followed are not on feed by default.
        self.assertNotIn(b'Post by Susan', response_index.data)
        self.assertIn(b'john', response_index.data) # Author username
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

    def test_edit_post_with_media_items(self):
        self._login('john@example.com', 'cat')

        # 1. Create initial post with one image and one video
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        initial_image_data = io.BytesIO(base64.b64decode(png_b64))
        initial_image_file = FileStorage(stream=initial_image_data, filename="initial_image.png", content_type="image/png")
        initial_video_data = io.BytesIO(b"initial video data")
        initial_video_file = FileStorage(stream=initial_video_data, filename="initial_video.mp4", content_type="video/mp4")

        initial_caption = "Initial album for edit test"
        create_resp = self.client.post('/create_post', data={
            'body': initial_caption,
            'media_files': [initial_image_file, initial_video_file]
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(create_resp.status_code, 200)
        post = Post.query.filter_by(body=initial_caption).first()
        self.assertIsNotNone(post)
        initial_media_items = post.media_items.all()
        self.assertEqual(len(initial_media_items), 2)
        initial_image_item = next(item for item in initial_media_items if item.media_type == 'image')
        initial_video_item = next(item for item in initial_media_items if item.media_type == 'video')

        # 2. Test Adding a new image
        new_image_data = io.BytesIO(base64.b64decode(png_b64)) # fresh stream
        new_image_file = FileStorage(stream=new_image_data, filename="new_image.png", content_type="image/png")
        updated_caption = "Caption updated, new image added"

        edit_resp_add = self.client.post(f'/edit_post/{post.id}', data={
            'body': updated_caption,
            'media_files': [new_image_file],
            # No delete_media_ids[] means we keep existing ones
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(edit_resp_add.status_code, 200)
        db.session.refresh(post)
        self.assertEqual(post.body, updated_caption)
        self.assertEqual(post.media_items.count(), 3) # 2 initial + 1 new
        new_image_item_db = post.media_items.filter(MediaItem.filename.contains('new_image.png')).first()
        self.assertIsNotNone(new_image_item_db)
        self.assertTrue(os.path.exists(os.path.join(self.media_items_path, new_image_item_db.filename)))

        # 3. Test Deleting the initial video
        caption_after_delete = "Caption same, video deleted"
        edit_resp_delete = self.client.post(f'/edit_post/{post.id}', data={
            'body': caption_after_delete, # Can also test caption change here
            'delete_media_ids[]': [initial_video_item.id]
            # No new media_files
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(edit_resp_delete.status_code, 200)
        db.session.refresh(post)
        self.assertEqual(post.body, caption_after_delete)
        self.assertEqual(post.media_items.count(), 2) # 3 - 1 deleted = 2
        self.assertIsNone(MediaItem.query.get(initial_video_item.id))
        self.assertFalse(os.path.exists(os.path.join(self.media_items_path, initial_video_item.filename)))
        # Ensure the other two (initial image, new image) are still there
        self.assertIsNotNone(MediaItem.query.get(initial_image_item.id))
        self.assertIsNotNone(MediaItem.query.get(new_image_item_db.id))

        self._logout()

    def test_delete_post_with_media_items(self):
        self._login('john@example.com', 'cat')
        # 1. Create a post with media
        img_data = io.BytesIO(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="))
        vid_data = io.BytesIO(b"video data for delete test")
        files_to_upload = [
            FileStorage(stream=img_data, filename="del_img.png", content_type="image/png"),
            FileStorage(stream=vid_data, filename="del_vid.mp4", content_type="video/mp4")
        ]
        create_resp = self.client.post('/create_post', data={
            'body': "Post to be deleted with media",
            'media_files': files_to_upload
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(create_resp.status_code, 200)
        post_to_delete = Post.query.filter_by(body="Post to be deleted with media").first()
        self.assertIsNotNone(post_to_delete)
        media_items_to_delete = post_to_delete.media_items.all()
        self.assertEqual(len(media_items_to_delete), 2)
        media_filenames = [item.filename for item in media_items_to_delete]
        for filename in media_filenames:
             self.assertTrue(os.path.exists(os.path.join(self.media_items_path, filename)))

        # 2. Delete the post
        delete_resp = self.client.post(f'/delete_post/{post_to_delete.id}', follow_redirects=True)
        self.assertEqual(delete_resp.status_code, 200)
        self.assertIn(b'Your post and all its media have been deleted!', delete_resp.data)

        # 3. Verify deletion from DB
        self.assertIsNone(Post.query.get(post_to_delete.id))
        self.assertEqual(MediaItem.query.filter_by(post_id=post_to_delete.id).count(), 0)

        # 4. Verify physical files are deleted
        for filename in media_filenames:
            self.assertFalse(os.path.exists(os.path.join(self.media_items_path, filename)))

        self._logout()

    def test_gallery_display_in_post_view(self):
        self._login('john@example.com', 'cat')

        # Scenario 1: Post with 0 media items (text-only post)
        self.client.post('/create_post', data={'body': 'Text only for gallery test'}, follow_redirects=True)
        response_0_items = self.client.get(f'/user/{self.user1.username}')
        self.assertNotIn(b'media-gallery', response_0_items.data)

        # Scenario 2: Post with 1 media item
        img_data_1 = io.BytesIO(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="))
        file1 = FileStorage(stream=img_data_1, filename="single_img.png", content_type="image/png")
        self.client.post('/create_post', data={'body': 'Post with one image', 'media_files': [file1]}, content_type='multipart/form-data', follow_redirects=True)

        post_1_item = Post.query.filter_by(body='Post with one image').first()
        media_item_1 = post_1_item.media_items.first()
        response_1_item = self.client.get(f'/user/{self.user1.username}') # Assuming posts are on profile page

        self.assertIn(b'<div class="media-gallery mb-3">', response_1_item.data) # Gallery div exists
        self.assertNotIn(b'carousel', response_1_item.data) # No carousel class for single item
        self.assertNotIn(b'carousel-nav', response_1_item.data) # No nav buttons
        self.assertIn(f'src="/static/{self.media_items_upload_folder_config}/{media_item_1.filename}"'.encode(), response_1_item.data)
        # Check that only one media item is rendered within a gallery item structure
        # This depends on the exact HTML, but we can count occurrences of 'media-gallery-item'
        # The class is inside the loop in _post.html, so this check is valid.
        self.assertEqual(response_1_item.data.count(b'<div class="media-gallery-item">'), 1)


        # Scenario 3: Post with 3 media items
        img_data_2 = io.BytesIO(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="))
        img_data_3 = io.BytesIO(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="))
        vid_data_1 = io.BytesIO(b"video data for 3 item gallery")
        files_3 = [
            FileStorage(stream=img_data_2, filename="img_gallery_1.png", content_type="image/png"),
            FileStorage(stream=vid_data_1, filename="vid_gallery_1.mp4", content_type="video/mp4"),
            FileStorage(stream=img_data_3, filename="img_gallery_2.png", content_type="image/png")
        ]
        self.client.post('/create_post', data={'body': 'Post with three items', 'media_files': files_3}, content_type='multipart/form-data', follow_redirects=True)

        post_3_items = Post.query.filter_by(body='Post with three items').first()
        media_items_3 = post_3_items.media_items.order_by(MediaItem.id).all() # Ensure consistent order for checking src
        response_3_items = self.client.get(f'/user/{self.user1.username}')

        self.assertIn(b'<div class="media-gallery mb-3 carousel">', response_3_items.data) # Carousel class should be present
        self.assertIn(b'<div class="carousel-track">', response_3_items.data)
        self.assertIn(b'<div class="carousel-nav">', response_3_items.data)
        self.assertIn(b'<button class="carousel-prev">', response_3_items.data)
        self.assertIn(b'<button class="carousel-next">', response_3_items.data)
        self.assertEqual(response_3_items.data.count(b'<div class="media-gallery-item">'), 3)
        for item in media_items_3:
            self.assertIn(f'src="/static/{self.media_items_upload_folder_config}/{item.filename}"'.encode(), response_3_items.data)

        self._logout()

    def test_edit_post_delete_all_media(self):
        self._login('john@example.com', 'cat')
        # 1. Create a post with 2 media items
        img_data_1 = io.BytesIO(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="))
        img_data_2 = io.BytesIO(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="))
        files_to_create = [
            FileStorage(stream=img_data_1, filename="img_to_del_1.png", content_type="image/png"),
            FileStorage(stream=img_data_2, filename="img_to_del_2.png", content_type="image/png")
        ]
        create_resp = self.client.post('/create_post', data={
            'body': "Post to delete all media from",
            'media_files': files_to_create
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(create_resp.status_code, 200)
        post = Post.query.filter_by(body="Post to delete all media from").first()
        self.assertIsNotNone(post)
        initial_media_ids = [item.id for item in post.media_items.all()]
        media_filenames_to_delete = [item.filename for item in post.media_items.all()] # Store filenames for file system check
        self.assertEqual(len(initial_media_ids), 2)

        # 2. Edit post and mark all media for deletion
        edit_resp = self.client.post(f'/edit_post/{post.id}', data={
            'body': "Caption remains, all media deleted",
            'delete_media_ids[]': initial_media_ids
        }, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(edit_resp.status_code, 200)
        self.assertIn(b'Your post has been updated!', edit_resp.data)

        db.session.refresh(post)
        self.assertEqual(post.body, "Caption remains, all media deleted")
        self.assertEqual(post.media_items.count(), 0)

        # Verify files are physically deleted
        for filename in media_filenames_to_delete:
            self.assertFalse(os.path.exists(os.path.join(self.media_items_path, filename)))

        # Verify MediaItem records are gone from DB
        for media_id in initial_media_ids:
            self.assertIsNone(MediaItem.query.get(media_id))

        # Verify rendered post on profile page shows no gallery
        profile_resp = self.client.get(f'/user/{self.user1.username}')
        self.assertNotIn(b'media-gallery', profile_resp.data)
        self.assertIn(b"Caption remains, all media deleted", profile_resp.data)

        self._logout()


if __name__ == '__main__':
    unittest.main(verbosity=2)
