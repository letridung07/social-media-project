import unittest
from flask import current_app, url_for
from app import create_app, db, socketio
from app.core.models import User, Post, Comment, ModerationLog, Notification
from config import TestingConfig
from unittest.mock import patch # For mocking socketio.emit

class ModerationFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create users
        self.user1 = User(username='testuser1', email='testuser1@example.com', password_hash=User.set_password('password123'))
        self.admin_user = User(username='adminuser', email='admin@example.com', password_hash=User.set_password('adminpass'), is_admin=True)
        db.session.add_all([self.user1, self.admin_user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.client.post(url_for('main.login'), data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get(url_for('main.logout'), follow_redirects=True)

    # --- Test Cases for MODERATION_ENABLED = True ---
    def test_create_post_allowed_moderation_enabled(self):
        self.app.config['MODERATION_ENABLED'] = True
        self._login(self.user1.email, 'password123')

        with patch('app.core.routes.socketio.emit') as mock_socket_emit: # Mock socketio
            response = self.client.post(url_for('main.create_post'), data={
                'body': 'This is a perfectly fine post.'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        post = Post.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(post)
        self.assertFalse(post.is_pending_moderation)
        self.assertFalse(post.is_hidden_by_moderation)
        self.assertTrue(post.is_published) # Should be published if allowed and not scheduled

        log_entry = ModerationLog.query.filter_by(related_post_id=post.id).first()
        # Depending on design, 'allowed' might not create a log, or might create one with action 'allowed'.
        # Current implementation in routes.py does not log 'allowed' actions from the system.
        self.assertIsNone(log_entry)
        mock_socket_emit.assert_not_called() # No moderation specific notifications for allowed posts

    def test_create_post_flagged_moderation_enabled(self):
        self.app.config['MODERATION_ENABLED'] = True
        self._login(self.user1.email, 'password123')

        with patch('app.core.routes.socketio.emit') as mock_socket_emit:
            response = self.client.post(url_for('main.create_post'), data={
                'body': 'This is a test_flag_text post that should be flagged.'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        post = Post.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(post)
        self.assertTrue(post.is_pending_moderation)
        self.assertFalse(post.is_hidden_by_moderation)
        self.assertTrue(post.is_published) # Flagged posts are still published pending review

        log_entry = ModerationLog.query.filter_by(related_post_id=post.id).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.action_taken, 'flagged')
        self.assertEqual(log_entry.user_id, self.user1.id) # Author initiated
        self.assertIsNotNone(log_entry.moderation_service_response)

        # No specific 'content_auto_hidden' notification for flagged, but general post notifications might occur.
        # For this test, we are focused on moderation-specific notifications.
        # The route logic for create_post does not send a specific notification for 'flagged'.

    def test_create_post_auto_hidden_moderation_enabled(self):
        self.app.config['MODERATION_ENABLED'] = True
        self._login(self.user1.email, 'password123')

        with patch('app.core.routes.socketio.emit') as mock_socket_emit:
            response = self.client.post(url_for('main.create_post'), data={
                'body': 'This is a test_block_severe_text post that should be auto-hidden.'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        post = Post.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(post)
        self.assertFalse(post.is_pending_moderation) # Hidden implies not just pending
        self.assertTrue(post.is_hidden_by_moderation)
        self.assertFalse(post.is_published) # Hidden posts should not be published

        log_entry = ModerationLog.query.filter_by(related_post_id=post.id).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.action_taken, 'auto_hidden')
        self.assertEqual(log_entry.user_id, self.user1.id)

        # Check for notification to author
        notification = Notification.query.filter_by(recipient_id=self.user1.id, type='content_auto_hidden', related_post_id=post.id).first()
        self.assertIsNotNone(notification)

        # Check that socketio was called for the auto-hidden notification
        mock_socket_emit.assert_any_call('new_notification',
                                         {'type': 'content_auto_hidden',
                                          'message': f"Your recent post ('{post.body[:30]}...') was automatically hidden pending review.",
                                          'post_id': post.id},
                                         room=str(self.user1.id))

        # Verify points are NOT awarded (need to check UserPoints model or related ActivityLog)
        # This requires UserPoints model and award_points logic to be integrated.
        # For now, we'll assume this needs to be checked via ActivityLog or UserPoints.
        # Example: self.assertEqual(self.user1.points_data_ref.points, 0) if starting from 0.

    def test_add_comment_allowed_moderation_enabled(self):
        self.app.config['MODERATION_ENABLED'] = True
        self._login(self.user1.email, 'password123')
        # Create a post first
        post_resp = self.client.post(url_for('main.create_post'), data={'body': 'Parent post for comment'}, follow_redirects=True)
        parent_post = Post.query.first()

        with patch('app.core.routes.socketio.emit') as mock_socket_emit:
            response = self.client.post(url_for('main.add_comment', post_id=parent_post.id), data={
                'body': 'This is a perfectly fine comment.'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        comment = Comment.query.filter_by(user_id=self.user1.id, post_id=parent_post.id).first()
        self.assertIsNotNone(comment)
        self.assertFalse(comment.is_pending_moderation)
        self.assertFalse(comment.is_hidden_by_moderation)

        log_entry = ModerationLog.query.filter_by(related_comment_id=comment.id).first()
        self.assertIsNone(log_entry) # No log for allowed comments from system

    def test_add_comment_flagged_moderation_enabled(self):
        self.app.config['MODERATION_ENABLED'] = True
        self._login(self.user1.email, 'password123')
        post_resp = self.client.post(url_for('main.create_post'), data={'body': 'Parent post for flagged comment'}, follow_redirects=True)
        parent_post = Post.query.first()

        with patch('app.core.routes.socketio.emit') as mock_socket_emit:
            response = self.client.post(url_for('main.add_comment', post_id=parent_post.id), data={
                'body': 'This comment contains test_flag_text and should be flagged.'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        comment = Comment.query.filter_by(user_id=self.user1.id, post_id=parent_post.id).first()
        self.assertIsNotNone(comment)
        self.assertTrue(comment.is_pending_moderation)
        self.assertFalse(comment.is_hidden_by_moderation)

        log_entry = ModerationLog.query.filter_by(related_comment_id=comment.id).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.action_taken, 'flagged')

    def test_add_comment_auto_hidden_moderation_enabled(self):
        self.app.config['MODERATION_ENABLED'] = True
        self._login(self.user1.email, 'password123')
        post_resp = self.client.post(url_for('main.create_post'), data={'body': 'Parent post for hidden comment'}, follow_redirects=True)
        parent_post = Post.query.first()

        with patch('app.core.routes.socketio.emit') as mock_socket_emit:
            response = self.client.post(url_for('main.add_comment', post_id=parent_post.id), data={
                'body': 'This comment is test_block_severe_text and should be auto-hidden.'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        comment = Comment.query.filter_by(user_id=self.user1.id, post_id=parent_post.id).first()
        self.assertIsNotNone(comment)
        self.assertFalse(comment.is_pending_moderation)
        self.assertTrue(comment.is_hidden_by_moderation)

        log_entry = ModerationLog.query.filter_by(related_comment_id=comment.id).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.action_taken, 'auto_hidden')

        notification = Notification.query.filter_by(recipient_id=self.user1.id, type='content_auto_hidden', related_comment_id=comment.id).first()
        self.assertIsNotNone(notification)
        mock_socket_emit.assert_any_call('new_notification',
                                         {'type': 'content_auto_hidden',
                                          'message': f"Your recent comment ('{comment.body[:30]}...') on post ID {parent_post.id} was automatically hidden pending review.",
                                          'comment_id': comment.id, 'post_id': parent_post.id},
                                         room=str(self.user1.id))

    # --- Test Cases for MODERATION_ENABLED = False ---
    def test_create_post_moderation_disabled(self):
        self.app.config['MODERATION_ENABLED'] = False
        self._login(self.user1.email, 'password123')

        with patch('app.core.routes.socketio.emit') as mock_socket_emit: # Still mock in case other notifications fire
            response = self.client.post(url_for('main.create_post'), data={
                'body': 'This is a test_block_severe_text post but moderation is off.'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        post = Post.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(post)
        self.assertFalse(post.is_pending_moderation)
        self.assertFalse(post.is_hidden_by_moderation)
        self.assertTrue(post.is_published) # Should be published

        log_entry = ModerationLog.query.filter_by(related_post_id=post.id).first()
        self.assertIsNone(log_entry) # No moderation log when disabled

        # Verify points ARE awarded (this needs UserPoints and ActivityLog setup)
        # Example: self.assertGreater(self.user1.points_data_ref.points, 0)

    def test_add_comment_moderation_disabled(self):
        self.app.config['MODERATION_ENABLED'] = False
        self._login(self.user1.email, 'password123')
        post_resp = self.client.post(url_for('main.create_post'), data={'body': 'Parent for comment, mod off'}, follow_redirects=True)
        parent_post = Post.query.first()

        with patch('app.core.routes.socketio.emit') as mock_socket_emit:
            response = self.client.post(url_for('main.add_comment', post_id=parent_post.id), data={
                'body': 'This is a test_block_severe_text comment but moderation is off.'
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        comment = Comment.query.filter_by(user_id=self.user1.id, post_id=parent_post.id).first()
        self.assertIsNotNone(comment)
        self.assertFalse(comment.is_pending_moderation)
        self.assertFalse(comment.is_hidden_by_moderation)

        log_entry = ModerationLog.query.filter_by(related_comment_id=comment.id).first()
        self.assertIsNone(log_entry)

    # --- Content Visibility Tests ---
    def test_hidden_post_visibility(self):
        self.app.config['MODERATION_ENABLED'] = True
        # User1 creates a post that gets auto-hidden
        self._login(self.user1.email, 'password123')
        hidden_post_body = "test_block_severe_text hidden post for visibility test"
        self.client.post(url_for('main.create_post'), data={'body': hidden_post_body}, follow_redirects=True)
        self._logout()

        hidden_post = Post.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(hidden_post)
        self.assertTrue(hidden_post.is_hidden_by_moderation)

        # User2 (another normal user) logs in
        user2 = User(username='user2', email='user2@example.com')
        user2.set_password('password2')
        db.session.add(user2)
        db.session.commit()
        self._login(user2.email, 'password2')

        # User2 checks main feed - hidden post should NOT appear
        response_feed = self.client.get(url_for('main.index'))
        self.assertNotIn(hidden_post_body.encode(), response_feed.data)

        # User2 checks User1's profile - hidden post should NOT appear
        response_profile_user1 = self.client.get(url_for('main.profile', username=self.user1.username))
        self.assertNotIn(hidden_post_body.encode(), response_profile_user1.data)
        self._logout()

        # User1 (author) logs in and checks own profile - hidden post SHOULD appear
        self._login(self.user1.email, 'password123')
        response_own_profile = self.client.get(url_for('main.profile', username=self.user1.username))
        self.assertIn(hidden_post_body.encode(), response_own_profile.data)
        # Check for visual cue if implemented in template, e.g., "(Hidden by moderation)"
        self._logout()

        # Admin user logs in and checks moderation queue - hidden post SHOULD appear
        self._login(self.admin_user.email, 'adminpass')
        response_admin_queue = self.client.get(url_for('admin.moderation_queue'))
        self.assertIn(hidden_post_body.encode(), response_admin_queue.data)
        self._logout()

    def test_hidden_comment_visibility(self):
        self.app.config['MODERATION_ENABLED'] = True
        # User1 creates a post
        self._login(self.user1.email, 'password123')
        parent_post_body = "Parent post for hidden comment visibility test"
        self.client.post(url_for('main.create_post'), data={'body': parent_post_body}, follow_redirects=True)
        parent_post = Post.query.filter_by(user_id=self.user1.id).first()

        # User1 adds a comment that gets auto-hidden
        hidden_comment_body = "test_block_severe_text hidden comment for visibility"
        self.client.post(url_for('main.add_comment', post_id=parent_post.id), data={'body': hidden_comment_body}, follow_redirects=True)
        self._logout()

        hidden_comment = Comment.query.filter_by(post_id=parent_post.id, user_id=self.user1.id).first()
        self.assertIsNotNone(hidden_comment)
        self.assertTrue(hidden_comment.is_hidden_by_moderation)

        # User2 logs in
        user2 = User(username='user2_comment_vis', email='user2_cv@example.com')
        user2.set_password('password2cv')
        db.session.add(user2)
        db.session.commit()
        self._login(user2.email, 'password2cv')

        # User2 views the parent post - hidden comment should NOT appear
        # This test assumes comments are displayed on the post's page (e.g., profile or index if post is there)
        # Let's check User1's profile where parent_post would be.
        response_post_view_user2 = self.client.get(url_for('main.profile', username=self.user1.username))
        self.assertIn(parent_post_body.encode(), response_post_view_user2.data) # Parent post is visible
        self.assertNotIn(hidden_comment_body.encode(), response_post_view_user2.data) # Hidden comment is not
        self._logout()

        # User1 (author of comment) logs in and views the post - hidden comment SHOULD appear (with indicator)
        self._login(self.user1.email, 'password123')
        response_post_view_author = self.client.get(url_for('main.profile', username=self.user1.username))
        self.assertIn(parent_post_body.encode(), response_post_view_author.data)
        self.assertIn(hidden_comment_body.encode(), response_post_view_author.data)
        self.assertIn(b"Hidden (Visible only to you)", response_post_view_author.data) # Check for indicator
        self._logout()

        # Admin user logs in and checks moderation queue - hidden comment SHOULD appear
        self._login(self.admin_user.email, 'adminpass')
        response_admin_queue = self.client.get(url_for('admin.moderation_queue'))
        self.assertIn(hidden_comment_body.encode(), response_admin_queue.data)
        self._logout()

if __name__ == '__main__':
    unittest.main()
