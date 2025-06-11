import unittest
import os
import io
from flask_login import current_user
from flask_socketio import SocketIOTestClient

from app import create_app, db, socketio
from app.models import User, Post, Notification, Comment, Like
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
    def test_socketio_event_on_like(self):
        post_by_user1 = Post(body="User1's Post for Socket Like Test", author=self.user1)
        db.session.add(post_by_user1)
        db.session.commit()

        with self.client:
            # User1 (recipient) logs in
            # User1 (recipient) logs in
            self._login(self.user1.email, 'password')
            self.client.get('/') # Ensure session is active
            self.socketio_test_client.connect(namespace='/')
            # User1 explicitly joins their notification room
            self.socketio_test_client.emit('join_notification_room', namespace='/')
            self.socketio_test_client.get_received(namespace='/') # Clear any connect-time/join messages

            # User2 (actor) logs in via HTTP client and performs action
            self._logout()
            self._login(self.user2.email, 'password')
            self.client.post(f'/like/{post_by_user1.id}', follow_redirects=True)

        # Check events received by user1's socketio_test_client
        received = self.socketio_test_client.get_received(namespace='/')
        new_notifs = [r for r in received if r['name'] == 'new_notification']
        self.assertGreater(len(new_notifs), 0, "No 'new_notification' event received after like.")
        if len(new_notifs) > 0: # Added to prevent index error if new_notifs is empty
            self.assertEqual(new_notifs[0]['args'][0]['type'], 'like')
            self.assertEqual(new_notifs[0]['args'][0]['actor_username'], self.user2.username)
        self._logout()

    def test_socketio_event_on_comment(self):
        post_by_user1 = Post(body="User1's Post for Socket Comment Test", author=self.user1)
        db.session.add(post_by_user1)
        db.session.commit()

        with self.client:
            self._login(self.user1.email, 'password')
            self.client.get('/') # Ensure session
            self.socketio_test_client.connect(namespace='/')
            self.socketio_test_client.emit('join_notification_room', namespace='/')
            self.socketio_test_client.get_received(namespace='/')

            self._logout()
            self._login(self.user2.email, 'password')
            self.client.post(f'/post/{post_by_user1.id}/comment', data={'body': 'Socket test comment'}, follow_redirects=True)

        received = self.socketio_test_client.get_received(namespace='/')
        self.assertGreater(len(received), 0)
        new_notifs = [r for r in received if r['name'] == 'new_notification']
        self.assertGreater(len(new_notifs), 0)
        self.assertEqual(new_notifs[0]['args'][0]['type'], 'comment')
        self.assertEqual(new_notifs[0]['args'][0]['actor_username'], self.user2.username)
        self.assertEqual(new_notifs[0]['args'][0]['comment_body'], 'Socket test comment')
        self._logout()

    def test_socketio_event_on_follow(self):
        with self.client:
            self._login(self.user1.email, 'password') # user1 is recipient
            self.client.get('/') # Ensure session
            self.socketio_test_client.connect(namespace='/')
            self.socketio_test_client.emit('join_notification_room', namespace='/')
            self.socketio_test_client.get_received(namespace='/')

            self._logout() # user1 logs out from flask client
            self._login(self.user2.email, 'password') # user2 (actor) logs in
            self.client.post(f'/follow/{self.user1.username}', follow_redirects=True) # user2 follows user1

        received = self.socketio_test_client.get_received(namespace='/')
        self.assertGreater(len(received), 0)
        new_notifs = [r for r in received if r['name'] == 'new_notification']
        self.assertGreater(len(new_notifs), 0)
        self.assertEqual(new_notifs[0]['args'][0]['type'], 'follow')
        self.assertEqual(new_notifs[0]['args'][0]['actor_username'], self.user2.username)
        self._logout()

if __name__ == '__main__':
    unittest.main()
