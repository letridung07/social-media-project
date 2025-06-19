import unittest
from unittest.mock import patch, MagicMock
from app import create_app, db, socketio as app_socketio # Import app_socketio for mocking
from app.core.models import User, Quest, UserQuestProgress, Badge, VirtualGood, UserPoints, ActivityLog, Notification, Post, MediaItem
from app.utils.quest_utils import seed_quests, update_quest_progress
from app.utils.gamification_utils import seed_badges # To ensure badges for rewards exist
from config import TestingConfig
from datetime import datetime, timedelta, timezone

class TestQuestsSystem(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create a test user
        self.user1 = User(username='testuser1', email='test1@example.com')
        self.user1.set_password('password')
        db.session.add(self.user1)

        self.user2 = User(username='testuser2', email='test2@example.com')
        self.user2.set_password('password')
        db.session.add(self.user2)

        db.session.commit()

        # Seed initial badges that might be used as rewards
        seed_badges()

        # Create a sample badge and virtual good for quest rewards if not seeded by name
        self.sample_badge = Badge.query.filter_by(criteria_key='photographer').first()
        if not self.sample_badge:
            self.sample_badge = Badge(name="Test Reward Badge", description="A badge for testing quest rewards.", criteria_key="test_reward_badge")
            db.session.add(self.sample_badge)
            db.session.commit()

        self.sample_virtual_good = VirtualGood.query.filter_by(name="Test Reward Good").first()
        if not self.sample_virtual_good:
            self.sample_virtual_good = VirtualGood(name="Test Reward Good", description="A good for testing.", price=0, currency="USD", type="title", title_text="Tester", is_active=True)
            db.session.add(self.sample_virtual_good)
            db.session.commit()


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # Helper to create a quest
    def _create_quest(self, title, criteria_type, target_count=1, reward_points=0, reward_badge_id=None, reward_virtual_good_id=None, type='achievement', is_active=True, repeatable_after_hours=None, start_date=None, end_date=None):
        quest = Quest(
            title=title, description=f"Desc for {title}", type=type,
            criteria_type=criteria_type, criteria_target_count=target_count,
            reward_points=reward_points, reward_badge_id=reward_badge_id,
            reward_virtual_good_id=reward_virtual_good_id, is_active=is_active,
            repeatable_after_hours=repeatable_after_hours,
            start_date=start_date, end_date=end_date
        )
        db.session.add(quest)
        db.session.commit()
        return quest

    # 1. Test Model Creation and Relationships
    def test_create_quest_model(self):
        q = self._create_quest("Test Quest 1", "test_action", 5, reward_points=10, reward_badge_id=self.sample_badge.id)
        self.assertIsNotNone(q.id)
        self.assertEqual(q.title, "Test Quest 1")
        self.assertEqual(q.reward_badge.name, self.sample_badge.name)

    def test_create_user_quest_progress(self):
        quest = self._create_quest("Progress Quest", "test_progress", 1)
        progress = UserQuestProgress(user_id=self.user1.id, quest_id=quest.id)
        db.session.add(progress)
        db.session.commit()

        self.assertIsNotNone(progress.id)
        self.assertEqual(progress.user_id, self.user1.id)
        self.assertEqual(progress.quest_id, quest.id)
        self.assertEqual(progress.current_count, 0)
        self.assertEqual(progress.status, 'in_progress')
        self.assertIsNotNone(progress.last_progress_at)

        # Test unique constraint
        duplicate_progress = UserQuestProgress(user_id=self.user1.id, quest_id=quest.id)
        db.session.add(duplicate_progress)
        with self.assertRaises(Exception): # Should raise IntegrityError or similar
            db.session.commit()
        db.session.rollback()

    # 2. Test seed_quests() Function
    def test_seed_quests(self):
        # Ensure no quests exist
        Quest.query.delete()
        db.session.commit()

        # Seed photographer badge and first steps title if they don't exist from main seeding
        photographer_badge = Badge.query.filter_by(criteria_key='photographer').first()
        if not photographer_badge:
             photographer_badge = Badge(name="Photographer", description="Test", criteria_key="photographer", icon_url="test.png")
             db.session.add(photographer_badge)

        first_steps_title = VirtualGood.query.filter_by(name="First Steps Title", type="title").first()
        if not first_steps_title:
            first_steps_title = VirtualGood(name="First Steps Title", type="title", price=0, currency="USD", title_text="Newbie", is_active=True)
            db.session.add(first_steps_title)
        db.session.commit()

        seed_quests()

        # Check if initial quests are added (count should match initial_quests in quest_utils)
        # This count might need adjustment based on your actual seed_quests content
        expected_quest_count = 5
        self.assertEqual(Quest.query.count(), expected_quest_count)

        # Test idempotency
        seed_quests() # Call again
        self.assertEqual(Quest.query.count(), expected_quest_count) # Count should remain the same

    # 3. Test update_quest_progress() Logic
    @patch('app.utils.quest_utils.app_socketio.emit') # Mock socketio
    def test_update_quest_progress_basic_and_completion(self, mock_socketio_emit):
        quest = self._create_quest("Simple Action Quest", "simple_action", target_count=2, reward_points=10)

        # First action
        update_quest_progress(self.user1, "simple_action")
        db.session.commit() # Route would commit
        progress = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertIsNotNone(progress)
        self.assertEqual(progress.current_count, 1)
        self.assertEqual(progress.status, 'in_progress')

        # Second action (completes quest)
        update_quest_progress(self.user1, "simple_action")
        db.session.commit() # Route would commit
        progress_updated = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertEqual(progress_updated.current_count, 2)
        self.assertEqual(progress_updated.status, 'completed')
        self.assertIsNotNone(progress_updated.completed_at)

        # Check notification
        notification = Notification.query.filter_by(recipient_id=self.user1.id, type='quest_completed').first()
        self.assertIsNotNone(notification)
        mock_socketio_emit.assert_called_once() # Assuming only one completion so far

    @patch('app.utils.quest_utils.app_socketio.emit')
    def test_non_repeatable_quest_already_completed(self, mock_socketio_emit):
        quest = self._create_quest("Non-Repeatable", "non_repeat_action", target_count=1)
        # Complete it
        update_quest_progress(self.user1, "non_repeat_action")
        db.session.commit()

        progress = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertEqual(progress.status, 'completed')
        mock_socketio_emit.reset_mock()

        # Try to progress again
        update_quest_progress(self.user1, "non_repeat_action")
        db.session.commit()
        progress_after = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertEqual(progress_after.current_count, 1) # Count should not change
        self.assertEqual(progress_after.status, 'completed') # Status should not change
        mock_socketio_emit.assert_not_called()

    @patch('app.utils.quest_utils.datetime') # Mock datetime inside quest_utils
    @patch('app.utils.quest_utils.app_socketio.emit')
    def test_repeatable_quest_cooldown_and_reset(self, mock_socketio_emit, mock_datetime_qutils):
        now_time = datetime.now(timezone.utc)
        mock_datetime_qutils.now.return_value = now_time # Initial time

        quest = self._create_quest("Repeatable Quest", "repeat_action", target_count=1, repeatable_after_hours=1)

        # First completion
        update_quest_progress(self.user1, "repeat_action")
        db.session.commit()
        progress = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertEqual(progress.status, 'completed')
        self.assertIsNotNone(progress.last_completed_instance_at)

        # Manually set to claimed for testing cooldown logic properly
        progress.status = 'claimed'
        db.session.commit()

        # Try to progress before cooldown
        update_quest_progress(self.user1, "repeat_action")
        db.session.commit()
        progress_before_cooldown = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertEqual(progress_before_cooldown.status, 'claimed') # Should still be claimed
        self.assertEqual(progress_before_cooldown.current_count, 1) # Count shouldn't reset

        # Advance time past cooldown
        mock_datetime_qutils.now.return_value = now_time + timedelta(hours=2)

        # Progress again, should reset and count
        update_quest_progress(self.user1, "repeat_action")
        db.session.commit()
        progress_after_cooldown = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertEqual(progress_after_cooldown.status, 'in_progress') # Reset to in_progress
        self.assertEqual(progress_after_cooldown.current_count, 1) # Incremented after reset

    def test_create_post_with_media_quest(self):
        quest = self._create_quest("Media Poster", "create_post_with_media", 1)

        # Create a post without media
        post_no_media = Post(body="Text only", author=self.user1)
        db.session.add(post_no_media)
        db.session.commit() # Post needs ID for related_item

        update_quest_progress(self.user1, "create_post_with_media", related_item=post_no_media)
        db.session.commit()
        progress = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertIsNone(progress) # No progress should be made

        # Create a post with media
        post_with_media = Post(body="With image", author=self.user1)
        db.session.add(post_with_media)
        db.session.flush() # Get post ID
        media_item = MediaItem(filename="test.jpg", media_type="image", post_id=post_with_media.id)
        db.session.add(media_item)
        db.session.commit()

        update_quest_progress(self.user1, "create_post_with_media", related_item=post_with_media)
        db.session.commit()
        progress_with_media = UserQuestProgress.query.filter_by(user_id=self.user1.id, quest_id=quest.id).first()
        self.assertIsNotNone(progress_with_media)
        self.assertEqual(progress_with_media.current_count, 1)
        self.assertEqual(progress_with_media.status, 'completed')

    @patch('app.utils.quest_utils.datetime')
    def test_timed_quests(self, mock_datetime_qutils):
        now_fixed = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime_qutils.now.return_value = now_fixed

        quest_future = self._create_quest("Future Quest", "timed_action", start_date=now_fixed + timedelta(days=1))
        quest_past = self._create_quest("Past Quest", "timed_action", end_date=now_fixed - timedelta(days=1))
        quest_current = self._create_quest("Current Quest", "timed_action", start_date=now_fixed - timedelta(days=1), end_date=now_fixed + timedelta(days=1))

        # Try future quest - no progress
        update_quest_progress(self.user1, "timed_action")
        db.session.commit()
        self.assertIsNone(UserQuestProgress.query.filter_by(quest_id=quest_future.id).first())

        # Try past quest - no progress
        update_quest_progress(self.user1, "timed_action")
        db.session.commit()
        self.assertIsNone(UserQuestProgress.query.filter_by(quest_id=quest_past.id).first())

        # Try current quest - should make progress
        update_quest_progress(self.user1, "timed_action")
        db.session.commit()
        self.assertIsNotNone(UserQuestProgress.query.filter_by(quest_id=quest_current.id).first())

    # 4. Test Reward Claiming Route
    def test_claim_quest_reward_successful(self):
        quest = self._create_quest("Claim Test Quest", "claim_action", 1, reward_points=50, reward_badge_id=self.sample_badge.id, reward_virtual_good_id=self.sample_virtual_good.id)
        progress = UserQuestProgress(user_id=self.user1.id, quest_id=quest.id, current_count=1, status='completed', completed_at=datetime.now(timezone.utc))
        db.session.add(progress)
        db.session.commit()

        with self.app.test_client() as client:
            # Simulate login
            with client.session_transaction() as sess:
                sess['user_id'] = str(self.user1.id) # Flask-Login uses string IDs in session
                sess['_fresh'] = True

            initial_points = UserPoints.query.filter_by(user_id=self.user1.id).first().points if UserPoints.query.filter_by(user_id=self.user1.id).first() else 0

            response = client.post(f'/quests/claim/{progress.id}')
            self.assertEqual(response.status_code, 302) # Redirect expected
            # Check flash message (more complex, often tested in UI tests)

        updated_progress = UserQuestProgress.query.get(progress.id)
        self.assertEqual(updated_progress.status, 'claimed')

        # Verify points
        user_points = UserPoints.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(user_points)
        self.assertEqual(user_points.points, initial_points + quest.reward_points)

        # Verify badge
        self.assertIn(self.sample_badge, self.user1.badges)

        # Verify virtual good
        uvg = UserVirtualGood.query.filter_by(user_id=self.user1.id, virtual_good_id=self.sample_virtual_good.id).first()
        self.assertIsNotNone(uvg)

        # Verify ActivityLogs
        self.assertIsNotNone(ActivityLog.query.filter_by(user_id=self.user1.id, activity_type='quest_reward_points').first())
        self.assertIsNotNone(ActivityLog.query.filter_by(user_id=self.user1.id, activity_type='quest_reward_badge').first())
        self.assertIsNotNone(ActivityLog.query.filter_by(user_id=self.user1.id, activity_type='quest_reward_virtual_good').first())

    # 5. Test UI Route (/quests)
    def test_view_quests_route(self):
        self._create_quest("Available Q", "avail_action", 1)
        progress_quest = self._create_quest("In Progress Q", "progress_action", 2)
        UserQuestProgress.query.delete() # Clear any prior progress for this user
        db.session.commit()

        up = UserQuestProgress(user_id=self.user1.id, quest_id=progress_quest.id, current_count=1)
        db.session.add(up)
        db.session.commit()

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = str(self.user1.id)
                sess['_fresh'] = True

            response = client.get('/quests')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Available Quests", response.data)
            self.assertIn(b"In Progress Quests", response.data)
            self.assertIn(b"Available Q", response.data)
            self.assertIn(b"In Progress Q", response.data)


if __name__ == '__main__':
    unittest.main()
