import unittest
from app import create_app, db, socketio, cache
from app.models import User, Post, Share, Notification, Group, GroupMembership
from flask_login import login_user, logout_user, current_user
from datetime import datetime, timedelta

from config import TestingConfig

class SharingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_class=TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create users
        self.user1 = User(username='user1', email='user1@example.com')
        self.user1.set_password('password')
        self.user2 = User(username='user2', email='user2@example.com')
        self.user2.set_password('password')
        db.session.add_all([self.user1, self.user2])
        db.session.commit()

        # Create a post by user1
        self.post1 = Post(body="User1's amazing post", author=self.user1)
        db.session.add(self.post1)
        db.session.commit()

        # Clear cache before each test to ensure isolation for feed tests
        cache.clear()


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        # Clear cache after each test
        cache.clear()

    def _login(self, user, password='password'):
        return self.client.post('/login', data=dict(
            email=user.email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # Helper to create a group and add members
    def _create_group_with_member(self, creator, member=None):
        group = Group(name='Test Group', description='A test group', creator=creator)
        db.session.add(group)
        db.session.flush() # Get group.id

        # Add creator as admin
        membership_creator = GroupMembership(user_id=creator.id, group_id=group.id, role='admin')
        db.session.add(membership_creator)

        if member:
            membership_member = GroupMembership(user_id=member.id, group_id=group.id, role='member')
            db.session.add(membership_member)

        db.session.commit()
        return group

    def test_share_model_creation(self):
        share = Share(user_id=self.user2.id, post_id=self.post1.id, timestamp=datetime.utcnow())
        db.session.add(share)
        db.session.commit()
        self.assertIsNotNone(share.id)
        self.assertEqual(share.user, self.user2)
        self.assertEqual(share.original_post, self.post1)
        self.assertIsNone(share.group) # Initially no group

    def test_share_post_to_own_feed(self):
        self._login(self.user2)
        response = self.client.post(f'/post/{self.post1.id}/share', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Post shared successfully!', response.data)

        share = Share.query.filter_by(user_id=self.user2.id, post_id=self.post1.id).first()
        self.assertIsNotNone(share)
        self.assertIsNone(share.group_id) # Shared to own feed

        # Check notification for user1 (original poster)
        notification = Notification.query.filter_by(recipient_id=self.user1.id, type='share').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.user2.id)
        self.assertEqual(notification.related_post_id, self.post1.id)
        self._logout()

    def test_cannot_share_own_post_to_own_feed(self):
        self._login(self.user1) # user1 is author of post1
        response = self.client.post(f'/post/{self.post1.id}/share', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"You cannot share your own post to your main feed.", response.data)

        share = Share.query.filter_by(user_id=self.user1.id, post_id=self.post1.id, group_id=None).first()
        self.assertIsNone(share) # No share should be created
        self._logout()

    def test_share_post_to_group(self):
        group = self._create_group_with_member(creator=self.user1, member=self.user2)
        self._login(self.user2) # user2 will share post1 to the group

        response = self.client.post(f'/post/{self.post1.id}/share', data={'group_id': group.id}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Post shared successfully!', response.data)
        # Check redirect to group page (assuming group name is in the page title or body)
        # A more robust check would be to check the response.request.path if using Flask 2.x+ or parse location header
        self.assertTrue(b'Test Group' in response.data or group.name.encode() in response.data)


        share = Share.query.filter_by(user_id=self.user2.id, post_id=self.post1.id, group_id=group.id).first()
        self.assertIsNotNone(share)
        self.assertEqual(share.group, group)

        # Check notification for user1 (original poster)
        notification = Notification.query.filter_by(recipient_id=self.user1.id, type='share').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.user2.id)
        self.assertEqual(notification.related_post_id, self.post1.id)
        self._logout()

    def test_cannot_reshare_to_same_destination(self):
        self._login(self.user2)
        # First share
        self.client.post(f'/post/{self.post1.id}/share', follow_redirects=True)

        # Attempt second share to own feed
        response = self.client.post(f'/post/{self.post1.id}/share', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You have already shared this post to this destination.', response.data)

        shares = Share.query.filter_by(user_id=self.user2.id, post_id=self.post1.id).all()
        self.assertEqual(len(shares), 1) # Only one share should exist
        self._logout()

    def test_shared_post_appears_in_feed(self):
        # user2 shares user1's post
        # Use a slightly older timestamp for the original post to distinguish from share time
        self.post1.timestamp = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()

        share_time = datetime.utcnow()
        share = Share(user=self.user2, original_post=self.post1, timestamp=share_time)
        db.session.add(share)
        db.session.commit()

        # user1 follows user2 so they can see user2's share
        self.user1.follow(self.user2)
        db.session.commit()

        self._login(self.user1) # Log in as user1 to view their feed

        response = self.client.get('/index') # Get the feed page
        self.assertEqual(response.status_code, 200)

        # Expected: user1's feed should contain user1's original post (because it's their own)
        # AND user2's share of user1's post (because user1 follows user2)
        # The _post.html template is used for both, differentiated by item_wrapper.type

        html_content = response.data.decode('utf-8')

        # Check for user1's original post display (not as a share by someone else)
        # This part is tricky because the same post content appears twice.
        # We rely on the structure generated by the loop in index.html and _post.html logic.
        # The original post will not have the "Shared by" attribution right before its header.

        # Check for user2's share of user1's post
        # This item should have the "Shared by user2" attribution
        self.assertIn(f"Shared by {self.user2.username}", html_content)
        self.assertIn(f"Original post on {self.post1.timestamp.strftime('%Y-%m-%d %H:%M')}", html_content)
        self.assertIn(self.post1.body, html_content)

        # To be more specific, we could count occurrences or use a more detailed parser,
        # but for now, checking for key phrases is a good start.
        # Ensure the shared item's timestamp is the share_time
        self.assertIn(f"on {share_time.strftime('%Y-%m-%d %H:%M')}", html_content)

        self._logout()

if __name__ == '__main__':
    unittest.main()
