import unittest
from app import create_app, db
from app.models import User, Post, Like, Comment, UserAnalytics
from flask_login import login_user, logout_user
from datetime import datetime, timedelta

class DatabaseOptimizationsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_class='config.TestingConfig')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create users
        self.user1 = User(username='userone', email='one@example.com')
        self.user1.set_password('pass1')
        self.user2 = User(username='usertwo', email='two@example.com')
        self.user2.set_password('pass2')
        self.user3 = User(username='userthree', email='three@example.com')
        self.user3.set_password('pass3')
        db.session.add_all([self.user1, self.user2, self.user3])
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_followed_posts_pagination(self):
        # User1 follows User2
        self.user1.follow(self.user2)
        db.session.commit()

        # Create posts for User1 (own) and User2 (followed)
        # Posts should be created with varying timestamps to test ordering
        for i in range(5): # User1's posts
            p = Post(body=f"User1 post {i+1}", author=self.user1, timestamp=datetime.utcnow() - timedelta(minutes=i*10))
            db.session.add(p)
        for i in range(7): # User2's posts
            p = Post(body=f"User2 post {i+1}", author=self.user2, timestamp=datetime.utcnow() - timedelta(minutes=i*5)) # User2's posts are more recent overall
            db.session.add(p)
        db.session.commit()

        # Test pagination for User1's feed
        # User1 has 5 posts, User2 has 7 posts. Total 12 posts in feed for User1.
        # Most recent should be User2's posts, then User1's.

        # Page 1, 5 items per page
        pagination1 = self.user1.followed_posts(page=1, per_page=5)
        self.assertEqual(len(pagination1.items), 5)
        self.assertTrue(pagination1.has_next)
        self.assertFalse(pagination1.has_prev)
        self.assertEqual(pagination1.total, 12)
        # Check if posts are ordered correctly (most recent first)
        self.assertTrue(all(pagination1.items[i].timestamp >= pagination1.items[i+1].timestamp for i in range(len(pagination1.items)-1)))
        # Expected: User2's posts 1-5 (as they are newer)
        self.assertEqual(pagination1.items[0].body, "User2 post 1")
        self.assertEqual(pagination1.items[4].body, "User2 post 5")


        # Page 2, 5 items per page
        pagination2 = self.user1.followed_posts(page=2, per_page=5)
        self.assertEqual(len(pagination2.items), 5)
        self.assertTrue(pagination2.has_next)
        self.assertTrue(pagination2.has_prev)
        self.assertEqual(pagination2.total, 12)
        self.assertTrue(all(pagination2.items[i].timestamp >= pagination2.items[i+1].timestamp for i in range(len(pagination2.items)-1)))
        # Expected: User2's posts 6-7, then User1's posts 1-3
        self.assertEqual(pagination2.items[0].body, "User2 post 6")
        self.assertEqual(pagination2.items[1].body, "User2 post 7")
        self.assertEqual(pagination2.items[2].body, "User1 post 1") # User1's post 1 is older than User2's post 7

        # Page 3, 5 items per page
        pagination3 = self.user1.followed_posts(page=3, per_page=5)
        self.assertEqual(len(pagination3.items), 2) # Remaining 2 posts
        self.assertFalse(pagination3.has_next)
        self.assertTrue(pagination3.has_prev)
        self.assertEqual(pagination3.total, 12)
        # Expected: User1's posts 4-5
        self.assertEqual(pagination3.items[0].body, "User1 post 4")
        self.assertEqual(pagination3.items[1].body, "User1 post 5")


    def test_user_analytics_updates_and_route(self):
        # Create posts, likes, and comments for user1
        p1_u1 = Post(body="Analytics Post 1 by User1", author=self.user1)
        p2_u1 = Post(body="Analytics Post 2 by User1", author=self.user1)
        db.session.add_all([p1_u1, p2_u1])
        db.session.commit()

        # Likes for p1_u1 (from user2 and user3)
        like1_p1 = Like(user=self.user2, post=p1_u1)
        like2_p1 = Like(user=self.user3, post=p1_u1)
        # Like for p2_u1 (from user2)
        like1_p2 = Like(user=self.user2, post=p2_u1)
        db.session.add_all([like1_p1, like2_p1, like1_p2])

        # Comments for p1_u1
        comment1_p1 = Comment(body="Comment 1 on P1", author=self.user2, commented_post=p1_u1)
        comment2_p1 = Comment(body="Comment 2 on P1", author=self.user3, commented_post=p1_u1)
        # Comment for p2_u1
        comment1_p2 = Comment(body="Comment 1 on P2", author=self.user3, commented_post=p2_u1)
        db.session.add_all([comment1_p1, comment2_p1, comment1_p2])
        db.session.commit()

        # Log in as user1 to access analytics update route (if it's restricted)
        # The current update_analytics route is @login_required
        self.client.post('/login', data={'email': self.user1.email, 'password': 'pass1'}, follow_redirects=True)

        # Trigger analytics update by calling the route
        update_response = self.client.post('/update_analytics', follow_redirects=True)
        self.assertEqual(update_response.status_code, 200) # Should redirect to analytics page
        self.assertIn(b'User analytics have been updated.', update_response.data)

        # Verify UserAnalytics table for user1
        analytics_u1 = UserAnalytics.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(analytics_u1)
        self.assertEqual(analytics_u1.total_likes_received, 3) # 2 for p1, 1 for p2
        self.assertEqual(analytics_u1.total_comments_received, 3) # 2 for p1, 1 for p2

        # Verify for user2 (should be 0 as they made no posts)
        analytics_u2 = UserAnalytics.query.filter_by(user_id=self.user2.id).first()
        self.assertIsNotNone(analytics_u2) # Entry should be created
        self.assertEqual(analytics_u2.total_likes_received, 0)
        self.assertEqual(analytics_u2.total_comments_received, 0)

        # Test accessing the /analytics route for user1
        analytics_page_response = self.client.get('/analytics')
        self.assertEqual(analytics_page_response.status_code, 200)
        self.assertIn(b'User Analytics', analytics_page_response.data)
        self.assertIn(b'Total Likes Received:</strong> 3', analytics_page_response.data)
        self.assertIn(b'Total Comments Received:</strong> 3', analytics_page_response.data)

        logout_user()

if __name__ == '__main__':
    unittest.main()
