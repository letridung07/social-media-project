import unittest
from app import create_app, db
from app.core.models import User, Group, GroupMembership, DiscussionThread, ThreadReply
from config import TestingConfig

class DiscussionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create users
        self.u1 = User(username='user1', email='user1@example.com')
        self.u1.set_password('password')
        self.u2 = User(username='user2', email='user2@example.com')
        self.u2.set_password('password')
        db.session.add_all([self.u1, self.u2])
        db.session.commit()

        # Create group
        self.group = Group(name='Test Group', description='A group for testing discussions', creator_id=self.u1.id)
        db.session.add(self.group)
        db.session.commit()

        # Add users to group
        self.gm1 = GroupMembership(user_id=self.u1.id, group_id=self.group.id, role='admin')
        self.gm2 = GroupMembership(user_id=self.u2.id, group_id=self.group.id, role='member')
        db.session.add_all([self.gm1, self.gm2])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.client.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_create_thread(self):
        self._login('user1@example.com', 'password')
        response = self.client.post(f'/group/{self.group.id}/thread/create', data={
            'title': 'Test Thread',
            'content': 'This is a test thread.'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Thread created successfully!', response.data)
        thread = DiscussionThread.query.filter_by(title='Test Thread').first()
        self.assertIsNotNone(thread)
        self.assertEqual(thread.group_id, self.group.id)
        self.assertEqual(thread.user_id, self.u1.id)
        self._logout()

    def test_view_thread(self):
        # Create a thread first
        thread = DiscussionThread(title='Viewable Thread', content='Content', author=self.u1, group=self.group)
        db.session.add(thread)
        db.session.commit()

        self._login('user2@example.com', 'password')
        response = self.client.get(f'/group/{self.group.id}/thread/{thread.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Viewable Thread', response.data)
        self.assertIn(b'Content', response.data)
        self._logout()

    def test_post_reply(self):
        # Create a thread first
        thread = DiscussionThread(title='Reply Thread', content='Content', author=self.u1, group=self.group)
        db.session.add(thread)
        db.session.commit()

        self._login('user2@example.com', 'password')
        response = self.client.post(f'/group/{self.group.id}/thread/{thread.id}/reply', data={
            'content': 'This is a reply.'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Your reply has been posted.', response.data)
        reply = ThreadReply.query.filter_by(content='This is a reply.').first()
        self.assertIsNotNone(reply)
        self.assertEqual(reply.thread_id, thread.id)
        self.assertEqual(reply.user_id, self.u2.id)
        self._logout()

    def test_non_member_cannot_create_thread(self):
        # u3 is not a member of the group
        u3 = User(username='user3', email='user3@example.com')
        u3.set_password('password')
        db.session.add(u3)
        db.session.commit()

        self._login('user3@example.com', 'password')
        response = self.client.post(f'/group/{self.group.id}/thread/create', data={
            'title': 'Illegal Thread',
            'content': 'This should not be created.'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You must be a member of the group to create a thread.', response.data)
        self.assertIsNone(DiscussionThread.query.filter_by(title='Illegal Thread').first())
        self._logout()

    def test_non_member_cannot_reply(self):
        # Create a thread first
        thread = DiscussionThread(title='Reply Thread', content='Content', author=self.u1, group=self.group)
        db.session.add(thread)
        db.session.commit()

        # u3 is not a member of the group
        u3 = User(username='user3', email='user3@example.com')
        u3.set_password('password')
        db.session.add(u3)
        db.session.commit()

        self._login('user3@example.com', 'password')
        response = self.client.post(f'/group/{self.group.id}/thread/{thread.id}/reply', data={
            'content': 'This is an illegal reply.'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You must be a member of the group to reply.', response.data)
        self.assertIsNone(ThreadReply.query.filter_by(content='This is an illegal reply.').first())
        self._logout()

if __name__ == '__main__':
    unittest.main(verbosity=2)
