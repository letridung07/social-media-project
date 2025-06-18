import unittest
from unittest.mock import patch
from app import create_app, db
from app.core.models import User, VirtualGood, UserVirtualGood
from app.services.purchase_service import process_virtual_good_purchase
from config import TestingConfig
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone # Import for checking purchase_date

class TestPurchaseServiceConfig(TestingConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost.localdomain' # For url_for in some contexts, though not strictly needed for service tests

class PurchaseServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestPurchaseServiceConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()

        try:
            db.create_all()
        except SQLAlchemyError as e:
            self.fail(f"Database creation failed in PurchaseServiceTestCase: {e}")

        # Create users
        self.user1 = User(username='user_service_test', email='userservice@example.com')
        self.user1.set_password('password')

        # Create VirtualGoods
        self.title_active = VirtualGood(name="Active Title", type="title", title_text="The Active One", price=10, currency="POINTS", is_active=True)
        self.title_inactive = VirtualGood(name="Inactive Title", type="title", title_text="The Sleeping One", price=10, currency="POINTS", is_active=False)
        self.title_owned = VirtualGood(name="Owned Title", type="title", title_text="The Possessed One", price=10, currency="POINTS", is_active=True)
        self.badge_active = VirtualGood(name="Active Badge", type="badge", price=5, currency="POINTS", is_active=True)

        db.session.add_all([self.user1, self.title_active, self.title_inactive, self.title_owned, self.badge_active])
        db.session.commit()

        # Pre-assign one title to user1
        self.owned_uvg = UserVirtualGood(user_id=self.user1.id, virtual_good_id=self.title_owned.id)
        db.session.add(self.owned_uvg)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_purchase_title_success(self):
        """Test successful purchase of an unowned active title."""
        result = process_virtual_good_purchase(user=self.user1, virtual_good=self.title_active)

        self.assertTrue(result["success"])
        self.assertEqual(result["status_key"], "purchase_successful")
        self.assertIn("acquired successfully", result["message"])
        self.assertIsNotNone(result["user_virtual_good"])
        self.assertEqual(result["user_virtual_good"].virtual_good_id, self.title_active.id)
        self.assertEqual(result["user_virtual_good"].user_id, self.user1.id)
        self.assertFalse(result["user_virtual_good"].is_equipped)

        # Verify in DB
        uvg_from_db = UserVirtualGood.query.get(result["user_virtual_good"].id)
        self.assertIsNotNone(uvg_from_db)
        self.assertIsNotNone(uvg_from_db.purchase_date)

    def test_purchase_title_already_owned(self):
        """Test purchasing a title already owned by the user."""
        result = process_virtual_good_purchase(user=self.user1, virtual_good=self.title_owned)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_key"], "already_owned")
        self.assertIn("You already own the title", result["message"])
        self.assertEqual(result["user_virtual_good"].id, self.owned_uvg.id)

    def test_purchase_inactive_good(self):
        """Test purchasing an inactive virtual good."""
        result = process_virtual_good_purchase(user=self.user1, virtual_good=self.title_inactive)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_key"], "item_not_active")
        self.assertIn("not available for purchase", result["message"])

    @patch('app.services.purchase_service.db.session.commit')
    @patch('app.services.purchase_service.current_app.logger')
    def test_purchase_db_error_on_commit(self, mock_logger, mock_commit):
        """Test handling of SQLAlchemyError during db.session.commit()."""
        mock_commit.side_effect = SQLAlchemyError("Simulated DB commit error")

        result = process_virtual_good_purchase(user=self.user1, virtual_good=self.title_active)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_key"], "purchase_failed_db_error")
        self.assertIn("database error occurred", result["message"])
        mock_logger.error.assert_called_once()
        # Check that exc_info=True was used in logger call
        args, kwargs = mock_logger.error.call_args
        self.assertTrue(kwargs.get('exc_info'))

        # Verify UserVirtualGood was not actually created or was rolled back
        uvg_check = UserVirtualGood.query.filter_by(user_id=self.user1.id, virtual_good_id=self.title_active.id).first()
        self.assertIsNone(uvg_check)

    @patch('app.services.purchase_service.db.session.add')
    @patch('app.services.purchase_service.current_app.logger')
    def test_purchase_db_error_on_add(self, mock_logger, mock_add):
        """Test handling of SQLAlchemyError during db.session.add()."""
        mock_add.side_effect = SQLAlchemyError("Simulated DB add error")

        result = process_virtual_good_purchase(user=self.user1, virtual_good=self.title_active)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_key"], "purchase_failed_db_error") # Expecting this key due to SQLAlchemyError
        self.assertIn("database error occurred", result["message"])
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        self.assertTrue(kwargs.get('exc_info'))


    def test_purchase_non_title_good_success(self):
        """Test successful purchase of an active non-title good."""
        result = process_virtual_good_purchase(user=self.user1, virtual_good=self.badge_active)

        self.assertTrue(result["success"])
        self.assertEqual(result["status_key"], "purchase_successful")
        self.assertIn("acquired successfully", result["message"])
        self.assertIsNotNone(result["user_virtual_good"])
        self.assertEqual(result["user_virtual_good"].virtual_good_id, self.badge_active.id)

        uvg_from_db = UserVirtualGood.query.get(result["user_virtual_good"].id)
        self.assertIsNotNone(uvg_from_db)

    def test_purchase_non_title_good_already_owned(self):
        """Test purchasing a non-title good that is already owned."""
        # self.badge_active is an active, non-title good.
        # First, ensure user1 owns it.
        owned_badge_uvg = UserVirtualGood(user_id=self.user1.id, virtual_good_id=self.badge_active.id, quantity=1)
        db.session.add(owned_badge_uvg)
        db.session.commit()
        self.assertIsNotNone(owned_badge_uvg.id)

        # Attempt to "purchase" it again
        result = process_virtual_good_purchase(user=self.user1, virtual_good=self.badge_active)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_key"], "already_owned_generic")
        self.assertIn("You already have", result["message"])
        self.assertEqual(result["user_virtual_good"].id, owned_badge_uvg.id)

        # Verify the quantity hasn't changed and no new entry was made
        uvg_count = UserVirtualGood.query.filter_by(user_id=self.user1.id, virtual_good_id=self.badge_active.id).count()
        self.assertEqual(uvg_count, 1)

        uvg_from_db = UserVirtualGood.query.get(owned_badge_uvg.id)
        self.assertEqual(uvg_from_db.quantity, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
