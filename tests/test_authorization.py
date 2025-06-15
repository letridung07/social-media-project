import unittest
from app import create_app, db
from app.models import User, Post # Add other models as needed for resource tests
from config import TestingConfig

class AuthorizationTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # Create users: one regular, one admin
        self.user_regular = User(username='reguser', email='reg@example.com', is_admin=False)
        self.user_regular.set_password('password123')

        self.user_admin = User(username='adminuser', email='admin@example.com', is_admin=True)
        self.user_admin.set_password('adminpass')

        # Create a resource owned by user_regular
        self.post_by_regular = Post(body="Regular user's post", author=self.user_regular)

        db.session.add_all([self.user_regular, self.user_admin, self.post_by_regular])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.app.post('/login', data=dict(email=email, password=password), follow_redirects=True)

    def _logout(self):
        return self.app.get('/logout', follow_redirects=True)

    # Test 1: Unauthenticated access to protected page
    def test_unauthenticated_access_to_edit_profile(self):
        response = self.app.get('/edit_profile', follow_redirects=False) # Check actual redirect
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/login' in response.location) # Should redirect to login

    # Test 2: Non-admin access to admin page
    def test_non_admin_access_to_admin_dashboard(self):
        self._login('reg@example.com', 'password123') # Login as regular user
        response = self.app.get('/admin/', follow_redirects=False) # Example admin route
        # Expecting a redirect to index (or a 403 if preferred, current admin_required redirects)
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/index' in response.location or '/' == response.location) # admin_required redirects to main.index

        response_followed = self.app.get('/admin/', follow_redirects=True)
        self.assertIn(b"You do not have permission to access this page.", response_followed.data)
        self._logout()

    # Test 3: Admin access to admin page
    def test_admin_access_to_admin_dashboard(self):
        self._login('admin@example.com', 'adminpass') # Login as admin user
        response = self.app.get('/admin/virtual_goods', follow_redirects=True) # A specific admin route
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Manage Virtual Goods", response.data) # Check for content from admin page
        self._logout()

    # Test 4: Attempt to edit another user's post (via GET to edit page)
    def test_regular_user_cannot_get_edit_page_for_others_post(self):
        # Create another user and their post
        other_user = User(username='otheruser', email='other@example.com')
        other_user.set_password('otherpass')
        post_by_other = Post(body="Other user's post", author=other_user)
        db.session.add_all([other_user, post_by_other])
        db.session.commit()

        self._login('reg@example.com', 'password123') # Login as regular_user
        response = self.app.get(f'/edit_post/{post_by_other.id}')
        self.assertEqual(response.status_code, 403) # Expect Forbidden
        self._logout()

    # Test 5: Attempt to edit another user's post (via POST to edit page)
    def test_regular_user_cannot_post_edit_for_others_post(self):
        other_user2 = User(username='otheruser2', email='other2@example.com')
        other_user2.set_password('otherpass2')
        post_by_other2 = Post(body="Another other user's post", author=other_user2)
        db.session.add_all([other_user2, post_by_other2])
        db.session.commit()

        self._login('reg@example.com', 'password123') # Login as regular_user
        response = self.app.post(f'/edit_post/{post_by_other2.id}', data={'body': 'malicious edit attempt'}, follow_redirects=True)
        self.assertEqual(response.status_code, 403) # Expect Forbidden

        # Verify the post body was not actually changed
        db.session.refresh(post_by_other2) # Refresh from DB
        self.assertEqual(post_by_other2.body, "Another other user's post")
        self._logout()

if __name__ == '__main__':
    unittest.main()
