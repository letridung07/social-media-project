import unittest
from flask import current_app, url_for
from app import create_app, db, socketio
from app.core.models import User, Post, Comment, ModerationLog, Notification
from config import TestingConfig
from unittest.mock import patch

class AdminModerationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create users
        self.user_author = User(username='authoruser', email='author@example.com')
        self.user_author.set_password('authorpass')
        self.admin_user = User(username='admin', email='admin@example.com', is_admin=True)
        self.admin_user.set_password('adminpass')
        db.session.add_all([self.user_author, self.admin_user])
        db.session.commit()

        # Enable moderation for these tests
        self.app.config['MODERATION_ENABLED'] = True
        # To award points correctly, we need to set up the UserPoints model for the author
        # from app.core.models import UserPoints
        # author_points = UserPoints(user_id=self.user_author.id, points=0)
        # db.session.add(author_points)
        # db.session.commit()
        # This setup might be better in a fixture or base test class if UserPoints is always needed.

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

    def _create_flagged_post(self):
        self._login(self.user_author.email, 'authorpass')
        # Text known to be flagged by MockModerationService
        self.client.post(url_for('main.create_post'), data={'body': 'This is test_flag_text for admin queue.'}, follow_redirects=True)
        self._logout()
        return Post.query.filter_by(user_id=self.user_author.id).order_by(Post.id.desc()).first()

    def _create_hidden_comment(self, post_id):
        self._login(self.user_author.email, 'authorpass')
        # Text known to be auto-hidden
        self.client.post(url_for('main.add_comment', post_id=post_id), data={'body': 'This is test_block_severe_text for admin queue comment.'}, follow_redirects=True)
        self._logout()
        return Comment.query.filter_by(user_id=self.user_author.id, post_id=post_id).order_by(Comment.id.desc()).first()

    def test_moderation_queue_access_and_content(self):
        flagged_post = self._create_flagged_post()
        hidden_comment = self._create_hidden_comment(flagged_post.id) # Comment on the flagged post

        self._login(self.admin_user.email, 'adminpass')
        response = self.client.get(url_for('admin.moderation_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Moderation Queue', response.data)
        self.assertIn(flagged_post.body.encode(), response.data)
        self.assertIn(hidden_comment.body.encode(), response.data)
        self.assertIn(b'Pending Review', response.data) # For flagged_post
        self.assertIn(b'Hidden', response.data) # For hidden_comment

    @patch('app.admin.routes.socketio.emit') # Patch where socketio is used in admin.routes
    def test_approve_flagged_post(self, mock_socket_emit):
        flagged_post = self._create_flagged_post()
        initial_author_points = self.user_author.points_data_ref.points if self.user_author.points_data_ref else 0


        self._login(self.admin_user.email, 'adminpass')
        response = self.client.post(url_for('admin.approve_content', content_type='post', content_id=flagged_post.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Post ID %d approved and published.' % flagged_post.id, response.data)

        db.session.refresh(flagged_post)
        self.assertFalse(flagged_post.is_pending_moderation)
        self.assertFalse(flagged_post.is_hidden_by_moderation)
        self.assertTrue(flagged_post.is_published)

        log_entry = ModerationLog.query.filter_by(related_post_id=flagged_post.id, action_taken='approved_by_admin').first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.user_id, self.admin_user.id)

        notification = Notification.query.filter_by(recipient_id=self.user_author.id, type='content_approved', related_post_id=flagged_post.id).first()
        self.assertIsNotNone(notification)
        mock_socket_emit.assert_called_with('new_notification',
                                            {'type': 'content_approved',
                                             'message': f"Your post ('{flagged_post.body[:30]}...') has been approved and is now visible.",
                                             'content_id': flagged_post.id, 'content_type': 'post'},
                                            room=str(self.user_author.id))

        # Check points (assuming 10 for a text post)
        # db.session.refresh(self.user_author.points_data_ref)
        # self.assertEqual(self.user_author.points_data_ref.points, initial_author_points + 10)


    @patch('app.admin.routes.socketio.emit')
    def test_approve_hidden_comment(self, mock_socket_emit):
        parent_post = self._create_flagged_post() # Create any post for the comment
        hidden_comment = self._create_hidden_comment(parent_post.id)
        initial_author_points = self.user_author.points_data_ref.points if self.user_author.points_data_ref else 0
        # initial_post_author_points = parent_post.author.points_data_ref.points if parent_post.author.points_data_ref else 0


        self._login(self.admin_user.email, 'adminpass')
        response = self.client.post(url_for('admin.approve_content', content_type='comment', content_id=hidden_comment.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Comment ID %d approved and published.' % hidden_comment.id, response.data)

        db.session.refresh(hidden_comment)
        self.assertFalse(hidden_comment.is_pending_moderation)
        self.assertFalse(hidden_comment.is_hidden_by_moderation)

        log_entry = ModerationLog.query.filter_by(related_comment_id=hidden_comment.id, action_taken='approved_by_admin').first()
        self.assertIsNotNone(log_entry)

        notification = Notification.query.filter_by(recipient_id=self.user_author.id, type='content_approved', related_comment_id=hidden_comment.id).first()
        self.assertIsNotNone(notification)
        mock_socket_emit.assert_called_with('new_notification',
                                            {'type': 'content_approved',
                                             'message': f"Your comment ('{hidden_comment.body[:30]}...') has been approved and is now visible.",
                                             'content_id': hidden_comment.id, 'content_type': 'comment'},
                                            room=str(self.user_author.id))

        # Check points (5 for comment, 3 for post author if different)
        # db.session.refresh(self.user_author.points_data_ref)
        # self.assertEqual(self.user_author.points_data_ref.points, initial_author_points + 5)
        # if parent_post.author_id != self.user_author.id:
        #     db.session.refresh(parent_post.author.points_data_ref)
        #     self.assertEqual(parent_post.author.points_data_ref.points, initial_post_author_points + 3)


    @patch('app.admin.routes.socketio.emit')
    def test_reject_hide_post(self, mock_socket_emit):
        flagged_post = self._create_flagged_post()
        self._login(self.admin_user.email, 'adminpass')
        response = self.client.post(url_for('admin.reject_hide_content', content_type='post', content_id=flagged_post.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Post ID %d rejected and will remain hidden.' % flagged_post.id, response.data)

        db.session.refresh(flagged_post)
        self.assertFalse(flagged_post.is_pending_moderation)
        self.assertTrue(flagged_post.is_hidden_by_moderation)
        self.assertFalse(flagged_post.is_published)

        log_entry = ModerationLog.query.filter_by(related_post_id=flagged_post.id, action_taken='rejected_by_admin_hidden').first()
        self.assertIsNotNone(log_entry)

        notification = Notification.query.filter_by(recipient_id=self.user_author.id, type='content_rejected_hidden', related_post_id=flagged_post.id).first()
        self.assertIsNotNone(notification)
        mock_socket_emit.assert_called_with('new_notification',
                                            {'type': 'content_rejected_hidden',
                                             'message': f"Your post ('{flagged_post.body[:30]}...') was reviewed and will remain hidden.",
                                             'content_id': flagged_post.id, 'content_type': 'post'},
                                            room=str(self.user_author.id))

    @patch('app.admin.routes.socketio.emit')
    def test_delete_moderated_comment(self, mock_socket_emit):
        parent_post = self._create_flagged_post() # Create a post for the comment
        hidden_comment = self._create_hidden_comment(parent_post.id)
        comment_id_for_test = hidden_comment.id
        comment_body_snippet = hidden_comment.body[:30]

        self._login(self.admin_user.email, 'adminpass')
        response = self.client.post(url_for('admin.delete_moderated_content', content_type='comment', content_id=comment_id_for_test), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Comment ID %d has been deleted.' % comment_id_for_test, response.data)

        self.assertIsNone(Comment.query.get(comment_id_for_test))

        log_entry = ModerationLog.query.filter_by(related_comment_id=comment_id_for_test, action_taken='deleted_by_admin').first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.user_id, self.admin_user.id)

        # The related_comment_id in notification might be tricky if the comment is deleted before notification is processed
        # or if the FK is an issue. The current implementation logs before deleting.
        notification = Notification.query.filter_by(recipient_id=self.user_author.id, type='content_deleted_by_admin').first()
        # We might need to query by actor_id or a combination if related_id is null due to deletion.
        # For this test, we check if any 'content_deleted_by_admin' notification was sent to the author.
        self.assertIsNotNone(notification)
        self.assertIsNone(notification.related_comment_id) # As the comment is deleted

        mock_socket_emit.assert_called_with('new_notification',
                                            {'type': 'content_deleted_by_admin',
                                             'message': f"Your comment ('{comment_body_snippet}...') was removed by an administrator.",
                                             'content_type': 'comment'},
                                            room=str(self.user_author.id))

if __name__ == '__main__':
    unittest.main()
