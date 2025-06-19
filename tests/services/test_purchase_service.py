import unittest
from unittest.mock import patch
from app import create_app, db
from app.core.models import User, VirtualGood, UserVirtualGood, UserPoints, ActivityLog # Added UserPoints, ActivityLog
from app.services.purchase_service import process_virtual_good_purchase
from config import TestingConfig
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone # Import for checking purchase_date
from app.utils.helpers import get_current_utc


class TestPurchaseServiceConfig(TestingConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Ensure in-memory DB for tests
    TESTING = True
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost.localdomain'

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
        db.session.add(self.user1)

        # Create another user for different scenarios if needed
        self.user2 = User(username='user2_service_test', email='user2service@example.com')
        self.user2.set_password('password123')
        db.session.add(self.user2)

        db.session.commit() # Commit users first to get IDs

        # Create VirtualGoods
        self.title_active_points = VirtualGood(name="Active Title Points", type="title", title_text="The Active Pointer", price=0, currency="USD", point_price=100, is_active=True)
        self.title_active_currency = VirtualGood(name="Active Title Currency", type="title", title_text="The Active Cash", price=10, currency="USD", point_price=None, is_active=True)
        self.title_inactive = VirtualGood(name="Inactive Title", type="title", title_text="The Sleeping One", price=10, currency="POINTS", is_active=False) # Original had POINTS, kept for now
        self.title_owned = VirtualGood(name="Owned Title", type="title", title_text="The Possessed One", price=10, currency="USD", is_active=True) # Assuming this is currency based for original test
        self.badge_active_points = VirtualGood(name="Active Badge Points", type="badge", price=0, currency="USD", point_price=50, is_active=True)

        db.session.add_all([self.title_active_points, self.title_active_currency, self.title_inactive, self.title_owned, self.badge_active_points])
        db.session.commit()

        # Pre-assign one title to user1 (for already_owned test)
        self.owned_uvg = UserVirtualGood(user_id=self.user1.id, virtual_good_id=self.title_owned.id)
        db.session.add(self.owned_uvg)

        # Setup UserPoints for user1
        self.user1_points = UserPoints(user_id=self.user1.id, points=1000)
        db.session.add(self.user1_points)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # --- Existing Tests (adapted slightly for clarity/consistency if needed) ---
    def test_purchase_title_success_currency(self):
        """Test successful purchase of an unowned active title with currency (original test)."""
        result = process_virtual_good_purchase(user=self.user2, virtual_good=self.title_active_currency) # Use user2 without points for this

        self.assertTrue(result["success"])
        self.assertEqual(result["status_key"], "purchase_successful")
        self.assertEqual(result["message"], f"'{self.title_active_currency.name}' acquired successfully!")
        self.assertIsNotNone(result["user_virtual_good"])
        self.assertEqual(result["user_virtual_good"].virtual_good_id, self.title_active_currency.id)
        self.assertEqual(result["user_virtual_good"].user_id, self.user2.id)

        uvg_from_db = UserVirtualGood.query.get(result["user_virtual_good"].id)
        self.assertIsNotNone(uvg_from_db)

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

    # --- New Test Cases for Point-Based Purchases ---
    def test_successful_purchase_with_points(self):
        initial_points = self.user1_points.points
        initial_activity_log_count = ActivityLog.query.filter_by(user_id=self.user1.id).count()

        result = process_virtual_good_purchase(self.user1, self.title_active_points)

        self.assertTrue(result["success"])
        self.assertEqual(result["status_key"], "purchase_successful")
        self.assertIsNotNone(result["user_virtual_good"])
        self.assertEqual(result["message"], f"'{self.title_active_points.name}' acquired successfully with points!")

        uvg_record = UserVirtualGood.query.filter_by(user_id=self.user1.id, virtual_good_id=self.title_active_points.id).first()
        self.assertIsNotNone(uvg_record)
        self.assertEqual(self.user1_points.points, initial_points - self.title_active_points.point_price)

        activity_log_entry = ActivityLog.query.filter_by(user_id=self.user1.id, activity_type='purchase_with_points').first()
        self.assertIsNotNone(activity_log_entry)
        self.assertEqual(activity_log_entry.points_earned, -self.title_active_points.point_price)
        self.assertEqual(activity_log_entry.related_id, self.title_active_points.id)
        self.assertEqual(activity_log_entry.related_item_type, 'virtual_good_purchase')
        self.assertEqual(ActivityLog.query.filter_by(user_id=self.user1.id).count(), initial_activity_log_count + 1)

    def test_insufficient_points(self):
        self.user1_points.points = 50 # Set points lower than item price
        db.session.commit()

        initial_points = self.user1_points.points

        result = process_virtual_good_purchase(self.user1, self.title_active_points) # title_active_points costs 100

        self.assertFalse(result["success"])
        self.assertEqual(result["status_key"], "insufficient_points")
        self.assertIsNone(result["user_virtual_good"])
        self.assertTrue(f"You need {self.title_active_points.point_price} points" in result["message"])
        self.assertTrue(f"but you have {initial_points}" in result["message"])

        uvg_record_count = UserVirtualGood.query.filter_by(user_id=self.user1.id, virtual_good_id=self.title_active_points.id).count()
        self.assertEqual(uvg_record_count, 0)
        self.assertEqual(self.user1_points.points, initial_points) # Points should not change

        activity_log_entry_count = ActivityLog.query.filter_by(user_id=self.user1.id, activity_type='purchase_with_points').count()
        self.assertEqual(activity_log_entry_count, 0)

    def test_insufficient_points_no_userpoints_record(self):
        # user2 has no UserPoints record
        result = process_virtual_good_purchase(self.user2, self.badge_active_points) # badge_active_points costs 50

        self.assertFalse(result["success"])
        self.assertEqual(result["status_key"], "insufficient_points")
        self.assertIsNone(result["user_virtual_good"])
        self.assertTrue(f"You need {self.badge_active_points.point_price} points" in result["message"])
        self.assertTrue("but you have 0" in result["message"])

        uvg_record_count = UserVirtualGood.query.filter_by(user_id=self.user2.id, virtual_good_id=self.badge_active_points.id).count()
        self.assertEqual(uvg_record_count, 0)

    def test_purchase_item_without_point_price_fallback(self):
        # self.title_active_currency has point_price=None
        # user1 has points, but they should not be used
        initial_points = self.user1_points.points
        initial_activity_log_count = ActivityLog.query.filter_by(user_id=self.user1.id, activity_type='purchase_with_points').count()

        result = process_virtual_good_purchase(self.user1, self.title_active_currency)

        self.assertTrue(result["success"])
        self.assertEqual(result["status_key"], "purchase_successful")
        self.assertIsNotNone(result["user_virtual_good"])
        self.assertEqual(result["message"], f"'{self.title_active_currency.name}' acquired successfully!") # No "with points"

        uvg_record = UserVirtualGood.query.filter_by(user_id=self.user1.id, virtual_good_id=self.title_active_currency.id).first()
        self.assertIsNotNone(uvg_record)

        # Assert points did not change
        self.assertEqual(self.user1_points.points, initial_points)
        # Assert no point-related activity log was created
        final_activity_log_count = ActivityLog.query.filter_by(user_id=self.user1.id, activity_type='purchase_with_points').count()
        self.assertEqual(final_activity_log_count, initial_activity_log_count)

    # --- Mocked DB Error Tests (from original file, kept for completeness) ---
    @patch('app.services.purchase_service.db.session.commit')
    @patch('app.services.purchase_service.current_app.logger')
    def test_purchase_db_error_on_commit(self, mock_logger, mock_commit):
        mock_commit.side_effect = SQLAlchemyError("Simulated DB commit error")
        # Use user2 and a currency item for this test to avoid point interactions
        result = process_virtual_good_purchase(user=self.user2, virtual_good=self.title_active_currency)

        self.assertFalse(result["success"])
        self.assertEqual(result["status_key"], "purchase_failed_db_error")
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        self.assertTrue(kwargs.get('exc_info'))
        uvg_check = UserVirtualGood.query.filter_by(user_id=self.user2.id, virtual_good_id=self.title_active_currency.id).first()
        self.assertIsNone(uvg_check)

    @patch('app.services.purchase_service.db.session.add')
    @patch('app.services.purchase_service.current_app.logger')
    def test_purchase_db_error_on_add(self, mock_logger, mock_add):
        mock_add.side_effect = SQLAlchemyError("Simulated DB add error")
        # Use user2 and a currency item for this test
        result = process_virtual_good_purchase(user=self.user2, virtual_good=self.title_active_currency)

        self.assertFalse(result["success"])
        # The error happens during the points deduction's db.session.add or the UVG's db.session.add
        # If it's during points deduction, status_key might be purchase_failed_db_error (if that part is reached and fails on add)
        # If it's during UVG add, it's definitely purchase_failed_db_error.
        # The current structure of process_virtual_good_purchase puts points deduction before UVG creation.
        # If point_price is None, it skips point logic.
        # Let's test with a points item to ensure the points logic's add is also covered, or a non-points item.
        # For this test, using title_active_currency (no point_price) means error happens on adding UserVirtualGood.

        self.assertEqual(result["status_key"], "purchase_failed_db_error")
        self.assertIn("database error occurred", result["message"])
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        self.assertTrue(kwargs.get('exc_info'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
