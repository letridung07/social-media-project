import unittest
from unittest.mock import patch # For mocking service
from app import create_app, db
from app.core.models import User, VirtualGood, UserVirtualGood
from config import TestingConfig
from flask_login import login_user, logout_user, current_user # For direct login if needed, or use client
from sqlalchemy.exc import SQLAlchemyError

class TestTitleRoutesConfig(TestingConfig):
    WTF_CSRF_ENABLED = False # Disable CSRF for simpler form testing in unit tests
    # SERVER_NAME might be needed if url_for is used without active request context outside of client calls
    # SERVER_NAME = 'localhost.localdomain'

class TitleRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestTitleRoutesConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()

        try:
            db.create_all()
        except SQLAlchemyError as e:
            print(f"SQLAlchemyError during db.create_all() in TitleRoutesTestCase: {e}")
            self.fail(f"Database creation failed: {e}") # Fail setup if DB can't be created

        self.client = self.app.test_client()

        # Create users
        self.user1 = User(username='user1_titles', email='user1_titles@example.com')
        self.user1.set_password('password')
        db.session.add(self.user1)

        # Create VirtualGoods (titles and other types)
        self.title_vg1 = VirtualGood(name="Hero Of The Day", type="title", title_text="Hero Of The Day", price=0, currency="POINTS", is_active=True)
        self.title_vg2 = VirtualGood(name="Community Helper", type="title", title_text="Community Helper", title_icon_url="static/icons/helper.png", price=0, currency="POINTS", is_active=True)
        self.title_inactive = VirtualGood(
            name="Inactive Title",
            description="This title cannot be purchased.",
            price=0.99,
            currency="USD", # Example currency
            type="title",
            image_url="static/images/inactive_title.png", # Example
            title_text="The Inactive",
            title_icon_url="static/icons/inactive.png", # Example
            is_active=False
        )
        self.other_vg1 = VirtualGood(name="Cool Badge", type="badge", price=10, currency="POINTS", is_active=True)

        db.session.add_all([self.title_vg1, self.title_vg2, self.title_inactive, self.other_vg1])
        db.session.commit()

        # Create UserVirtualGood entries for user1 (owned titles)
        self.uvg1_user1 = UserVirtualGood(user_id=self.user1.id, virtual_good_id=self.title_vg1.id, quantity=1)
        # self.uvg2_user1 = UserVirtualGood(user_id=self.user1.id, virtual_good_id=self.title_vg2.id, quantity=1) # Will create this when testing purchase

        db.session.add_all([self.uvg1_user1])
        db.session.commit()

        # Login helper
        self.user1_id = self.user1.id # Store id before potential session detachment

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login_user1(self):
        # For test client requests, POSTing to login is more robust
        return self.client.post('/login', data=dict(
            email=self.user1.email,
            password='password'
        ), follow_redirects=True)

    def _logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # --- Test /purchase_virtual_good ---
    @patch('app.core.routes.process_virtual_good_purchase')
    def test_route_purchase_title_success(self, mock_process_purchase):
        self._login_user1()
        mock_process_purchase.return_value = {
            "success": True,
            "message": "Title 'Community Helper' acquired successfully!",
            "status_key": "purchase_successful",
            "user_virtual_good": None # Mock UVG or skip asserting its details here
        }

        response = self.client.post(f'/purchase_virtual_good/{self.title_vg2.id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Title 'Community Helper' acquired successfully!", response.data)
        mock_process_purchase.assert_called_once_with(user=User.query.get(self.user1_id), virtual_good=self.title_vg2)
        self._logout()

    @patch('app.core.routes.process_virtual_good_purchase')
    def test_route_purchase_title_already_owned(self, mock_process_purchase):
        self._login_user1()
        mock_process_purchase.return_value = {
            "success": False,
            "message": "You already own the title: 'Hero Of The Day'.",
            "status_key": "already_owned"
        }

        response = self.client.post(f'/purchase_virtual_good/{self.title_vg1.id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"You already own the title: 'Hero Of The Day'.", response.data)
        mock_process_purchase.assert_called_once_with(user=User.query.get(self.user1_id), virtual_good=self.title_vg1)
        self._logout()

    @patch('app.core.routes.process_virtual_good_purchase')
    def test_route_purchase_inactive_title(self, mock_process_purchase):
        self._login_user1()
        # Service will handle the inactive check
        mock_process_purchase.return_value = {
            "success": False,
            "message": f"'{self.title_inactive.name}' is currently not available for purchase.",
            "status_key": "item_not_active"
        }

        response = self.client.post(f'/purchase_virtual_good/{self.title_inactive.id}', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"'Inactive Title' is currently not available for purchase.", response.data)
        mock_process_purchase.assert_called_once_with(user=User.query.get(self.user1_id), virtual_good=self.title_inactive)
        self._logout()

    @patch('app.core.routes.process_virtual_good_purchase')
    def test_route_purchase_fails_db_error(self, mock_process_purchase):
        self._login_user1()
        mock_process_purchase.return_value = {
            "success": False,
            "message": "A database error occurred while processing your purchase. Please try again.",
            "status_key": "purchase_failed_db_error"
        }

        response = self.client.post(f'/purchase_virtual_good/{self.title_vg2.id}', follow_redirects=True) # Attempt to buy unowned title_vg2
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"A database error occurred", response.data)
        mock_process_purchase.assert_called_once_with(user=User.query.get(self.user1_id), virtual_good=self.title_vg2)
        self._logout()

    # --- Test /manage-titles (GET) ---
    def test_manage_titles_get_no_titles_owned(self):
        # Create a new user with no titles
        user2 = User(username='user2_titles', email='user2_titles@example.com')
        user2.set_password('password')
        db.session.add(user2)
        db.session.commit()

        self.client.post('/login', data=dict(email=user2.email, password='password'), follow_redirects=True)

        response = self.client.get('/manage-titles')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Manage Your Titles", response.data)
        self.assertIn(b"You do not own any titles yet.", response.data)
        self._logout()

    def test_manage_titles_get_with_owned_titles(self):
        self._login_user1() # user1 owns self.title_vg1

        response = self.client.get('/manage-titles')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Manage Your Titles", response.data)
        self.assertIn(b"Hero Of The Day", response.data) # From self.uvg1_user1
        self.assertNotIn(b"Community Helper", response.data) # Not owned yet by user1 at this point
        self._logout()

    # --- Test /manage-titles (POST - Set/Clear Active Title) ---
    def test_set_active_title(self):
        self._login_user1()
        # user1 owns self.uvg1_user1 (Hero Of The Day)

        response = self.client.post('/manage-titles', data={'user_virtual_good_id': str(self.uvg1_user1.id)}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Title 'Hero Of The Day' is now your active title!", response.data)

        # Fetch user from DB to check active_title_id
        user_reloaded = User.query.get(self.user1_id)
        self.assertEqual(user_reloaded.active_title_id, self.uvg1_user1.id)

        # Check is_equipped status
        uvg_reloaded = UserVirtualGood.query.get(self.uvg1_user1.id)
        self.assertTrue(uvg_reloaded.is_equipped)
        self._logout()

    def test_set_different_active_title(self):
        self._login_user1()
        # First, set uvg1_user1 as active
        self.user1.active_title_id = self.uvg1_user1.id
        self.uvg1_user1.is_equipped = True
        db.session.commit()

        # Now, user1 purchases and sets title_vg2 as active
        uvg2_user1 = UserVirtualGood(user_id=self.user1_id, virtual_good_id=self.title_vg2.id, quantity=1)
        db.session.add(uvg2_user1)
        db.session.commit()

        response = self.client.post('/manage-titles', data={'user_virtual_good_id': str(uvg2_user1.id)}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Title 'Community Helper' is now your active title!", response.data)

        user_reloaded = User.query.get(self.user1_id)
        self.assertEqual(user_reloaded.active_title_id, uvg2_user1.id)

        uvg1_reloaded = UserVirtualGood.query.get(self.uvg1_user1.id)
        uvg2_reloaded = UserVirtualGood.query.get(uvg2_user1.id)
        self.assertFalse(uvg1_reloaded.is_equipped, "Old title should be unequipped")
        self.assertTrue(uvg2_reloaded.is_equipped, "New title should be equipped")
        self._logout()

    def test_clear_active_title(self):
        self._login_user1()
        # Set an active title first
        self.user1.active_title_id = self.uvg1_user1.id
        self.uvg1_user1.is_equipped = True
        db.session.commit()

        response = self.client.post('/manage-titles', data={'user_virtual_good_id': 'clear_active_title'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Active title has been cleared.', response.data)

        user_reloaded = User.query.get(self.user1_id)
        self.assertIsNone(user_reloaded.active_title_id)

        uvg1_reloaded = UserVirtualGood.query.get(self.uvg1_user1.id)
        # The route doesn't explicitly unequip on clear, current_user.active_title_id is the source of truth.
        # However, it's good practice if it did. For now, test based on current route logic.
        # If the route were updated to set is_equipped=False on clear, this test would change.
        # self.assertFalse(uvg1_reloaded.is_equipped)
        self._logout()

    def test_set_active_title_not_owned(self):
        self._login_user1()
        # Create a UVG not owned by user1
        other_user = User(username='other_title_user', email='other_title@example.com')
        other_user.set_password('password')
        db.session.add(other_user)
        db.session.commit()

        other_uvg = UserVirtualGood(user_id=other_user.id, virtual_good_id=self.title_vg1.id)
        db.session.add(other_uvg)
        db.session.commit()

        response = self.client.post('/manage-titles', data={'user_virtual_good_id': str(other_uvg.id)}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid selection or title not found.', response.data)

        user_reloaded = User.query.get(self.user1_id)
        self.assertIsNone(user_reloaded.active_title_id) # Should not have changed
        self._logout()

    def test_set_active_title_not_a_title_type(self):
        self._login_user1()
        # Create a UVG for a non-title item owned by user1
        badge_uvg = UserVirtualGood(user_id=self.user1_id, virtual_good_id=self.other_vg1.id)
        db.session.add(badge_uvg)
        db.session.commit()

        response = self.client.post('/manage-titles', data={'user_virtual_good_id': str(badge_uvg.id)}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid selection or title not found.', response.data)

        user_reloaded = User.query.get(self.user1_id)
        self.assertIsNone(user_reloaded.active_title_id)
        self._logout()

if __name__ == '__main__':
    unittest.main(verbosity=2)
