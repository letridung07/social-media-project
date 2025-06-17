# tests/test_engagement.py
import unittest
from app import create_app, db
from app.models import User, Post, Like, Comment
from config import TestingConfig
from datetime import datetime, timedelta

class EngagementSystemCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create test users
        self.u1 = User(username='user1', email='user1@example.com')
        self.u1.set_password('pass1')
        self.u2 = User(username='user2', email='user2@example.com')
        self.u2.set_password('pass2')
        db.session.add_all([self.u1, self.u2])
        db.session.commit()

        # Create a test post by user1
        self.post1 = Post(body="User1's test post", author=self.u1, timestamp=datetime.utcnow())
        db.session.add(self.post1)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.client.post('/login', data=dict(email=email, password=password), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # --- Like Tests ---
    def test_like_unlike_post(self):
        self._login(self.u2.email, 'pass2') # user2 logs in
        self.client.post(f'/follow/{self.u1.username}', follow_redirects=True) # user2 follows user1

        # user2 likes post1
        response = self.client.post(f'/like/{self.post1.id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You liked the post!', response.data)

        like = Like.query.filter_by(user_id=self.u2.id, post_id=self.post1.id).first()
        self.assertIsNotNone(like)
        self.assertEqual(self.post1.like_count(), 1)
        self.assertTrue(self.post1.is_liked_by(self.u2))

        # Check like button now says "Unlike" and count is displayed
        response_post_page = self.client.get('/') # Assuming post is on index
        self.assertIn(b'1 like', response_post_page.data) # Check count
        self.assertIn(f'action="/unlike/{self.post1.id}"'.encode(), response_post_page.data) # Check for unlike form

        # user2 tries to like again (should fail gracefully)
        response = self.client.post(f'/like/{self.post1.id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You have already liked this post.', response.data)
        self.assertEqual(self.post1.like_count(), 1) # Count should not change

        # user2 unlikes post1
        response = self.client.post(f'/unlike/{self.post1.id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You unliked the post.', response.data)
        self.assertIsNone(Like.query.filter_by(user_id=self.u2.id, post_id=self.post1.id).first())
        self.assertEqual(self.post1.like_count(), 0)
        self.assertFalse(self.post1.is_liked_by(self.u2))

        self._logout()

    def test_like_requires_login(self):
        response = self.client.post(f'/like/{self.post1.id}', follow_redirects=True)
        self.assertTrue(response.request.path.startswith('/login'))

        response = self.client.post(f'/unlike/{self.post1.id}', follow_redirects=True)
        self.assertTrue(response.request.path.startswith('/login'))
        self.assertEqual(self.post1.like_count(), 0)

    # --- Comment Tests ---
    def test_add_comment(self):
        self._login(self.u2.email, 'pass2') # user2 logs in
        self.client.post(f'/follow/{self.u1.username}', follow_redirects=True) # user2 follows user1
        comment_text = "This is a test comment from user2!"

        response = self.client.post(f'/post/{self.post1.id}/comment', data={
            'body': comment_text
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your comment has been added!', response.data)

        comment = Comment.query.filter_by(post_id=self.post1.id, user_id=self.u2.id).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.body, comment_text)
        self.assertEqual(comment.author.username, self.u2.username)
        self.assertEqual(comment.commented_post.id, self.post1.id)

        # Check if comment is displayed on the page (e.g., index)
        response_page = self.client.get('/')
        self.assertIn(comment_text.encode(), response_page.data)
        self.assertIn(self.u2.username.encode(), response_page.data) # Comment author

        self._logout()

    def test_add_empty_comment_fails(self):
        self._login(self.u2.email, 'pass2')
        response = self.client.post(f'/post/{self.post1.id}/comment', data={'body': ''}, follow_redirects=True)
        self.assertEqual(response.status_code, 200) # The add_comment route redirects, so status is 200
        # Check for the flash message content
        # The exact flash message depends on how form.errors is formatted in the route
        self.assertIn(b'Error adding comment: Body: This field is required.', response.data)
        self.assertEqual(Comment.query.count(), 0)
        self._logout()

    def test_comment_requires_login(self):
        response = self.client.post(f'/post/{self.post1.id}/comment', data={'body': 'Trying to comment anonymously'}, follow_redirects=True)
        self.assertTrue(response.request.path.startswith('/login'))
        self.assertEqual(Comment.query.count(), 0)

    def test_comment_order_and_display(self):
        # user2 adds first comment
        self._login(self.u2.email, 'pass2')
        comment1_text = "User2: First comment!"
        self.client.post(f'/post/{self.post1.id}/comment', data={'body': comment1_text}, follow_redirects=True)

        # Manually adjust timestamp of the first comment to ensure it's older
        c1 = Comment.query.filter_by(body=comment1_text).first()
        self.assertIsNotNone(c1, "First comment not found in DB for timestamp adjustment")
        c1.timestamp = datetime.utcnow() - timedelta(seconds=10)
        db.session.commit()
        self._logout()


        # user1 adds second comment
        self._login(self.u1.email, 'pass1')
        comment2_text = "User1: Second comment, replying to user2!"
        self.client.post(f'/post/{self.post1.id}/comment', data={'body': comment2_text}, follow_redirects=True)
        self._logout()

        response = self.client.get('/') # Or wherever the post is displayed

        content_data = response.data.decode()
        pos_comment1 = content_data.find(comment1_text)
        pos_comment2 = content_data.find(comment2_text)

        self.assertTrue(pos_comment1 != -1, f"Comment 1 '{comment1_text}' not found in response: {content_data}")
        self.assertTrue(pos_comment2 != -1, f"Comment 2 '{comment2_text}' not found in response: {content_data}")
        self.assertTrue(pos_comment1 < pos_comment2, f"Comments are not in chronological (ascending) order. Pos1: {pos_comment1}, Pos2: {pos_comment2}")

        # Verify authors displayed
        self.assertIn(self.u1.username, content_data)
        self.assertIn(self.u2.username, content_data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
