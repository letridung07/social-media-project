# tests/test_posts.py
import unittest
from app import create_app, db
from app.models import User, Post
from config import TestingConfig # Using TestingConfig for tests
from datetime import datetime, timedelta

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

    def tearDown(self):
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

    def test_create_post(self):
        # Log in user1
        self._login('john@example.com', 'cat')

        # Attempt to create a new post
        response = self.client.post('/create_post', data={
            'body': 'This is a test post from John!'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to index

        # Check if the post is in the database
        post = Post.query.filter_by(body='This is a test post from John!').first()
        self.assertIsNotNone(post)
        self.assertEqual(post.author.username, 'john')

        # Check if the post appears on the index page
        response_index = self.client.get('/')
        self.assertIn(b'This is a test post from John!', response_index.data)
        self.assertIn(b'john', response_index.data) # Author's name

        # Check if the post appears on the user's profile page
        response_profile = self.client.get(f'/user/{self.user1.username}')
        self.assertIn(b'This is a test post from John!', response_profile.data)

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
        self.assertIn(b'Post by Susan', response_index.data)
        self.assertIn(b'john', response_index.data) # Author username
        self.assertIn(b'susan', response_index.data) # Author username
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

if __name__ == '__main__':
    unittest.main(verbosity=2)
