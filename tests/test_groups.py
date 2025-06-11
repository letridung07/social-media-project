import unittest
import os
import io
from flask import current_app
from app import create_app, db
from app.models import User, Post, Group, GroupMembership, Notification
from config import TestingConfig
from werkzeug.datastructures import FileStorage # For mock files
import base64 # For dummy image data

class GroupTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.client = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # Create test users
        self.u1 = User(username='user1', email='user1@example.com')
        self.u1.set_password('password')
        self.u2 = User(username='user2', email='user2@example.com')
        self.u2.set_password('password')
        self.u3 = User(username='user3', email='user3@example.com')
        self.u3.set_password('password')
        db.session.add_all([self.u1, self.u2, self.u3])
        db.session.commit()

        # Path for group images
        self.group_images_path = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER_GROUP_IMAGES'])
        os.makedirs(self.group_images_path, exist_ok=True)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

        # Clean up group_images directory
        if os.path.exists(self.group_images_path):
            for f in os.listdir(self.group_images_path):
                try:
                    os.remove(os.path.join(self.group_images_path, f))
                except OSError:
                    pass
            if not os.listdir(self.group_images_path): # Only remove if empty
                try:
                    os.rmdir(self.group_images_path)
                except OSError: # Could fail if other tests are creating files there concurrently, though unlikely for test setup
                    pass


    # --- Helper Methods ---
    def _login(self, email, password):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def _create_group(self, name, description, image_file_storage=None):
        data = {
            'name': name,
            'description': description,
        }
        if image_file_storage:
            data['image_file'] = image_file_storage

        return self.client.post('/group/create', data=data,
                                content_type='multipart/form-data', follow_redirects=True)

    def _create_post_in_group(self, user_email, user_password, body, group_id, alt_text=None):
        self._login(user_email, user_password)
        data = {'body': body}
        if alt_text:
            data['alt_text'] = alt_text
        # Assuming no image/video for simplicity in this helper for now
        response = self.client.post(f'/create_post?group_id={group_id}', data=data, follow_redirects=True)
        self._logout()
        return response

    def _get_dummy_image(self, filename="test_image.png"):
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        mock_image_data = io.BytesIO(base64.b64decode(png_b64))
        return FileStorage(stream=mock_image_data, filename=filename, content_type="image/png")

    # --- Test Cases ---

    def test_group_creation_page_load(self):
        self._login(self.u1.email, 'password')
        response = self.client.get('/group/create')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Create New Group', response.data)
        self._logout()

    def test_group_creation_logged_out_redirect(self):
        response = self.client.get('/group/create', follow_redirects=True)
        self.assertTrue(response.request.path.startswith('/login'))

        response_post = self.client.post('/group/create', data={'name': 'Fail Group', 'description': 'Desc'}, follow_redirects=True)
        self.assertTrue(response_post.request.path.startswith('/login'))

    def test_successful_group_creation_no_image(self):
        self._login(self.u1.email, 'password')
        group_name = "Test Group Alpha"
        group_desc = "Description for Test Group Alpha"
        response = self._create_group(group_name, group_desc)

        self.assertEqual(response.status_code, 200) # Should redirect to group view page
        self.assertIn(b'Group created successfully!', response.data)
        self.assertIn(bytes(group_name, 'utf-8'), response.data) # Check group name on the group page

        group = Group.query.filter_by(name=group_name).first()
        self.assertIsNotNone(group)
        self.assertEqual(group.description, group_desc)
        self.assertEqual(group.creator_id, self.u1.id)
        self.assertEqual(group.image_file, 'default_group_pic.png') # Default image

        # Verify creator is admin
        membership = GroupMembership.query.filter_by(user_id=self.u1.id, group_id=group.id).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'admin')
        self._logout()

    def test_successful_group_creation_with_image(self):
        self._login(self.u1.email, 'password')
        group_name = "Test Group Beta"
        group_desc = "Description for Test Group Beta with image"
        dummy_image = self._get_dummy_image("beta_group.png")

        response = self._create_group(group_name, group_desc, image_file_storage=dummy_image)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Group created successfully!', response.data)

        group = Group.query.filter_by(name=group_name).first()
        self.assertIsNotNone(group)
        self.assertNotEqual(group.image_file, 'default_group_pic.png')
        self.assertTrue(group.image_file.endswith('.png'))

        expected_image_path = os.path.join(self.group_images_path, group.image_file)
        self.assertTrue(os.path.exists(expected_image_path)) # Verify image file was saved
        self._logout()

    def test_view_group_page(self):
        self._login(self.u1.email, 'password')
        group = Group(name="View Test Group", description="View Desc", creator_id=self.u1.id)
        db.session.add(group)
        db.session.commit()
        # u1 is creator and thus admin, and member
        self._logout()

        # Non-member (u2) viewing
        self._login(self.u2.email, 'password')
        response_u2 = self.client.get(f'/group/{group.id}')
        self.assertEqual(response_u2.status_code, 200)
        self.assertIn(b'View Test Group', response_u2.data)
        self.assertIn(b'Join Group', response_u2.data) # u2 should see Join
        self.assertNotIn(b'Leave Group', response_u2.data)
        self.assertNotIn(b'Manage Group', response_u2.data)
        self._logout()

        # Member (u1, admin) viewing
        self._login(self.u1.email, 'password')
        response_u1 = self.client.get(f'/group/{group.id}')
        self.assertEqual(response_u1.status_code, 200)
        self.assertIn(b'View Test Group', response_u1.data)
        self.assertNotIn(b'Join Group', response_u1.data)
        self.assertIn(b'Leave Group', response_u1.data) # u1 can leave
        self.assertIn(b'Manage Group', response_u1.data) # u1 is admin
        self._logout()

    def test_join_and_leave_group(self):
        # u1 creates a group
        self._login(self.u1.email, 'password')
        self._create_group("JoinLeave Group", "JL Desc")
        group = Group.query.filter_by(name="JoinLeave Group").first()
        self.assertIsNotNone(group)
        self._logout()

        # u2 joins the group
        self._login(self.u2.email, 'password')
        response_join = self.client.post(f'/group/{group.id}/join', follow_redirects=True)
        self.assertEqual(response_join.status_code, 200)
        self.assertIn(b'You have successfully joined the group', response_join.data)
        membership_u2 = GroupMembership.query.filter_by(user_id=self.u2.id, group_id=group.id).first()
        self.assertIsNotNone(membership_u2)
        self.assertEqual(membership_u2.role, 'member')

        # u2 tries to join again
        response_join_again = self.client.post(f'/group/{group.id}/join', follow_redirects=True)
        self.assertEqual(response_join_again.status_code, 200)
        self.assertIn(b'You are already a member of this group', response_join_again.data)

        # u2 leaves the group
        response_leave = self.client.post(f'/group/{group.id}/leave', follow_redirects=True)
        self.assertEqual(response_leave.status_code, 200)
        self.assertIn(b'You have left the group', response_leave.data)
        self.assertIsNone(GroupMembership.query.filter_by(user_id=self.u2.id, group_id=group.id).first())
        self._logout()

        # u3 (non-member) tries to leave
        self._login(self.u3.email, 'password')
        response_leave_non_member = self.client.post(f'/group/{group.id}/leave', follow_redirects=True)
        self.assertEqual(response_leave_non_member.status_code, 200)
        self.assertIn(b'You are not a member of this group', response_leave_non_member.data)
        self._logout()

    def test_posting_to_group(self):
        # u1 creates group
        self._login(self.u1.email, 'password')
        self._create_group("Postable Group", "Posts here")
        group = Group.query.filter_by(name="Postable Group").first()
        self._logout()

        # u1 (member) posts to group
        post_body_u1 = "U1's post in Postable Group"
        self._create_post_in_group(self.u1.email, 'password', post_body_u1, group.id)

        post1 = Post.query.filter_by(body=post_body_u1).first()
        self.assertIsNotNone(post1)
        self.assertEqual(post1.group_id, group.id)
        self.assertEqual(post1.user_id, self.u1.id)

        # Verify post appears on group page
        group_page_response = self.client.get(f'/group/{group.id}')
        self.assertIn(bytes(post_body_u1, 'utf-8'), group_page_response.data)

        # u2 (non-member) tries to post to group
        self._login(self.u2.email, 'password')
        post_body_u2_fail = "U2's failed post"
        response_u2_fail = self.client.post(f'/create_post?group_id={group.id}',
                                             data={'body': post_body_u2_fail}, follow_redirects=True)
        self.assertIn(b'You are not a member of this group and cannot post in it', response_u2_fail.data)
        self.assertIsNone(Post.query.filter_by(body=post_body_u2_fail).first())
        self._logout()

    def test_group_management_edit_group(self):
        # u1 (admin) creates group
        self._login(self.u1.email, 'password')
        self._create_group("Manageable Group", "Original Desc")
        group = Group.query.filter_by(name="Manageable Group").first()

        # u1 edits the group
        updated_name = "Managed Group Name"
        updated_desc = "Updated Description"
        dummy_image_edit = self._get_dummy_image("edited_group.jpg")
        response_edit = self.client.post(f'/group/{group.id}/manage', data={
            'name': updated_name,
            'description': updated_desc,
            'image_file': dummy_image_edit
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(response_edit.status_code, 200) # Redirects to manage page
        self.assertIn(b'Group details updated successfully!', response_edit.data)

        db.session.refresh(group)
        self.assertEqual(group.name, updated_name)
        self.assertEqual(group.description, updated_desc)
        self.assertNotEqual(group.image_file, 'default_group_pic.png')
        self.assertTrue(group.image_file.endswith('.jpg'))
        self.assertTrue(os.path.exists(os.path.join(self.group_images_path, group.image_file)))
        self._logout()

        # u2 (non-admin) tries to access manage page
        self._login(self.u2.email, 'password')
        response_u2_get = self.client.get(f'/group/{group.id}/manage', follow_redirects=True)
        self.assertIn(b'You are not authorized to manage this group', response_u2_get.data)
        # u2 tries to post to manage page
        response_u2_post = self.client.post(f'/group/{group.id}/manage', data={'name': 'Hack Attempt'}, follow_redirects=True)
        self.assertIn(b'You are not authorized to manage this group', response_u2_post.data)
        self._logout()

    def test_group_management_remove_member(self):
        # u1 (admin) creates group, u2 joins
        self._login(self.u1.email, 'password')
        self._create_group("Member Removal Group", "MRG Desc")
        group = Group.query.filter_by(name="Member Removal Group").first()
        self._logout()

        self._login(self.u2.email, 'password')
        self.client.post(f'/group/{group.id}/join', follow_redirects=True)
        self.assertIsNotNone(GroupMembership.query.filter_by(user_id=self.u2.id, group_id=group.id).first())
        self._logout()

        # u1 (admin) removes u2
        self._login(self.u1.email, 'password')
        response_remove = self.client.post(f'/group/{group.id}/remove_member/{self.u2.id}', follow_redirects=True)
        self.assertEqual(response_remove.status_code, 200) # On manage page
        self.assertIn(bytes(f'{self.u2.username} has been removed from the group', 'utf-8'), response_remove.data)
        self.assertIsNone(GroupMembership.query.filter_by(user_id=self.u2.id, group_id=group.id).first())

        # u1 (admin) tries to remove self (creator, only admin) - should fail based on current logic
        response_remove_self = self.client.post(f'/group/{group.id}/remove_member/{self.u1.id}', follow_redirects=True)
        self.assertIn(b'You cannot remove yourself as you are the only admin', response_remove_self.data)
        self.assertIsNotNone(GroupMembership.query.filter_by(user_id=self.u1.id, group_id=group.id).first())
        self._logout()

        # u3 (non-admin) joins, then u2 (now non-member and non-admin) tries to remove u3
        self._login(self.u3.email, 'password')
        self.client.post(f'/group/{group.id}/join', follow_redirects=True)
        self._logout()

        self._login(self.u2.email, 'password')
        response_u2_remove_u3 = self.client.post(f'/group/{group.id}/remove_member/{self.u3.id}', follow_redirects=True)
        self.assertIn(b'You are not authorized to manage this group', response_u2_remove_u3.data)
        self.assertIsNotNone(GroupMembership.query.filter_by(user_id=self.u3.id, group_id=group.id).first()) # u3 still member
        self._logout()

    def test_group_management_delete_group(self):
        # u1 (admin) creates group
        self._login(self.u1.email, 'password')
        self._create_group("Deletable Group", "DG Desc", image_file_storage=self._get_dummy_image("delete.png"))
        group = Group.query.filter_by(name="Deletable Group").first()
        group_image_filename = group.image_file # Save for checking deletion

        # u1 creates a post in this group
        self._create_post_in_group(self.u1.email, 'password', "Post in Deletable Group", group.id)
        post = Post.query.filter_by(group_id=group.id).first()
        self.assertIsNotNone(post)

        # u2 joins this group
        self._logout()
        self._login(self.u2.email, 'password')
        self.client.post(f'/group/{group.id}/join', follow_redirects=True)
        self.assertIsNotNone(GroupMembership.query.filter_by(user_id=self.u2.id, group_id=group.id).first())
        self._logout()

        # u3 (non-admin) tries to delete
        self._login(self.u3.email, 'password')
        response_u3_delete = self.client.post(f'/group/{group.id}/delete', follow_redirects=True)
        self.assertIn(b'You are not authorized to delete this group', response_u3_delete.data)
        self.assertIsNotNone(Group.query.get(group.id)) # Group still exists
        self._logout()

        # u1 (admin) deletes the group
        self._login(self.u1.email, 'password')
        response_delete = self.client.post(f'/group/{group.id}/delete', follow_redirects=True)
        self.assertEqual(response_delete.status_code, 200) # Redirects to index
        self.assertIn(b'Group "Deletable Group" has been deleted successfully.', response_delete.data)

        self.assertIsNone(Group.query.get(group.id)) # Group deleted
        self.assertFalse(os.path.exists(os.path.join(self.group_images_path, group_image_filename))) # Image deleted
        self.assertEqual(GroupMembership.query.filter_by(group_id=group.id).count(), 0) # Memberships deleted

        db.session.refresh(post) # Refresh post from DB
        self.assertIsNone(post.group_id) # Post's group_id nullified
        self._logout()

    def test_notification_new_group_post(self):
        # u1 creates group, u2 joins
        self._login(self.u1.email, 'password')
        self._create_group("Notify Group Post", "NGP Desc")
        group = Group.query.filter_by(name="Notify Group Post").first()
        self._logout()

        self._login(self.u2.email, 'password')
        self.client.post(f'/group/{group.id}/join', follow_redirects=True)
        self._logout()

        # u1 posts in the group
        self._create_post_in_group(self.u1.email, 'password', "Notification test post", group.id)
        post = Post.query.filter_by(body="Notification test post").first()

        # Check notification for u2
        notification_u2 = Notification.query.filter_by(recipient_id=self.u2.id, type='new_group_post').first()
        self.assertIsNotNone(notification_u2)
        self.assertEqual(notification_u2.actor_id, self.u1.id)
        self.assertEqual(notification_u2.related_post_id, post.id)
        self.assertEqual(notification_u2.related_group_id, group.id)

        # Check no notification for u1 (author)
        notification_u1 = Notification.query.filter_by(recipient_id=self.u1.id, type='new_group_post').first()
        self.assertIsNone(notification_u1)

        # Simulate u2 viewing notifications
        self._login(self.u2.email, 'password')
        response_notifs = self.client.get('/notifications')
        expected_link_text = f'<a href="/group/{group.id}#post-{post.id}">Notification test post'
        self.assertIn(bytes(f'{self.u1.username}</a>\n                            posted\n                            \n                                "{expected_link_text}', 'utf-8'), response_notifs.data)
        self.assertIn(bytes(f'in group <a href="/group/{group.id}">Notify Group Post</a>', 'utf-8'), response_notifs.data)
        self._logout()

    def test_notification_user_joined_group(self):
        # u1 (admin) creates group
        self._login(self.u1.email, 'password')
        self._create_group("Notify Join Group", "NJG Desc")
        group = Group.query.filter_by(name="Notify Join Group").first()
        self._logout()

        # u2 joins the group
        self._login(self.u2.email, 'password')
        self.client.post(f'/group/{group.id}/join', follow_redirects=True)
        self._logout()

        # Check notification for u1 (admin)
        notification_u1 = Notification.query.filter_by(recipient_id=self.u1.id, type='user_joined_group').first()
        self.assertIsNotNone(notification_u1)
        self.assertEqual(notification_u1.actor_id, self.u2.id) # u2 joined
        self.assertEqual(notification_u1.related_group_id, group.id)

        # Simulate u1 viewing notifications
        self._login(self.u1.email, 'password')
        response_notifs = self.client.get('/notifications')
        self.assertIn(bytes(f'{self.u2.username}</a>\n                            joined your group <a href="/group/{group.id}">Notify Join Group</a>', 'utf-8'), response_notifs.data)
        self._logout()

if __name__ == '__main__':
    unittest.main(verbosity=2)
