import unittest
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from flask import url_for, get_flashed_messages # get_flashed_messages can be useful
from app import create_app, db, cache
from app.models import User, Post, Like, Comment, Hashtag, Group, GroupMembership, HistoricalAnalytics, UserAnalytics, post_hashtags # Added new models
from config import TestingConfig # Use TestingConfig as in existing file

class AnalyticsTestCase(unittest.TestCase): # Use existing class name
    def setUp(self):
        self.app = create_app(TestingConfig) # Use TestingConfig
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()
        cache.clear() # Clear cache before each test

        # Keep existing user creation for compatibility or adapt tests
        self.user1 = self._create_user(username='analytica', email='analytica@example.com', password='pass1')
        self.user2 = self._create_user(username='beta_user', email='beta@example.com', password='pass2')
        self.user3 = self._create_user(username='gamma_user', email='gamma@example.com', password='pass3')


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        cache.clear() # Clear cache after each test

    # Helper methods from my generated tests + existing login/logout
    def _login(self, email_or_username, password): # Allow login by username too if User model supports it, or stick to email
        user = User.query.filter((User.email == email_or_username) | (User.username == email_or_username)).first()
        if not user:
            raise ValueError(f"User {email_or_username} not found for login")
        return self.client.post(url_for('main.login'), data=dict(
            email=user.email, # Login form likely uses email
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get(url_for('main.logout'), follow_redirects=True)

    def _create_user(self, username="testuser", email="test@example.com", password="password"):
        # Check if user already exists by username or email to avoid conflicts with setUp users
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            return existing_user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    def _create_post(self, user_id, body="Test post body", group_id=None, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        post = Post(user_id=user_id, body=body, group_id=group_id, timestamp=timestamp)
        db.session.add(post)
        db.session.commit()
        return post

    def _create_like(self, user_id, post_id):
        like = Like(user_id=user_id, post_id=post_id)
        db.session.add(like)
        db.session.commit()
        return like

    def _create_comment(self, user_id, post_id, body="Test comment"):
        comment = Comment(user_id=user_id, post_id=post_id, body=body)
        db.session.add(comment)
        db.session.commit()
        return comment

    def _create_hashtag(self, tag_text):
        ht = Hashtag.query.filter_by(tag_text=tag_text.lower()).first()
        if not ht:
            ht = Hashtag(tag_text=tag_text.lower())
            db.session.add(ht)
            db.session.commit()
        return ht

    def _add_hashtag_to_post(self, post, hashtag):
        if hashtag not in post.hashtags:
            post.hashtags.append(hashtag)
            db.session.commit()

    def _create_group(self, creator_id, name="Test Group", description="A group for testing"):
        group = Group(name=name, description=description, creator_id=creator_id)
        db.session.add(group)
        db.session.flush() # Get group.id
        membership = GroupMembership(user_id=creator_id, group_id=group.id, role='admin')
        db.session.add(membership)
        db.session.commit()
        return group

    def _create_historical_analytics(self, user_id, timestamp, likes=0, comments=0, followers=0):
        record = HistoricalAnalytics(
            user_id=user_id, timestamp=timestamp,
            likes_received=likes, comments_received=comments, followers_count=followers
        )
        db.session.add(record)
        db.session.commit()
        return record

    def _create_user_analytics(self, user_id, likes=0, comments=0, posts=0): # Added posts for completeness
        ua = UserAnalytics.query.filter_by(user_id=user_id).first()
        if not ua:
            ua = UserAnalytics(user_id=user_id)
            db.session.add(ua)
        ua.total_likes_received = likes
        ua.total_comments_received = comments
        # Note: UserAnalytics model in the original problem doesn't have total_posts.
        # If it did, you'd set it here. Total posts is derived dynamically in the route.
        db.session.commit()
        return ua

    # --- Existing Tests (adapted or kept) ---
    def test_analytics_page_loads_for_logged_in_user(self):
        self._login(self.user1.email, 'pass1')
        response = self.client.get(url_for('main.analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My Analytics Dashboard', response.data)
        self.assertIn(bytes(self.user1.username, 'utf-8'), response.data)
        self._logout()

    def test_analytics_redirects_for_non_logged_in_user(self):
        response = self.client.get(url_for('main.analytics'), follow_redirects=False)
        self.assertEqual(response.status_code, 302) # Should redirect
        self.assertTrue('/login' in response.location)

        response_followed = self.client.get(url_for('main.analytics'), follow_redirects=True)
        self.assertEqual(response_followed.status_code, 200) # Lands on login page
        self.assertIn(b'Sign In', response_followed.data)


    # --- New Test Cases ---
    def test_create_historical_analytics_record(self):
        user = self._create_user(username="hist_user_modeltest")
        now = datetime.now(timezone.utc)
        record = self._create_historical_analytics(user.id, now, likes=10, comments=5, followers=20)

        self.assertIsNotNone(record.id)
        self.assertEqual(record.user_id, user.id)
        self.assertEqual(record.likes_received, 10)
        # ... (rest of asserts from my generated test)
        self.assertTrue(abs(record.timestamp - now) < timedelta(seconds=1))
        self.assertIn(record, user.historical_analytics.all())


    def test_get_historical_engagement_util(self): # Renamed to avoid clash if a route test is named similarly
        from app.utils import get_historical_engagement
        user = self.user1 # Use one of the pre-created users
        now = datetime.now(timezone.utc)

        self._create_historical_analytics(user.id, now - timedelta(days=3), likes=1)
        self._create_historical_analytics(user.id, now - timedelta(days=10), likes=2)
        self._create_historical_analytics(user.id, now - timedelta(days=40), likes=3)

        data_7days = get_historical_engagement(user.id, '7days')
        self.assertEqual(len(data_7days), 1)
        self.assertEqual(data_7days[0].likes_received, 1)

        data_30days = get_historical_engagement(user.id, '30days')
        self.assertEqual(len(data_30days), 2)

        # ... (rest of asserts from my generated test for get_historical_engagement)
        custom_start = now - timedelta(days=15)
        custom_end = now - timedelta(days=5)
        data_custom = get_historical_engagement(user.id, 'custom', custom_start_date=custom_start, custom_end_date=custom_end)
        self.assertEqual(len(data_custom), 1)
        self.assertEqual(data_custom[0].likes_received, 2)


    def test_get_top_performing_hashtags_util(self): # Renamed
        from app.utils import get_top_performing_hashtags
        user = self.user1

        ht1 = self._create_hashtag("popular")
        ht2 = self._create_hashtag("average")

        post1 = self._create_post(user.id, body="#popular #average")
        self._add_hashtag_to_post(post1, ht1)
        self._add_hashtag_to_post(post1, ht2)
        self._create_like(self.user2.id, post1.id) # Liked by user2
        self._create_comment(self.user3.id, post1.id, "Great post!") # Comment by user3
        # ht1: 1 like, 1 comment -> engagement 2
        # ht2: 1 like, 1 comment -> engagement 2

        post2 = self._create_post(user.id, body="More #popular stuff")
        self._add_hashtag_to_post(post2, ht1)
        self._create_like(self.user2.id, post2.id)
        self._create_like(self.user3.id, post2.id)
        # ht1: now has 1+2=3 likes, 1 comment -> engagement 4

        top_hashtags = get_top_performing_hashtags(user.id, limit=2)
        self.assertEqual(len(top_hashtags), 2)
        self.assertEqual(top_hashtags[0]['tag_text'], "popular")
        self.assertEqual(top_hashtags[0]['engagement'], 4)
        self.assertEqual(top_hashtags[0]['likes'], 3)
        self.assertEqual(top_hashtags[0]['comments'], 1)

        self.assertEqual(top_hashtags[1]['tag_text'], "average")
        self.assertEqual(top_hashtags[1]['engagement'], 2)
        self.assertEqual(top_hashtags[1]['likes'], 1)
        self.assertEqual(top_hashtags[1]['comments'], 1)

    def test_get_top_performing_groups_util(self): # Renamed
        from app.utils import get_top_performing_groups
        user = self.user1

        group1 = self._create_group(user.id, name="Active Group Util") # Unique name
        group2 = self._create_group(user.id, name="Quiet Group Util")

        post_g1 = self._create_post(user.id, body="Post in Active Group", group_id=group1.id)
        self._create_like(self.user2.id, post_g1.id)
        self._create_comment(self.user3.id, post_g1.id, "Nice group post")
        # group1: 1 like, 1 comment -> engagement 2

        post_g2 = self._create_post(user.id, body="Post in Quiet Group", group_id=group2.id)
        # No likes/comments on this post for this group from user1's posts

        top_groups = get_top_performing_groups(user.id, limit=2)
        self.assertEqual(len(top_groups), 1) # Only Active Group should appear
        self.assertEqual(top_groups[0]['group_name'], "Active Group Util")
        self.assertEqual(top_groups[0]['engagement'], 2)

    def test_analytics_dashboard_route_new_features(self): # New test for /analytics
        self._login(self.user1.email, 'pass1')

        # Setup data for user1
        now = datetime.now(timezone.utc)
        self._create_user_analytics(self.user1.id, likes=150, comments=75)
        self._create_historical_analytics(self.user1.id, now - timedelta(days=1), likes=10, comments=5, followers=20)
        self._create_historical_analytics(self.user1.id, now - timedelta(days=2), likes=8, comments=3, followers=18)

        ht_top = self._create_hashtag("topone")
        post_for_ht = self._create_post(self.user1.id, body="#topone content")
        self._add_hashtag_to_post(post_for_ht, ht_top)
        self._create_like(self.user2.id, post_for_ht.id)

        group_top = self._create_group(self.user1.id, name="Top Test Group")
        post_for_group = self._create_post(self.user1.id, body="Content for top group", group_id=group_top.id)
        self._create_comment(self.user2.id, post_for_group.id, "A comment")


        response = self.client.get(url_for('main.analytics', period='7days'))
        self.assertEqual(response.status_code, 200)
        response_data_str = response.data.decode('utf-8')

        self.assertIn(b"My Analytics Dashboard", response.data)
        self.assertIn(bytes(self.user1.username, 'utf-8'), response.data)
        self.assertIn(b"Historical Engagement Trends", response.data)
        self.assertIn(b"value=\"7days\" selected", response.data) # Check period selector

        # Check for presence of chart data JSON (existence and basic format)
        self.assertIn("var historicalLabels =", response_data_str)
        self.assertIn("var likesData =", response_data_str)
        self.assertIn("var commentsData =", response_data_str)
        self.assertIn("var followersData =", response_data_str)

        # Check for top hashtags section
        self.assertIn(b"Top Performing Hashtags", response.data)
        self.assertIn(b"#topone", response.data) # Check if our hashtag is rendered

        # Check for top groups section
        self.assertIn(b"Top Performing Groups", response.data)
        self.assertIn(b"Top Test Group", response.data) # Check if our group is rendered

        # Check summary stats (confirming they are still there and using correct values)
        self.assertIn(f'<h4 class="card-title">150</h4>', response_data_str) # Likes from UserAnalytics
        self.assertIn(f'<h4 class="card-title">75</h4>', response_data_str)  # Comments from UserAnalytics

        # Test cache (make another request, should be faster if cache works, but hard to assert speed)
        # Instead, we can check if a specific header is added by Flask-Caching, or by modifying data
        # and seeing if old data is served (if within timeout). For now, just ensuring it loads.
        response_cached = self.client.get(url_for('main.analytics', period='7days'))
        self.assertEqual(response_cached.status_code, 200)


    def test_analytics_export_route(self):
        self._login(self.user1.email, 'pass1')

        # Setup data for user1
        self._create_user_analytics(self.user1.id, likes=200, comments=100)
        self._create_post(self.user1.id, body="Exportable post main")
        now = datetime.now(timezone.utc)
        self._create_historical_analytics(self.user1.id, now - timedelta(days=5), likes=20, comments=10, followers=50)

        ht_export_csv = self._create_hashtag("csvexportable")
        post_for_ht_csv = self._create_post(self.user1.id, body="#csvexportable content")
        self._add_hashtag_to_post(post_for_ht_csv, ht_export_csv)
        self._create_like(self.user2.id, post_for_ht_csv.id)

        group_export_csv = self._create_group(self.user1.id, name="CSV Export Group")
        post_for_group_csv = self._create_post(self.user1.id, body="Content for CSV export group", group_id=group_export_csv.id)
        self._create_comment(self.user2.id, post_for_group_csv.id, "CSV comment")


        response = self.client.get(url_for('main.analytics_export', period='all'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/csv')
        self.assertIn(f"attachment; filename=analytics_export_{self.user1.username}_", response.headers["Content-Disposition"])
        self.assertIn(".csv", response.headers["Content-Disposition"])

        csv_data_string = response.data.decode('utf-8')
        csv_reader = csv.reader(io.StringIO(csv_data_string))
        csv_content = list(csv_reader)

        self.assertIn(["Summary Statistics"], csv_content)
        self.assertTrue(any("Total Likes Received" in row and "200" in row for row in csv_content))
        self.assertIn(["Historical Engagement Data"], csv_content)
        self.assertTrue(any("20" in row and "10" in row and "50" in row for row in csv_content if len(row) == 4 and row[0] != "Date")) # Check historical data values
        self.assertIn(["Top Performing Hashtags"], csv_content)
        self.assertTrue(any("csvexportable" in row for row in csv_content))
        self.assertIn(["Top Performing Groups"], csv_content)
        self.assertTrue(any("CSV Export Group" in row for row in csv_content))

if __name__ == '__main__':
    unittest.main(verbosity=2)
