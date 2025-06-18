import unittest
from app import create_app, db
from app.core.models import User, Post, Story, Group, GroupMembership, Hashtag, followers, PRIVACY_PUBLIC, PRIVACY_FOLLOWERS, PRIVACY_PRIVATE # Corrected import
from flask import url_for
from datetime import datetime, timedelta, timezone
from config import TestingConfig

class TestContentVisibilityRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create users
        self.u1 = User(username='user1', email='u1@test.com', default_post_privacy=PRIVACY_PUBLIC, default_story_privacy=PRIVACY_PUBLIC)
        self.u1.set_password('cat')
        self.u2 = User(username='user2', email='u2@test.com', default_post_privacy=PRIVACY_PUBLIC, default_story_privacy=PRIVACY_PUBLIC)
        self.u2.set_password('dog')
        self.u3 = User(username='user3', email='u3@test.com', default_post_privacy=PRIVACY_PUBLIC, default_story_privacy=PRIVACY_PUBLIC) # Another user for broader scenarios
        self.u3.set_password('fish')
        db.session.add_all([self.u1, self.u2, self.u3])
        db.session.commit()

        # u1 follows u2
        self.u1.follow(self.u2)
        db.session.commit()

        # Posts
        # u1's posts
        self.p1_u1_pub = Post(author=self.u1, body="U1 Public Post - Published", is_published=True, timestamp=datetime.now(timezone.utc) - timedelta(hours=5))
        self.p2_u1_sched = Post(author=self.u1, body="U1 Public Post - Scheduled", is_published=False, scheduled_for=datetime.now(timezone.utc) + timedelta(days=1), timestamp=datetime.now(timezone.utc) - timedelta(hours=6))
        # u2's posts (followed by u1)
        self.p3_u2_pub_public = Post(author=self.u2, body="U2 Public Post - Published", is_published=True, privacy_level=PRIVACY_PUBLIC, timestamp=datetime.now(timezone.utc) - timedelta(hours=4))
        self.p4_u2_sched_public = Post(author=self.u2, body="U2 Public Post - Scheduled", is_published=False, scheduled_for=datetime.now(timezone.utc) + timedelta(days=1), privacy_level=PRIVACY_PUBLIC, timestamp=datetime.now(timezone.utc) - timedelta(hours=3))
        self.p5_u2_pub_followers = Post(author=self.u2, body="U2 Followers Post - Published", is_published=True, privacy_level=PRIVACY_FOLLOWERS, timestamp=datetime.now(timezone.utc) - timedelta(hours=2))
        self.p6_u2_sched_followers = Post(author=self.u2, body="U2 Followers Post - Scheduled", is_published=False, scheduled_for=datetime.now(timezone.utc) + timedelta(days=1), privacy_level=PRIVACY_FOLLOWERS, timestamp=datetime.now(timezone.utc) - timedelta(hours=1))
        # u3's posts (not followed by u1)
        self.p7_u3_pub_public = Post(author=self.u3, body="U3 Public Post - Published", is_published=True, privacy_level=PRIVACY_PUBLIC, timestamp=datetime.now(timezone.utc) - timedelta(minutes=30))
        self.p8_u3_sched_public = Post(author=self.u3, body="U3 Public Post - Scheduled", is_published=False, scheduled_for=datetime.now(timezone.utc) + timedelta(days=1), privacy_level=PRIVACY_PUBLIC, timestamp=datetime.now(timezone.utc) - timedelta(minutes=20))
        self.p9_u3_pub_private = Post(author=self.u3, body="U3 Private Post - Published", is_published=True, privacy_level=PRIVACY_PRIVATE, timestamp=datetime.now(timezone.utc) - timedelta(minutes=10)) # Corrected Syntax

        db.session.add_all([
            self.p1_u1_pub, self.p2_u1_sched, self.p3_u2_pub_public, self.p4_u2_sched_public,
            self.p5_u2_pub_followers, self.p6_u2_sched_followers, self.p7_u3_pub_public,
            self.p8_u3_sched_public, self.p9_u3_pub_private
        ])
        db.session.commit()

        # Stories (need image_filename or video_filename)
        # u1's stories
        self.s1_u1_pub = Story(author=self.u1, caption="U1 Public Story - Published", is_published=True, image_filename="s1.jpg", timestamp=datetime.now(timezone.utc) - timedelta(hours=5))
        self.s2_u1_sched = Story(author=self.u1, caption="U1 Public Story - Scheduled", is_published=False, scheduled_for=datetime.now(timezone.utc) + timedelta(days=1), image_filename="s2.jpg", timestamp=datetime.now(timezone.utc) - timedelta(hours=6))
        # u2's stories
        self.s3_u2_pub = Story(author=self.u2, caption="U2 Public Story - Published", is_published=True, image_filename="s3.jpg", privacy_level=PRIVACY_PUBLIC, timestamp=datetime.now(timezone.utc) - timedelta(hours=4))
        self.s4_u2_sched = Story(author=self.u2, caption="U2 Public Story - Scheduled", is_published=False, scheduled_for=datetime.now(timezone.utc) + timedelta(days=1), image_filename="s4.jpg", privacy_level=PRIVACY_PUBLIC, timestamp=datetime.now(timezone.utc) - timedelta(hours=3))

        db.session.add_all([self.s1_u1_pub, self.s2_u1_sched, self.s3_u2_pub, self.s4_u2_sched])
        db.session.commit()
        # Manually set expires_at for published stories for testing display_stories
        self.s1_u1_pub.expires_at = self.s1_u1_pub.timestamp + timedelta(hours=24)
        self.s3_u2_pub.expires_at = self.s3_u2_pub.timestamp + timedelta(hours=24)
        db.session.commit()


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, username_attr_name, password): # e.g. "u1" for self.u1
        user_obj = getattr(self, username_attr_name)
        return self.client.post(url_for('main.login'), data=dict(
            email=user_obj.email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get(url_for('main.logout'), follow_redirects=True)

    def test_index_feed_visibility_unauthenticated(self):
        response = self.client.get(url_for('main.index'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.p3_u2_pub_public.body.encode(), response.data) # u2 public published
        self.assertIn(self.p7_u3_pub_public.body.encode(), response.data) # u3 public published
        self.assertNotIn(self.p1_u1_pub.body.encode(), response.data) # u1 (not followed by anon) unless public (which it is by default in model)
        self.assertNotIn(self.p2_u1_sched.body.encode(), response.data) # u1 scheduled
        self.assertNotIn(self.p4_u2_sched_public.body.encode(), response.data) # u2 scheduled
        self.assertNotIn(self.p5_u2_pub_followers.body.encode(), response.data) # u2 follower only
        self.assertNotIn(self.p9_u3_pub_private.body.encode(), response.data) # u3 private

    def test_index_feed_visibility_authenticated_u1(self):
        self._login('u1', 'cat')
        response = self.client.get(url_for('main.index'))
        self.assertEqual(response.status_code, 200)

        # Own posts
        self.assertIn(self.p1_u1_pub.body.encode(), response.data) # Own published
        self.assertIn(self.p2_u1_sched.body.encode(), response.data) # Own scheduled

        # Followed user (u2) posts
        self.assertIn(self.p3_u2_pub_public.body.encode(), response.data) # u2 public published
        self.assertIn(self.p5_u2_pub_followers.body.encode(), response.data) # u2 followers published
        self.assertNotIn(self.p4_u2_sched_public.body.encode(), response.data) # u2 public scheduled (not visible to others)
        self.assertNotIn(self.p6_u2_sched_followers.body.encode(), response.data) # u2 followers scheduled

        # Non-followed user (u3) posts
        self.assertIn(self.p7_u3_pub_public.body.encode(), response.data) # u3 public published (discovery)
        self.assertNotIn(self.p8_u3_sched_public.body.encode(), response.data) # u3 public scheduled
        self.assertNotIn(self.p9_u3_pub_private.body.encode(), response.data) # u3 private
        self._logout()

    def test_profile_visibility_own(self):
        self._login('u1', 'cat')
        response = self.client.get(url_for('main.profile', username=self.u1.username))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.p1_u1_pub.body.encode(), response.data) # Own published
        self.assertIn(self.p2_u1_sched.body.encode(), response.data) # Own scheduled
        self._logout()

    def test_profile_visibility_other_public(self):
        self._login('u1', 'cat') # u1 views u2's profile
        self.u2.profile_visibility = PRIVACY_PUBLIC # Ensure u2's profile is public
        db.session.commit()

        response = self.client.get(url_for('main.profile', username=self.u2.username))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.p3_u2_pub_public.body.encode(), response.data) # u2 public published
        self.assertIn(self.p5_u2_pub_followers.body.encode(), response.data) # u2 followers published (u1 follows u2)
        self.assertNotIn(self.p4_u2_sched_public.body.encode(), response.data) # u2 public scheduled (not visible)
        self.assertNotIn(self.p6_u2_sched_followers.body.encode(), response.data) # u2 followers scheduled
        self._logout()

    def test_story_feed_visibility(self):
        # Unauthenticated
        response_anon = self.client.get(url_for('main.display_stories'))
        self.assertEqual(response_anon.status_code, 302) # Redirects to login as per current setup

        # Authenticated (u1)
        self._login('u1', 'cat')
        response_u1 = self.client.get(url_for('main.display_stories'))
        self.assertEqual(response_u1.status_code, 200)
        self.assertIn(self.s1_u1_pub.caption.encode(), response_u1.data) # Own published story
        self.assertIn(self.s2_u1_sched.caption.encode(), response_u1.data) # Own scheduled story
        self.assertIn(self.s3_u2_pub.caption.encode(), response_u1.data) # Followed (u2) public published story
        self.assertNotIn(self.s4_u2_sched.caption.encode(), response_u1.data) # Followed (u2) scheduled story
        self._logout()

    def test_group_feed_visibility(self):
        # Create group and add u1 as member
        group = Group(name="Test Group", creator=self.u2)
        db.session.add(group)
        db.session.commit()
        membership = GroupMembership(user=self.u1, group=group)
        db.session.add(membership)
        db.session.commit()

        # Posts in group
        post_group_pub = Post(author=self.u2, body="Group Published Post", group_id=group.id, is_published=True, timestamp=datetime.now(timezone.utc) - timedelta(minutes=5))
        post_group_sched = Post(author=self.u2, body="Group Scheduled Post", group_id=group.id, is_published=False, scheduled_for=datetime.now(timezone.utc) + timedelta(days=1), timestamp=datetime.now(timezone.utc) - timedelta(minutes=10))
        db.session.add_all([post_group_pub, post_group_sched])
        db.session.commit()

        self._login('u1', 'cat')
        response = self.client.get(url_for('main.view_group', group_id=group.id))
        self.assertEqual(response.status_code, 200)
        self.assertIn(post_group_pub.body.encode(), response.data)
        self.assertNotIn(post_group_sched.body.encode(), response.data)
        self._logout()

    def test_hashtag_feed_visibility(self):
        # Create hashtag and posts
        tag_visible = Hashtag(tag_text="visiblecontent")
        post_ht_pub = Post(author=self.u1, body="Published #visiblecontent post", is_published=True)
        post_ht_sched = Post(author=self.u1, body="Scheduled #visiblecontent post", is_published=False, scheduled_for=datetime.now(timezone.utc) + timedelta(days=1))

        post_ht_pub.hashtags.append(tag_visible)
        post_ht_sched.hashtags.append(tag_visible)
        db.session.add_all([tag_visible, post_ht_pub, post_ht_sched])
        db.session.commit()

        response = self.client.get(url_for('main.hashtag_feed', tag_text="visiblecontent"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(post_ht_pub.body.encode(), response.data)
        self.assertNotIn(post_ht_sched.body.encode(), response.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
