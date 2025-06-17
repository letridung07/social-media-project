import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from app import create_app, db
from app.core.models import User, Post, Story, Notification, Mention, Group, GroupMembership # Add all relevant models
from app.core.scheduler import publish_scheduled_content # The function to test
from config import TestingConfig # Ensure TestingConfig is used

# process_mentions is called internally by scheduler logic if it's part of publish_scheduled_content now
# from app.utils.helpers import process_mentions

class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig) # Use TestingConfig
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create users
        self.u1 = User(username='sched_user1', email='su1@test.com')
        self.u1.set_password('pw')
        self.u2 = User(username='sched_user2', email='su2@test.com') # For mentions
        self.u2.set_password('pw')
        db.session.add_all([self.u1, self.u2])
        db.session.commit()

        # Create a group for group post notification testing
        self.group1 = Group(name="Scheduled Group", creator_id=self.u1.id)
        db.session.add(self.group1)
        db.session.commit()
        # Add u2 as a member of group1 to receive notification
        membership = GroupMembership(user_id=self.u2.id, group_id=self.group1.id, role='member')
        db.session.add(membership)
        db.session.commit()


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_publish_scheduled_posts(self):
        past_schedule_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        future_schedule_time = datetime.now(timezone.utc) + timedelta(days=1)

        # Post that should be published
        post_to_publish = Post(body="Post to publish now", author=self.u1,
                               scheduled_for=past_schedule_time, is_published=False)
        # Post that should remain scheduled
        post_not_due = Post(body="Post for future", author=self.u1,
                            scheduled_for=future_schedule_time, is_published=False)
        # Post already published
        post_already_published = Post(body="Already out", author=self.u1,
                                      scheduled_for=past_schedule_time, is_published=True)

        db.session.add_all([post_to_publish, post_not_due, post_already_published])
        db.session.commit()

        # Call the scheduler task function directly
        publish_scheduled_content()

        # Verify post_to_publish is now published
        # It's better to query by ID as other attributes might change or be non-unique
        retrieved_published_post = Post.query.get(post_to_publish.id)
        self.assertTrue(retrieved_published_post.is_published)

        # Verify post_not_due is still not published
        retrieved_not_due_post = Post.query.get(post_not_due.id)
        self.assertFalse(retrieved_not_due_post.is_published)

        # Verify post_already_published remains published
        retrieved_already_published_post = Post.query.get(post_already_published.id)
        self.assertTrue(retrieved_already_published_post.is_published)

    def test_publish_scheduled_stories(self):
        now = datetime.now(timezone.utc) # Capture time before scheduler runs
        past_schedule_time = now - timedelta(minutes=10)

        story_to_publish = Story(caption="Story to publish", author=self.u1, image_filename="s1.jpg",
                                 scheduled_for=past_schedule_time, is_published=False)
        db.session.add(story_to_publish)
        db.session.commit()

        # Call the task
        publish_scheduled_content()

        retrieved_story = Story.query.get(story_to_publish.id)
        self.assertTrue(retrieved_story.is_published)
        self.assertIsNotNone(retrieved_story.expires_at)
        # Check that expires_at is approx 24 hours from 'now' (the mocked publish time)
        expected_expires_at = now + timedelta(hours=24)
        self.assertAlmostEqual(retrieved_story.expires_at, expected_expires_at, delta=timedelta(seconds=15)) # Increased delta for scheduler run variance slightly

    @patch('app.scheduler.datetime') # Mock datetime within the scheduler module
    def test_publish_scheduled_stories_mocked_time(self, mock_dt):
        # Set a fixed "current time" for the test
        fixed_now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = fixed_now # Mock datetime.now(timezone.utc)
        # If timedelta is also used from datetime in the mocked module, it should be fine
        # or mock it too if it causes issues (mock_dt.timedelta = timedelta)

        schedule_time_for_story = fixed_now - timedelta(hours=1) # Story scheduled an hour ago relative to fixed_now

        story_to_publish = Story(caption="Mock time story", author=self.u1, image_filename="s_mock.jpg",
                                 scheduled_for=schedule_time_for_story, is_published=False)
        db.session.add(story_to_publish)
        db.session.commit()

        publish_scheduled_content()

        retrieved_story = Story.query.get(story_to_publish.id)
        self.assertTrue(retrieved_story.is_published)
        self.assertIsNotNone(retrieved_story.expires_at)
        expected_expires_at = fixed_now + timedelta(hours=24)
        self.assertEqual(retrieved_story.expires_at, expected_expires_at)


    def test_notifications_for_scheduled_post_mention(self):
        # Post with a mention, scheduled for past
        mention_schedule_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        post_with_mention = Post(
            body=f"Hello @{self.u2.username}, this is a scheduled mention!",
            author=self.u1,
            scheduled_for=mention_schedule_time,
            is_published=False
        )
        db.session.add(post_with_mention)
        db.session.commit()

        # Ensure no notifications exist yet
        notifs_before = Notification.query.filter_by(recipient_id=self.u2.id).all()
        self.assertEqual(len(notifs_before), 0)

        # Call scheduler task
        publish_scheduled_content()

        # Verify post is published
        db.session.refresh(post_with_mention) # Refresh state from DB
        self.assertTrue(post_with_mention.is_published)

        # Verify notification was created for u2
        mention_notif = Notification.query.filter_by(recipient_id=self.u2.id, type='mention').first()
        self.assertIsNotNone(mention_notif)
        self.assertEqual(mention_notif.actor_id, self.u1.id)
        self.assertEqual(mention_notif.related_post_id, post_with_mention.id)

        # Check that a Mention object was created
        mention_obj = Mention.query.filter_by(user_id=self.u2.id, post_id=post_with_mention.id).first()
        self.assertIsNotNone(mention_obj)
        self.assertEqual(mention_notif.related_mention_id, mention_obj.id)

    def test_notifications_for_scheduled_group_post(self):
        schedule_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        group_post = Post(
            body="Scheduled post for the group!",
            author=self.u1,
            group_id=self.group1.id,
            scheduled_for=schedule_time,
            is_published=False
        )
        db.session.add(group_post)
        db.session.commit()

        # No notifications for u2 (group member) yet
        notifs_before = Notification.query.filter_by(recipient_id=self.u2.id, type='new_group_post').all()
        self.assertEqual(len(notifs_before), 0)

        publish_scheduled_content()

        db.session.refresh(group_post)
        self.assertTrue(group_post.is_published)

        # Notification for u2 (group member) should exist
        group_post_notif = Notification.query.filter_by(recipient_id=self.u2.id, type='new_group_post').first()
        self.assertIsNotNone(group_post_notif)
        self.assertEqual(group_post_notif.actor_id, self.u1.id)
        self.assertEqual(group_post_notif.related_post_id, group_post.id)
        self.assertEqual(group_post_notif.related_group_id, self.group1.id)

if __name__ == '__main__':
    unittest.main(verbosity=2)
