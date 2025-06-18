import unittest
from unittest.mock import patch # Add this import
import os
import io
from flask_login import current_user
from flask_socketio import SocketIOTestClient

from app import create_app, db, socketio
from app.core.models import User, Post, Notification, Comment, Reaction # Corrected import, changed Like to Reaction
from config import TestingConfig

class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client(use_cookies=True)
        self.socketio_test_client = socketio.test_client(self.app, flask_test_client=self.client)

        # Create test users
        self.user1 = User(username='testuser1', email='test1@example.com')
        self.user1.set_password('password')
        self.user2 = User(username='testuser2', email='test2@example.com')
        self.user2.set_password('password')
        db.session.add_all([self.user1, self.user2])
        db.session.commit()

    def tearDown(self):
        if self.socketio_test_client:
            # It seems there isn't a direct 'is_connected' attribute.
            # Disconnecting should be safe even if not connected or namespace not used.
            try:
                self.socketio_test_client.disconnect(namespace='/')
            except Exception: # pylint: disable=broad-except
                pass # Ignore errors if already disconnected or namespace issues

        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # --- Test /notifications route ---
    def test_notifications_page_unauthenticated(self):
        response = self.client.get('/notifications')
        self.assertEqual(response.status_code, 302) # Redirect
        self.assertTrue('/login' in response.location)

    def test_notifications_page_authenticated_no_notifications(self):
        self._login('test1@example.com', 'password')
        response = self.client.get('/notifications')
        self.assertEqual(response.status_code, 200)
        self.assertIn("You have no notifications.", response.get_data(as_text=True))
        self._logout()

    def test_notifications_page_with_notifications(self):
        # user2 creates a post
        post_by_user2 = Post(body="User2's Post", author=self.user2)
        db.session.add(post_by_user2)
        db.session.commit()

        # user1 logs in and likes user2's post
        self._login('test1@example.com', 'password')
        self.client.post(f'/like/{post_by_user2.id}', follow_redirects=True)
        self._logout()

        # user2 logs in and checks notifications
        self._login('test2@example.com', 'password')
        response = self.client.get('/notifications')
        self.assertEqual(response.status_code, 200)
        response_data = response.get_data(as_text=True)
        self.assertIn(self.user1.username, response_data)
        self.assertIn("liked your", response_data)
        self.assertIn("post", response_data) # Check if "post" is part of a link or text
        # More specific check for the link structure if needed:
        # self.assertIn(f'<a href="/user/{self.user1.username}">{self.user1.username}</a>', response_data)
        # self.assertIn(f'<a href="/user/{self.user2.username}#post-{post_by_user2.id}">post</a>', response_data)
        self._logout()

    # --- Test Notification Object Creation ---
    def test_notification_created_on_like(self):
        post_by_user1 = Post(body="User1's Post for Like Test", author=self.user1)
        db.session.add(post_by_user1)
        db.session.commit()

        self._login('test2@example.com', 'password') # user2 logs in
        self.client.post(f'/like/{post_by_user1.id}', follow_redirects=True)

        notification = Notification.query.filter_by(recipient_id=self.user1.id).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.user2.id)
        self.assertEqual(notification.type, 'like')
        self.assertEqual(notification.related_post_id, post_by_user1.id)
        self._logout()

    def test_notification_created_on_comment(self):
        post_by_user1 = Post(body="User1's Post for Comment Test", author=self.user1)
        db.session.add(post_by_user1)
        db.session.commit()

        self._login('test2@example.com', 'password') # user2 logs in
        self.client.post(f'/post/{post_by_user1.id}/comment', data={'body': 'A test comment'}, follow_redirects=True)

        notification = Notification.query.filter_by(recipient_id=self.user1.id, type='comment').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.user2.id)
        self.assertEqual(notification.related_post_id, post_by_user1.id)
        self._logout()

    def test_notification_created_on_follow(self):
        self._login('test2@example.com', 'password') # user2 logs in
        self.client.post(f'/follow/{self.user1.username}', follow_redirects=True)

        notification = Notification.query.filter_by(recipient_id=self.user1.id, type='follow').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.user2.id)
        self._logout()

    def test_no_notification_for_own_action(self):
        post_by_user1 = Post(body="User1's Own Action Test Post", author=self.user1)
        db.session.add(post_by_user1)
        db.session.commit()

        self._login('test1@example.com', 'password') # user1 logs in
        self.client.post(f'/like/{post_by_user1.id}', follow_redirects=True) # user1 likes their own post

        notifications_count = Notification.query.filter_by(recipient_id=self.user1.id, type='like').count()
        self.assertEqual(notifications_count, 0)
        self._logout()

    # --- Test Socket.IO Event Emission (Simplified) ---
    @patch('app.routes.socketio.emit') # Patch socketio.emit from app.routes
    def test_socketio_event_on_like(self, mock_socketio_emit):
        post_by_user1 = Post(body="User1's Post for Socket Like Test", author=self.user1)
        db.session.add(post_by_user1)
        db.session.commit()

        # User2 (actor) logs in via HTTP client and performs action
        self._login(self.user2.email, 'password')
        self.client.post(f'/like/{post_by_user1.id}', follow_redirects=True)
        self._logout()

        # Check if socketio.emit was called correctly
        emit_called_correctly = False
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.user1.id):
                payload = args[1]
                if (payload.get('type') == 'like' and
                    payload.get('actor_username') == self.user2.username and
                    payload.get('post_author_username') == self.user1.username and
                    payload.get('post_id') == post_by_user1.id):
                    emit_called_correctly = True
                    break
        self.assertTrue(emit_called_correctly, "socketio.emit for 'like' not called correctly.")

    @patch('app.routes.socketio.emit')
    def test_socketio_event_on_comment(self, mock_socketio_emit):
        post_by_user1 = Post(body="User1's Post for Socket Comment Test", author=self.user1)
        db.session.add(post_by_user1)
        db.session.commit()

        # User2 (actor) logs in and comments
        self._login(self.user2.email, 'password')
        self.client.post(f'/post/{post_by_user1.id}/comment', data={'body': 'Socket test comment'}, follow_redirects=True)
        self._logout()

        emit_called_correctly = False
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.user1.id):
                payload = args[1]
                if (payload.get('type') == 'comment' and
                    payload.get('actor_username') == self.user2.username and
                    payload.get('post_author_username') == self.user1.username and
                    payload.get('post_id') == post_by_user1.id and
                    payload.get('comment_body') == 'Socket test comment'):
                    emit_called_correctly = True
                    break
        self.assertTrue(emit_called_correctly, "socketio.emit for 'comment' not called correctly.")

    @patch('app.routes.socketio.emit')
    def test_socketio_event_on_follow(self, mock_socketio_emit):
        # User2 (actor) logs in and follows User1
        self._login(self.user2.email, 'password')
        self.client.post(f'/follow/{self.user1.username}', follow_redirects=True) # user2 follows user1
        self._logout()

        emit_called_correctly = False
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.user1.id):
                payload = args[1]
                if (payload.get('type') == 'follow' and
                    payload.get('actor_username') == self.user2.username):
                    emit_called_correctly = True
                    break
        self.assertTrue(emit_called_correctly, "socketio.emit for 'follow' not called correctly.")

    @patch('app.routes.socketio.emit') # Patching where emit is called in app.routes
    def test_socketio_notifications_cleared_on_visit(self, mock_socketio_emit):
        # This test previously used socketio_test_client to receive 'notifications_cleared'.
        # Now, it checks if the server attempts to emit it.

        # Setup: user2 likes a post by user1, so user1 gets a notification.
        post_by_user1 = Post(body="User1's Post for Notification Cleared Test", author=self.user1)
        db.session.add(post_by_user1)
        db.session.commit()

        # user2 logs in and likes user1's post
        self._login(self.user2.email, 'password')
        self.client.post(f'/like/{post_by_user1.id}', follow_redirects=True)
        self._logout() # user2 logs out

        # Ensure a 'like' notification was created for user1
        notification_for_user1 = Notification.query.filter_by(recipient_id=self.user1.id, type='like').first()
        self.assertIsNotNone(notification_for_user1, "Like notification for user1 was not created by user2's like.")
        self.assertFalse(notification_for_user1.is_read, "Notification for user1 should be unread initially.")

        # User1 logs in to visit the notifications page
        self._login(self.user1.email, 'password')
        response = self.client.get('/notifications') # This HTTP GET triggers the 'notifications_cleared' emit for user1
        self.assertEqual(response.status_code, 200)
        # No need to logout user1 immediately if we are checking their DB state next.
        # self._logout()

        # Assert that 'notifications_cleared' event was emitted to user1's room
        cleared_event_emitted = False
        for call_args_item in mock_socketio_emit.call_args_list:
            args, kwargs = call_args_item # Use different var name to avoid confusion
            if args[0] == 'notifications_cleared' and kwargs.get('room') == str(self.user1.id):
                self.assertEqual(args[1], {'message': 'All notifications marked as read.'})
                cleared_event_emitted = True
                break
        self.assertTrue(cleared_event_emitted, "'notifications_cleared' event was not emitted correctly.")

        # Verify the notification in DB is marked as read
        db.session.refresh(notification_for_user1)
        self.assertTrue(notification_for_user1.is_read, "Notification in DB was not marked as read.")
        self._logout()

# Using a smaller, more manageable set of milestones for these tests
TEST_LIKE_MILESTONES = [3, 5]

class TestLikeMilestoneNotifications(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig) # Use TestingConfig like other tests in this file

        # Patch LIKE_MILESTONES in app.routes for the duration of the tests
        self.milestones_patch = patch('app.routes.LIKE_MILESTONES', TEST_LIKE_MILESTONES)
        self.mock_milestones = self.milestones_patch.start()

        self.app_context = self.app.app_context()
        self.app_context.push()
        with self.app.app_context(): # Ensure operations are within app context
            db.create_all()

        self.client = self.app.test_client(use_cookies=True) # Ensure cookies for login session

        # Create users
        # Post author
        self.post_author = User(username='post_author', email='author@example.com')
        self.post_author.set_password('password')
        db.session.add(self.post_author)

        # Liker users
        self.liker_users = []
        # Create enough users to hit all test milestones + a few more
        for i in range(1, TEST_LIKE_MILESTONES[-1] + 3):
            liker = User(username=f'liker_user{i}', email=f'liker{i}@example.com')
            liker.set_password('password')
            self.liker_users.append(liker)
            db.session.add(liker)

        db.session.commit()

        # Create a post by post_author
        self.test_post = Post(body="Milestone Test Post", author=self.post_author)
        db.session.add(self.test_post)
        db.session.commit()

    def tearDown(self):
        with self.app.app_context(): # Ensure operations are within app context
            db.session.remove()
            db.drop_all()
        self.app_context.pop()
        self.milestones_patch.stop() # Important to stop the patch

    def _login(self, email, password='password'):
        # Simplified login using email, matching existing test style
        return self.client.post('/login', data=dict(
            email=email, # Use email for login as per existing tests
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def _like_post(self, post_id, as_user_obj):
        self._login(as_user_obj.email) # Login with email
        response = self.client.post(f'/like/{post_id}', follow_redirects=True)
        self._logout() # Ensure logout after action to isolate user sessions for likes
        return response

    @patch('app.routes.socketio.emit')
    def test_milestone_notification_creation_and_emission(self, mock_socketio_emit):
        """Test notification and emission when first milestone is reached."""
        milestone_to_hit = TEST_LIKE_MILESTONES[0] # e.g., 3
        liker_who_hit_milestone = None

        for i in range(milestone_to_hit):
            self._like_post(self.test_post.id, self.liker_users[i])
            if (i + 1) == milestone_to_hit:
                liker_who_hit_milestone = self.liker_users[i]
        self._logout() # Logout the last liker

        # Verify DB notification
        notification = Notification.query.filter_by(
            recipient_id=self.post_author.id,
            related_post_id=self.test_post.id,
            type=f'like_milestone_{milestone_to_hit}'
        ).first()
        self.assertIsNotNone(notification, f"Milestone {milestone_to_hit} notification not found in DB.")
        self.assertEqual(notification.actor_id, liker_who_hit_milestone.id)

        # Verify socketio.emit call
        milestone_emit_found = False
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.post_author.id):
                payload = args[1]
                if payload.get('type') == f'like_milestone_{milestone_to_hit}':
                    milestone_emit_found = True
                    self.assertEqual(payload['milestone_count'], milestone_to_hit)
                    self.assertEqual(payload['actor_username'], liker_who_hit_milestone.username)
                    self.assertEqual(payload['post_id'], self.test_post.id)
                    self.assertTrue(f"reached {milestone_to_hit} likes!" in payload['message'])
                    break
        self.assertTrue(milestone_emit_found, "SocketIO emit for milestone notification not found or incorrect.")

    @patch('app.routes.socketio.emit')
    def test_no_notification_if_milestone_not_reached(self, mock_socketio_emit):
        milestone_to_hit = TEST_LIKE_MILESTONES[0]
        likes_to_add = milestone_to_hit - 1

        for i in range(likes_to_add):
            self._like_post(self.test_post.id, self.liker_users[i])
        self._logout() # Logout the last liker

        notification = Notification.query.filter(
            Notification.recipient_id == self.post_author.id,
            Notification.related_post_id == self.test_post.id,
            Notification.type.startswith('like_milestone_')
        ).first()
        self.assertIsNone(notification, "Milestone notification found when it shouldn't have been.")

        for call_args in mock_socketio_emit.call_args_list:
            args, _ = call_args
            if args[0] == 'new_notification':
                payload = args[1]
                self.assertFalse(payload.get('type', '').startswith('like_milestone_'),
                                 "SocketIO emit for milestone notification found when it shouldn't exist.")

    @patch('app.routes.socketio.emit')
    def test_no_duplicate_milestone_notification_on_overshoot(self, mock_socketio_emit):
        """Test that a milestone notification is not sent again if count goes past it."""
        milestone_to_hit = TEST_LIKE_MILESTONES[0] # e.g., 3

        # Hit the milestone
        for i in range(milestone_to_hit):
            self._like_post(self.test_post.id, self.liker_users[i])

        # Clear mock calls from hitting the first milestone
        # Note: standard 'like' notifications also call mock_socketio_emit
        # We are interested in *additional* milestone notifications
        # Count calls before adding more likes
        milestone_emit_calls_before_overshoot = 0
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.post_author.id):
                payload = args[1]
                if payload.get('type') == f'like_milestone_{milestone_to_hit}':
                    milestone_emit_calls_before_overshoot +=1

        self.assertEqual(milestone_emit_calls_before_overshoot, 1, "Milestone emit should have happened once.")

        # Add one more like (takes it past the first milestone, e.g., 4th like)
        self._like_post(self.test_post.id, self.liker_users[milestone_to_hit])
        self._logout()

        # Verify no NEW DB notification for the *first* milestone
        notifications = Notification.query.filter_by(
            recipient_id=self.post_author.id,
            related_post_id=self.test_post.id,
            type=f'like_milestone_{milestone_to_hit}'
        ).all()
        self.assertEqual(len(notifications), 1, "Should only be one DB notification for the first milestone.")

        # Verify socketio.emit was not called *again* for the first milestone
        milestone_emit_calls_after_overshoot = 0
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.post_author.id):
                payload = args[1]
                if payload.get('type') == f'like_milestone_{milestone_to_hit}':
                    milestone_emit_calls_after_overshoot +=1

        self.assertEqual(milestone_emit_calls_after_overshoot, milestone_emit_calls_before_overshoot,
                         "SocketIO emit for the first milestone was found again after overshooting.")


    @patch('app.routes.socketio.emit')
    def test_multiple_milestones(self, mock_socketio_emit):
        first_milestone = TEST_LIKE_MILESTONES[0] # e.g., 3
        second_milestone = TEST_LIKE_MILESTONES[1] # e.g., 5
        liker_at_first_milestone = None
        liker_at_second_milestone = None

        # Hit the first milestone
        for i in range(first_milestone):
            self._like_post(self.test_post.id, self.liker_users[i])
            if (i + 1) == first_milestone:
                liker_at_first_milestone = self.liker_users[i]

        notification1 = Notification.query.filter_by(
            recipient_id=self.post_author.id,
            related_post_id=self.test_post.id,
            type=f'like_milestone_{first_milestone}'
        ).first()
        self.assertIsNotNone(notification1)
        self.assertEqual(notification1.actor_id, liker_at_first_milestone.id)

        # Clear mock calls for the first milestone socket event to specifically check the second one later
        # This is a bit tricky as standard 'like' notifications are also emitted.
        # We'll count the specific milestone emits.
        first_milestone_emits = 0
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.post_author.id):
                payload = args[1]
                if payload.get('type') == f'like_milestone_{first_milestone}':
                    first_milestone_emits += 1
        self.assertEqual(first_milestone_emits, 1, "First milestone SocketIO event not emitted exactly once.")


        # Continue liking to hit the second milestone
        for i in range(first_milestone, second_milestone):
            self._like_post(self.test_post.id, self.liker_users[i])
            if (i + 1) == second_milestone:
                liker_at_second_milestone = self.liker_users[i]
        self._logout() # Logout last liker

        notification2 = Notification.query.filter_by(
            recipient_id=self.post_author.id,
            related_post_id=self.test_post.id,
            type=f'like_milestone_{second_milestone}'
        ).first()
        self.assertIsNotNone(notification2)
        self.assertEqual(notification2.actor_id, liker_at_second_milestone.id)

        second_milestone_emits = 0
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.post_author.id):
                payload = args[1]
                if payload.get('type') == f'like_milestone_{second_milestone}':
                    second_milestone_emits += 1
                    self.assertEqual(payload['milestone_count'], second_milestone)
                    self.assertEqual(payload['actor_username'], liker_at_second_milestone.username)
        self.assertEqual(second_milestone_emits, 1, "Second milestone SocketIO event not emitted exactly once.")

        # Ensure the first milestone notification was not re-triggered or counted again
        total_first_milestone_emits = 0
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs = call_args
            if args[0] == 'new_notification' and kwargs.get('room') == str(self.post_author.id):
                payload = args[1]
                if payload.get('type') == f'like_milestone_{first_milestone}':
                     total_first_milestone_emits +=1
        self.assertEqual(total_first_milestone_emits, first_milestone_emits, "First milestone was re-emitted.")


if __name__ == '__main__':
    unittest.main()
