import unittest
import json
from datetime import datetime, timedelta
from app import create_app, db
from app.models import User, Post, Like, Comment # Removed Event, Notification
from config import TestingConfig

class AnalyticsTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # Create test users
        self.user1 = User(username='analytica', email='analytica@example.com')
        self.user1.set_password('pass1')
        self.user2 = User(username='beta_user', email='beta@example.com')
        self.user2.set_password('pass2')
        self.user3 = User(username='gamma_user', email='gamma@example.com')
        self.user3.set_password('pass3')

        db.session.add_all([self.user1, self.user2, self.user3])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.app.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.app.get('/logout', follow_redirects=True)

    # --- Test Cases Start Here ---

    def test_analytics_page_loads_for_logged_in_user(self):
        self._login(self.user1.email, 'pass1')
        response = self.app.get('/analytics')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My Analytics Dashboard', response.data)
        self.assertIn(bytes(self.user1.username, 'utf-8'), response.data)
        self._logout()

    def test_analytics_redirects_for_non_logged_in_user(self):
        response = self.app.get('/analytics', follow_redirects=False) # Check for 302 before redirect
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/login' in response.location)

        response_followed = self.app.get('/analytics', follow_redirects=True)
        self.assertEqual(response_followed.status_code, 200)
        self.assertIn(b'Sign In', response_followed.data) # Should be on login page

    def test_analytics_data_aggregation(self):
        # Setup data specific to user1
        # User1 follows user2
        self.user1.follow(self.user2)
        # User3 follows user1
        self.user3.follow(self.user1)
        db.session.commit()

        # Posts by user1
        post1_u1 = Post(body="User1 Post 1 - Most Liked", author=self.user1, timestamp=datetime.utcnow() - timedelta(days=3))
        post2_u1 = Post(body="User1 Post 2 - Some Likes", author=self.user1, timestamp=datetime.utcnow() - timedelta(days=2))
        post3_u1 = Post(body="User1 Post 3 - No Likes", author=self.user1, timestamp=datetime.utcnow() - timedelta(days=1))
        post4_u1 = Post(body="User1 Post 4", author=self.user1, timestamp=datetime.utcnow() - timedelta(hours=12))
        post5_u1 = Post(body="User1 Post 5", author=self.user1, timestamp=datetime.utcnow() - timedelta(hours=6))
        post6_u1 = Post(body="User1 Post 6 - Second Most Liked", author=self.user1, timestamp=datetime.utcnow() - timedelta(hours=1))

        db.session.add_all([post1_u1, post2_u1, post3_u1, post4_u1, post5_u1, post6_u1])
        db.session.commit()

        # Likes
        # Post1_u1: 3 likes (user1, user2, user3)
        like1_p1 = Like(user=self.user1, post=post1_u1)
        like2_p1 = Like(user=self.user2, post=post1_u1)
        like3_p1 = Like(user=self.user3, post=post1_u1)
        # Post2_u1: 1 like (user2)
        like1_p2 = Like(user=self.user2, post=post2_u1)
        # Post6_u1: 2 likes (user2, user3)
        like1_p6 = Like(user=self.user2, post=post6_u1)
        like2_p6 = Like(user=self.user3, post=post6_u1)

        db.session.add_all([like1_p1, like2_p1, like3_p1, like1_p2, like1_p6, like2_p6])
        db.session.commit()

        # Comments
        # Post1_u1: 2 comments
        comment1_p1 = Comment(body="Comment 1 on P1", author=self.user2, commented_post=post1_u1)
        comment2_p1 = Comment(body="Comment 2 on P1", author=self.user3, commented_post=post1_u1)
        # Post2_u1: 1 comment
        comment1_p2 = Comment(body="Comment 1 on P2", author=self.user1, commented_post=post2_u1)

        db.session.add_all([comment1_p1, comment2_p1, comment1_p2])
        db.session.commit()

        expected_total_posts = 6
        expected_likes_received = 3 + 1 + 2 # 6
        expected_comments_received = 2 + 1 # 3
        expected_follower_count = 1 # user3 follows user1
        expected_following_count = 1 # user1 follows user2

        self._login(self.user1.email, 'pass1')
        response = self.app.get('/analytics')
        self.assertEqual(response.status_code, 200)

        # Test rendered HTML for specific values (more robust than context checking)
        response_data_str = response.data.decode('utf-8')

        self.assertIn(f'<h4 class="card-title">{expected_total_posts}</h4>', response_data_str)
        self.assertIn(f'<h4 class="card-title">{expected_likes_received}</h4>', response_data_str)
        self.assertIn(f'<h4 class="card-title">{expected_comments_received}</h4>', response_data_str)
        self.assertIn(f'<h4 class="card-title">{expected_follower_count}</h4>', response_data_str)
        self.assertIn(f'<h4 class="card-title">{expected_following_count}</h4>', response_data_str)

        # Test top_posts_chart_data (passed as JSON to the template)
        # Extract the JSON string from the script block
        # This is a bit brittle if template structure changes significantly.
        chart_data_json_str = None
        for line in response_data_str.splitlines():
            if 'var topPostsDataRaw =' in line:
                chart_data_json_str = line.split('var topPostsDataRaw =')[1].split(';')[0].strip()
                break

        self.assertIsNotNone(chart_data_json_str, "topPostsDataRaw JSON not found in template")
        chart_data = json.loads(chart_data_json_str)

        self.assertEqual(len(chart_data), 5) # Top 5 posts
        # Check first post (most liked)
        self.assertEqual(chart_data[0]['value'], 3) # Likes for post1_u1
        self.assertIn(post1_u1.body[:20], chart_data[0]['label'])
        # Check second post (second most liked)
        self.assertEqual(chart_data[1]['value'], 2) # Likes for post6_u1
        self.assertIn(post6_u1.body[:20], chart_data[1]['label'])
        # Check third post
        self.assertEqual(chart_data[2]['value'], 1) # Likes for post2_u1
        self.assertIn(post2_u1.body[:20], chart_data[2]['label'])
        # Check posts with 0 likes (order among them might vary based on timestamp if stable sort is not used, but they should be last)
        zero_like_posts_in_chart = [item for item in chart_data if item['value'] == 0]
        self.assertEqual(len(zero_like_posts_in_chart), 2)


        self._logout()

if __name__ == '__main__':
    unittest.main(verbosity=2)
