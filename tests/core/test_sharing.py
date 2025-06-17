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
        self.user3 = User(username='user3', email='user3@example.com') # New user
        self.user3.set_password('password')
        db.session.add_all([self.user1, self.user2, self.user3])
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

    def _add_user_to_group(self, user, group, role='member'):
        membership = GroupMembership(user_id=user.id, group_id=group.id, role=role)
        db.session.add(membership)
        # Removed commit from here to be part of a larger commit in _create_group_with_members

    def _create_group_with_members(self, creator, members_users_roles=None):
        # Unique group name using timestamp
        group = Group(name=f'Test Group {datetime.utcnow().timestamp()}', description='A test group', creator=creator)
        db.session.add(group)
        db.session.flush()

        self._add_user_to_group(creator, group, role='admin')

        if members_users_roles:
            for user_obj, role in members_users_roles: # Corrected variable name
                self._add_user_to_group(user_obj, group, role=role)

        db.session.commit() # Single commit at the end
        return group

    # Optional: Keep the old helper if other tests might use it, or adapt them.
    # For this task, the new one is preferred.
    # def _create_group_with_member(self, creator, member=None):
    #     group = Group(name='Test Group', description='A test group', creator=creator)
    #     db.session.add(group)
    #     db.session.flush() # Get group.id
    #     membership_creator = GroupMembership(user_id=creator.id, group_id=group.id, role='admin')
    #     db.session.add(membership_creator)
    #     if member:
    #         membership_member = GroupMembership(user_id=member.id, group_id=group.id, role='member')
    #         db.session.add(membership_member)
    #     db.session.commit()
    #     return group

    def _check_notification_exists(self, recipient_id, actor_id, type, post_id=None, group_id=None):
        query = Notification.query.filter_by(
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=type
        )
        if post_id:
            query = query.filter_by(related_post_id=post_id)
        if group_id:
            query = query.filter_by(related_group_id=group_id)

        notification = query.first()
        self.assertIsNotNone(notification,
            f"Notification not found for recipient {recipient_id}, actor {actor_id}, type {type}, post {post_id}, group {group_id}")
        return notification

    def _check_notification_does_not_exist(self, recipient_id, actor_id, type, post_id=None, group_id=None):
        query = Notification.query.filter_by(
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=type
        )
        if post_id:
            query = query.filter_by(related_post_id=post_id)
        if group_id:
            query = query.filter_by(related_group_id=group_id)

        notification = query.first()
        self.assertIsNone(notification,
            f"Notification unexpectedly found for recipient {recipient_id}, actor {actor_id}, type {type}, post {post_id}, group {group_id}")

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

    def test_share_post_to_group(self): # This test can be enhanced or replaced by the new more specific tests
        group = self._create_group_with_members(creator=self.user1, members_users_roles=[(self.user2, 'member')])
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
        self.assertIn(f"on {share_time.strftime('%Y-%m-%d %H:%M')}", html_content) # Check for the share time

        self._logout()

    def test_share_post_to_group_feed_and_notifications(self):
        # 1. Setup: Create group, add user1 (author), user2 (sharer), user3 (member)
        group = self._create_group_with_members(creator=self.user1, members_users_roles=[
            (self.user2, 'member'),
            (self.user3, 'member')
        ])

        # 2. Action: user2 logs in and shares post1 (by user1) to the group
        self._login(self.user2)
        response = self.client.post(f'/post/{self.post1.id}/share', data={'group_id': group.id}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Post shared successfully!', response.data)

        # 3. Verify Share Creation
        share = Share.query.filter_by(user_id=self.user2.id, post_id=self.post1.id, group_id=group.id).first()
        self.assertIsNotNone(share)
        self.assertEqual(share.user, self.user2)
        self.assertEqual(share.original_post, self.post1)
        self.assertEqual(share.group, group)
        share_timestamp_str = share.timestamp.strftime('%Y-%m-%d %H:%M') # For checking in HTML
        self._logout()

        # 4. Verify Group Feed for user3
        self._login(self.user3)
        response = self.client.get(f'/group/{group.id}')
        self.assertEqual(response.status_code, 200)
        html_content = response.data.decode('utf-8')

        # Check for the "Shared by user2" attribution and the share timestamp
        # The _post.html template creates a structure like:
        # <small class="text-muted"> Shared by <a href="...">user2</a> on SHARE_TIMESTAMP UTC </small>
        # ... then original post details ...
        self.assertIn(f"Shared by {self.user2.username}", html_content)
        self.assertIn(f"on {share_timestamp_str}", html_content) # Check for share timestamp
        self.assertIn(self.post1.body, html_content) # Original post content
        self.assertIn(self.post1.author.username, html_content) # Original author
        self._logout()

        # 5. Verify Notifications for Group Members
        # user1 (post author, group member) should get 'group_share' from user2
        self._check_notification_exists(recipient_id=self.user1.id, actor_id=self.user2.id,
                                        type='group_share', post_id=self.post1.id, group_id=group.id)

        # user3 (other group member) should get 'group_share' from user2
        self._check_notification_exists(recipient_id=self.user3.id, actor_id=self.user2.id,
                                        type='group_share', post_id=self.post1.id, group_id=group.id)

        # user2 (sharer) should NOT get 'group_share' for their own action
        self._check_notification_does_not_exist(recipient_id=self.user2.id, actor_id=self.user2.id,
                                                type='group_share', post_id=self.post1.id, group_id=group.id)

        # 6. Verify Notification for Original Post Author (Standard Share Notification)
        # user1 (original post author) should also receive the standard 'share' notification from user2
        self._check_notification_exists(recipient_id=self.user1.id, actor_id=self.user2.id,
                                        type='share', post_id=self.post1.id)
        # Ensure this 'share' notification is NOT tied to the group specifically in Notification table
        std_share_notif = Notification.query.filter_by(recipient_id=self.user1.id, actor_id=self.user2.id, type='share', post_id=self.post1.id).first()
        self.assertIsNotNone(std_share_notif)
        self.assertIsNone(std_share_notif.related_group_id)


    def test_sharing_own_post_to_group(self):
        # 1. Setup: Create group, add user1 (author/sharer) and user2 (member)
        group = self._create_group_with_members(creator=self.user1, members_users_roles=[
            (self.user2, 'member')
        ])

        # 2. Action: user1 logs in and shares their own post1 to the group
        self._login(self.user1)
        response = self.client.post(f'/post/{self.post1.id}/share', data={'group_id': group.id}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Post shared successfully!', response.data)

        # 3. Verify Share Creation
        share = Share.query.filter_by(user_id=self.user1.id, post_id=self.post1.id, group_id=group.id).first()
        self.assertIsNotNone(share)
        share_timestamp_str = share.timestamp.strftime('%Y-%m-%d %H:%M')
        self._logout()

        # 4. Verify Group Feed for user2
        self._login(self.user2)
        response = self.client.get(f'/group/{group.id}')
        self.assertEqual(response.status_code, 200)
        html_content = response.data.decode('utf-8')
        self.assertIn(f"Shared by {self.user1.username}", html_content) # Shared by user1
        self.assertIn(f"on {share_timestamp_str}", html_content)
        self.assertIn(self.post1.body, html_content)
        self._logout()

        # 5. Verify Notifications
        # user2 (other group member) should get 'group_share' from user1
        self._check_notification_exists(recipient_id=self.user2.id, actor_id=self.user1.id,
                                        type='group_share', post_id=self.post1.id, group_id=group.id)

        # user1 (sharer and author) should NOT get 'group_share'
        self._check_notification_does_not_exist(recipient_id=self.user1.id, actor_id=self.user1.id,
                                                type='group_share', post_id=self.post1.id, group_id=group.id)

        # user1 (sharer and author) should NOT get standard 'share' notification (as they shared their own post)
        # The route logic for standard 'share' is `if post_to_share.author != current_user:`
        self._check_notification_does_not_exist(recipient_id=self.user1.id, actor_id=self.user1.id,
                                                type='share', post_id=self.post1.id)

    def test_prevent_duplicate_share_to_same_group(self):
        # 1. Setup: Create group, add user2 as member
        group = self._create_group_with_members(creator=self.user1, members_users_roles=[(self.user2, 'member')])

        # 2. Action: user2 logs in and shares post1 to the group
        self._login(self.user2)
        response_first_share = self.client.post(f'/post/{self.post1.id}/share', data={'group_id': group.id}, follow_redirects=True)
        self.assertEqual(response_first_share.status_code, 200)
        self.assertIn(b'Post shared successfully!', response_first_share.data)

        # 3. Attempt to share again to the same group
        response_second_share = self.client.post(f'/post/{self.post1.id}/share', data={'group_id': group.id}, follow_redirects=True)
        self.assertEqual(response_second_share.status_code, 200)
        self.assertIn(b'You have already shared this post to this destination.', response_second_share.data)
        self._logout()

        # 4. Verify No New Share
        shares = Share.query.filter_by(user_id=self.user2.id, post_id=self.post1.id, group_id=group.id).all()
        self.assertEqual(len(shares), 1)


if __name__ == '__main__':
    unittest.main()
