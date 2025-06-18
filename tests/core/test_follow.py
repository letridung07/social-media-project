# tests/test_follow.py
import unittest
from app import create_app, db
from app.core.models import User, Post # Corrected import path
from config import TestingConfig
from datetime import datetime, timedelta

class FollowSystemCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create test users
        self.u1 = User(username='john', email='john@example.com')
        self.u1.set_password('cat')
        self.u2 = User(username='susan', email='susan@example.com')
        self.u2.set_password('dog')
        self.u3 = User(username='david', email='david@example.com')
        self.u3.set_password('mouse')
        db.session.add_all([self.u1, self.u2, self.u3])
        db.session.commit()

        # Create some posts
        self.p1_u1 = Post(body="John's first post", author=self.u1, timestamp=datetime.utcnow() + timedelta(seconds=1))
        self.p2_u2 = Post(body="Susan's first post", author=self.u2, timestamp=datetime.utcnow() + timedelta(seconds=2))
        self.p3_u3 = Post(body="David's first post", author=self.u3, timestamp=datetime.utcnow() + timedelta(seconds=3))
        db.session.add_all([self.p1_u1, self.p2_u2, self.p3_u3])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.client.post('/login', data=dict(email=email, password=password), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_follow_unfollow(self):
        # John logs in
        self._login(self.u1.email, 'cat')

        # John follows Susan
        response = self.client.post(f'/follow/{self.u2.username}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You are now following susan!', response.data)
        self.assertTrue(self.u1.is_following(self.u2))
        self.assertFalse(self.u2.is_following(self.u1)) # Susan is not following John yet
        self.assertEqual(self.u1.followed.count(), 1)
        self.assertEqual(self.u1.followed.first().username, 'susan')
        self.assertEqual(self.u2.followers.count(), 1)
        self.assertEqual(self.u2.followers.first().username, 'john')

        # John tries to follow Susan again (should have no effect)
        response = self.client.post(f'/follow/{self.u2.username}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You are already following susan.', response.data)

        # John unfollows Susan
        response = self.client.post(f'/unfollow/{self.u2.username}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You have unfollowed susan.', response.data)
        self.assertFalse(self.u1.is_following(self.u2))
        self.assertEqual(self.u1.followed.count(), 0)
        self.assertEqual(self.u2.followers.count(), 0)

        self._logout()

    def test_follow_requires_login(self):
        response = self.client.post(f'/follow/{self.u2.username}', follow_redirects=True)
        self.assertTrue(response.request.path.startswith('/login'))
        self.assertFalse(self.u1.is_following(self.u2))

        response = self.client.post(f'/unfollow/{self.u2.username}', follow_redirects=True)
        self.assertTrue(response.request.path.startswith('/login'))

    def test_cannot_follow_self(self):
        self._login(self.u1.email, 'cat')
        response = self.client.post(f'/follow/{self.u1.username}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You cannot follow yourself!', response.data)
        self.assertFalse(self.u1.is_following(self.u1))
        self._logout()

    def test_feed_shows_followed_posts(self):
        # John logs in and follows Susan
        self._login(self.u1.email, 'cat')
        self.client.post(f'/follow/{self.u2.username}', follow_redirects=True) # John follows Susan

        # John also follows David
        self.client.post(f'/follow/{self.u3.username}', follow_redirects=True) # John follows David

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

        # Check for posts: John's own, Susan's, and David's
        self.assertIn(b"John&#39;s first post", response.data) # HTML escaped
        self.assertIn(b"Susan&#39;s first post", response.data) # HTML escaped
        self.assertIn(b"David&#39;s first post", response.data) # HTML escaped

        # Susan logs in (she is not following anyone)
        self._logout()
        self._login(self.u2.email, 'dog')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Susan&#39;s first post", response.data) # HTML escaped, Only her own post
        self.assertNotIn(b"John&#39;s first post", response.data)
        self.assertNotIn(b"David&#39;s first post", response.data)

        self._logout()

    def test_guest_feed_shows_all_posts(self):
        # No one is logged in
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"John&#39;s first post", response.data) # HTML escaped
        self.assertIn(b"Susan&#39;s first post", response.data) # HTML escaped
        self.assertIn(b"David&#39;s first post", response.data) # HTML escaped

if __name__ == '__main__':
    unittest.main(verbosity=2)
