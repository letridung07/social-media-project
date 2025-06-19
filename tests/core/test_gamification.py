"""
Tests for the gamification points and badge system.

This module includes tests for:
- Awarding points to users (`award_points` utility).
- Integration of point awarding in various user actions (e.g., creating posts, daily logins).
- Seeding of initial badges into the database (`seed_badges` utility).
- Logic for checking and awarding badges based on user achievements (`check_and_award_badges` utility).
- Ensuring badges are awarded correctly based on criteria and not awarded multiple times.
"""
import pytest
from app import create_app, db, socketio
from flask import current_app # For logger mocking
from app.core.models import User, Post, Reaction, UserPoints, Badge, ActivityLog, Notification, Story, Poll, Article, AudioPost, Comment, Group, Event, VirtualGood, UserVirtualGood # Add all models used in badge criteria
from app.utils.helpers import award_points
from app.utils.gamification_utils import seed_badges, check_and_award_badges, INITIAL_BADGES, LEVEL_THRESHOLDS, get_leaderboard
from sqlalchemy.exc import SQLAlchemyError # For simulating DB error
from sqlalchemy import desc # For leaderboard sorting
from config import TestingConfig
from datetime import datetime, timedelta, timezone, date # Added date for mocking
from unittest.mock import patch # For mocking socketio.emit and datetime

# PyTest fixture for application context
@pytest.fixture(scope='module')
def test_client():
    flask_app = create_app(TestingConfig)
    testing_client = flask_app.test_client()

    # Establish an application context before running the tests.
    ctx = flask_app.app_context()
    ctx.push()

    yield testing_client  # this is where the testing happens!

    ctx.pop()

# PyTest fixture for database initialization
@pytest.fixture(scope='module')
def init_database(test_client):
    db.create_all()

    yield db  # this is where the testing happens!

    db.session.remove()
    db.drop_all()

# PyTest fixture for a new user, automatically used in tests
@pytest.fixture(scope='function') # function scope for clean user each test
def new_user(init_database):
    user = User(username='testuser', email='test@example.com')
    user.set_password('password')
    db.session.add(user)
    db.session.commit()
    return user

# PyTest fixture for another user
@pytest.fixture(scope='function')
def other_user(init_database):
    user = User(username='otheruser', email='other@example.com')
    user.set_password('password')
    db.session.add(user)
    db.session.commit()
    return user

# Basic test to ensure fixtures work
def test_app_exists(test_client):
    assert test_client is not None

def test_db_exists(init_database):
    assert init_database is not None

# Placeholder for actual tests
def test_example():
    assert True

# --- Tests for award_points ---
def test_award_points_first_time(init_database, new_user):
    """
    Verify UserPoints and ActivityLog creation when a user receives points for the first time.
    Ensures `check_and_award_badges` is called.
    """
    assert new_user.points is None # Initially no UserPoints record

    # Mock check_and_award_badges to isolate award_points logic
    with patch('app.utils.helpers.check_and_award_badges') as mock_check_badges:
        award_points(new_user, 'test_action', 10)
        db.session.commit() # award_points doesn't commit, test needs to commit
        mock_check_badges.assert_called_once_with(new_user)

    user_points = UserPoints.query.filter_by(user_id=new_user.id).first()
    assert user_points is not None
    assert user_points.points == 10

    activity_log = ActivityLog.query.filter_by(user_id=new_user.id, activity_type='test_action').first()
    assert activity_log is not None
    assert activity_log.points_earned == 10
    assert activity_log.user_id == new_user.id

def test_award_points_additional(init_database, new_user):
    """
    Test that awarding additional points correctly updates the UserPoints record
    and creates a new ActivityLog entry.
    """
    # Initial points
    with patch('app.utils.helpers.check_and_award_badges'): # Mock to prevent side effects
        award_points(new_user, 'initial_action', 10)
        db.session.commit()

    # Additional points
    with patch('app.utils.helpers.check_and_award_badges') as mock_check_badges_additional:
        award_points(new_user, 'additional_action', 5)
        db.session.commit()
        mock_check_badges_additional.assert_called_once_with(new_user)

    user_points = UserPoints.query.filter_by(user_id=new_user.id).first()
    assert user_points is not None
    assert user_points.points == 15 # 10 + 5

    additional_log = ActivityLog.query.filter_by(user_id=new_user.id, activity_type='additional_action').first()
    assert additional_log is not None
    assert additional_log.points_earned == 5
    assert ActivityLog.query.filter_by(user_id=new_user.id).count() == 2

def test_award_points_with_related_item(init_database, new_user):
    """
    Test that `award_points` correctly logs `related_id` and `related_item_type`
    when a `related_item` is provided.
    """
    post = Post(body="Test post", author=new_user)
    db.session.add(post)
    db.session.commit()

    with patch('app.utils.helpers.check_and_award_badges'):
        award_points(new_user, 'post_related_action', 7, related_item=post)
        db.session.commit()

    activity_log = ActivityLog.query.filter_by(user_id=new_user.id, activity_type='post_related_action').first()
    assert activity_log is not None
    assert activity_log.related_id == post.id
    assert activity_log.related_item_type == 'post' # Based on __class__.__name__.lower()

# --- Tests for Route Integrations (Points) ---

# Helper fixture to log in a user
@pytest.fixture(scope='function')
def logged_in_user(test_client, new_user):
    with test_client.session_transaction() as sess:
        sess['user_id'] = new_user.id
        sess['_fresh'] = True # Mark session as fresh (needed by some Flask-Login features)
    # Simulate current_user for award_points direct calls if not going through routes
    # For route tests, test_client.post/get handles this if login is simulated correctly.
    # However, award_points itself uses current_user.is_authenticated if user is current_user
    # This setup is more for direct calls. For route tests, the login should make current_user available.
    # For now, we rely on test_client to handle session for route tests.
    return new_user


def test_create_text_post_awards_points(test_client, logged_in_user, init_database):
    """
    Test that creating a text post through the route awards the correct number of points (10).
    """
    # Log in the user for the test client session
    # This often requires a POST to the login route if not using a simpler session manipulation
    # For simplicity, assuming logged_in_user fixture sets up a usable session for current_user
    # If direct User object is needed, logged_in_user provides it.

    # To truly simulate login for client requests:
    with test_client.post('/login', data=dict(email='test@example.com', password='password'), follow_redirects=True):
        pass # Simulate login

    initial_points = UserPoints.query.filter_by(user_id=logged_in_user.id).first()
    initial_points_value = initial_points.points if initial_points else 0

    # Create a post
    with patch('app.utils.helpers.check_and_award_badges'): # Mock badge check
        response = test_client.post('/create_post', data={
            'body': 'This is a test post content.',
            'privacy_level': 'PUBLIC'
            # Add other required form fields if any, e.g., csrf_token if not disabled in testing
        }, follow_redirects=True)
    assert response.status_code == 200 # Assuming redirect to index or group page

    updated_points = UserPoints.query.filter_by(user_id=logged_in_user.id).first()
    assert updated_points is not None
    assert updated_points.points == initial_points_value + 10 # 10 points for text post

    activity_log = ActivityLog.query.filter_by(user_id=logged_in_user.id, activity_type='create_post').order_by(ActivityLog.timestamp.desc()).first()
    assert activity_log is not None
    assert activity_log.points_earned == 10

def test_daily_login_awards_points_once(test_client, new_user, init_database):
    """
    Test that points for daily login are awarded only once per day.
    Simulates logins on the same day and on a subsequent day.
    """
    # Day 1: First login
    with patch('app.utils.helpers.check_and_award_badges'): # Mock badge check during award_points
        with patch('app.core.routes.datetime') as mock_dt_day1:
            mock_dt_day1.now.return_value = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt_day1.date.return_value = date(2024, 1, 1) # For date comparison
            # Mocking date() on datetime object for when datetime.now().date() is called
            mock_dt_day1.now.return_value.date.return_value = date(2024,1,1)


            # Simulate login via POST request
            test_client.post('/login', data=dict(email=new_user.email, password='password'), follow_redirects=True)

    user_points_day1 = UserPoints.query.filter_by(user_id=new_user.id).first()
    assert user_points_day1 is not None
    assert user_points_day1.points == 5
    assert ActivityLog.query.filter_by(user_id=new_user.id, activity_type='daily_login').count() == 1

    # Day 1: Second login (same day)
    with patch('app.utils.helpers.check_and_award_badges'):
        with patch('app.core.routes.datetime') as mock_dt_day1_again:
            mock_dt_day1_again.now.return_value = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
            mock_dt_day1_again.now.return_value.date.return_value = date(2024,1,1)

            test_client.post('/login', data=dict(email=new_user.email, password='password'), follow_redirects=True)

    user_points_day1_again = UserPoints.query.filter_by(user_id=new_user.id).first()
    assert user_points_day1_again.points == 5 # Points should not change
    assert ActivityLog.query.filter_by(user_id=new_user.id, activity_type='daily_login').count() == 1 # Still one daily_login

    # Day 2: Login on a different day
    with patch('app.utils.helpers.check_and_award_badges'):
        with patch('app.core.routes.datetime') as mock_dt_day2:
            mock_dt_day2.now.return_value = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt_day2.now.return_value.date.return_value = date(2024,1,2)

            test_client.post('/login', data=dict(email=new_user.email, password='password'), follow_redirects=True)

    user_points_day2 = UserPoints.query.filter_by(user_id=new_user.id).first()
    assert user_points_day2.points == 10 # 5 (day1) + 5 (day2)
    assert ActivityLog.query.filter_by(user_id=new_user.id, activity_type='daily_login').count() == 2

# --- Tests for seed_badges ---
def test_seed_badges_populates_empty_table(init_database):
    """
    Test that `seed_badges` correctly populates the Badge table if it's empty.
    """
    # Ensure table is empty
    assert Badge.query.count() == 0
    seed_badges()
    assert Badge.query.count() == len(INITIAL_BADGES)
    # Check a specific badge
    welcome_badge = Badge.query.filter_by(criteria_key='welcome_wagon').first()
    assert welcome_badge is not None
    assert welcome_badge.name == 'Welcome Wagon'

def test_seed_badges_does_not_repopulate(init_database):
    # First seed
    seed_badges()
    initial_count = Badge.query.count()
    assert initial_count == len(INITIAL_BADGES)

    # Try seeding again
    seed_badges()
    assert Badge.query.count() == initial_count # Count should not change

# --- Tests for check_and_award_badges ---

# Mock socketio.emit for these tests
@patch('app.utils.gamification_utils.socketio.emit')
def test_award_first_steps_badge(mock_socketio_emit, init_database, new_user):
    """
    Test that the 'First Steps' badge is awarded when a user makes their first post.
    Verifies ActivityLog, Notification creation, and SocketIO event emission.
    """
    seed_badges() # Ensure badges exist

    # User creates a post
    post = Post(body="My first post!", author=new_user)
    db.session.add(post)
    db.session.commit()

    check_and_award_badges(new_user)
    db.session.commit() # check_and_award_badges might add to session, then commit

    first_steps_badge = Badge.query.filter_by(criteria_key='first_steps').first()
    assert first_steps_badge is not None
    assert first_steps_badge in new_user.badges

    activity_log = ActivityLog.query.filter_by(user_id=new_user.id, activity_type='earn_badge', related_id=first_steps_badge.id).first()
    assert activity_log is not None

    notification = Notification.query.filter_by(recipient_id=new_user.id, type='new_badge').first()
    assert notification is not None

    mock_socketio_emit.assert_called_once()
    args, kwargs = mock_socketio_emit.call_args
    assert args[0] == 'new_notification'
    assert args[1]['type'] == 'new_badge'
    assert args[1]['badge_name'] == 'First Steps'
    assert kwargs['room'] == str(new_user.id)

@patch('app.utils.gamification_utils.socketio.emit')
def test_award_point_collector_badge(mock_socketio_emit, init_database, new_user):
    seed_badges()

    # Give user 100 points (award_points calls check_and_award_badges, so we need to handle that or mock it)
    # For this test, let's directly manipulate UserPoints after an initial award_points call that seeds UserPoints
    with patch('app.utils.helpers.check_and_award_badges'): # Mock inner call from award_points
        award_points(new_user, 'test_points', 10) # Creates UserPoints record
        db.session.commit()

    user_points = UserPoints.query.filter_by(user_id=new_user.id).first()
    user_points.points = 100 # Directly set points
    db.session.add(user_points)
    db.session.commit()

    check_and_award_badges(new_user) # This is the call we are testing
    db.session.commit()

    point_collector_badge = Badge.query.filter_by(criteria_key='point_collector').first()
    assert point_collector_badge is not None
    assert point_collector_badge in new_user.badges
    mock_socketio_emit.assert_called() # Called for point_collector badge

@patch('app.utils.gamification_utils.socketio.emit')
def test_badge_not_awarded_if_criteria_not_met(mock_socketio_emit, init_database, new_user):
    """
    Test that a badge (e.g., 'First Steps') is NOT awarded if the user
    has not met the criteria (e.g., has not made any posts).
    """
    seed_badges()
    # User has no posts
    check_and_award_badges(new_user)
    db.session.commit()

    first_steps_badge = Badge.query.filter_by(criteria_key='first_steps').first()
    assert first_steps_badge not in new_user.badges
    mock_socketio_emit.assert_not_called()

@patch('app.utils.gamification_utils.socketio.emit')
def test_badge_not_awarded_twice(mock_socketio_emit, init_database, new_user):
    """
    Test that a badge is not awarded to a user if they have already earned it.
    Ensures no duplicate ActivityLog or SocketIO events for the same badge.
    """
    seed_badges()
    # Award 'First Steps' badge
    post = Post(body="My first post!", author=new_user)
    db.session.add(post)
    db.session.commit()
    check_and_award_badges(new_user)
    db.session.commit()

    mock_socketio_emit.reset_mock() # Reset mock after first award

    # Call again
    check_and_award_badges(new_user)
    db.session.commit()

    first_steps_badge = Badge.query.filter_by(criteria_key='first_steps').first()
    # Count how many times this specific badge was logged as earned
    activity_log_count = ActivityLog.query.filter_by(user_id=new_user.id, activity_type='earn_badge', related_id=first_steps_badge.id).count()
    assert activity_log_count == 1
    mock_socketio_emit.assert_not_called() # Should not be called for an already awarded badge


@patch('app.utils.gamification_utils.socketio.emit') # Mock socketio for badge notifications
def test_award_first_steps_title_with_badge(mock_badge_socketio_emit, init_database, new_user):
    """
    Test that earning the 'First Steps' badge also awards the corresponding title.
    """
    seed_badges() # Ensure badges exist

    # 1. Create the 'First Steps Title' VirtualGood
    first_steps_title_vg = VirtualGood(
        name="First Steps Title",
        type="title",
        title_text="Newcomer",
        price=0,
        currency="POINTS", # Assuming points or free for awarded titles
        is_active=True
    )
    db.session.add(first_steps_title_vg)
    db.session.commit()
    assert first_steps_title_vg.id is not None, "Failed to create 'First Steps Title' VirtualGood"

    # 2. User creates their first post (criteria for 'First Steps' badge)
    post = Post(body="My very first post!", author=new_user)
    db.session.add(post)
    db.session.commit()

    # 3. Call check_and_award_badges
    check_and_award_badges(new_user)
    # The check_and_award_badges function now commits internally if badges/titles are awarded.

    # 4. Assert 'First Steps' badge is awarded
    first_steps_badge_db = Badge.query.filter_by(criteria_key='first_steps').first()
    assert first_steps_badge_db is not None, "'First Steps' badge not found in DB"
    assert first_steps_badge_db in new_user.badges, "'First Steps' badge not awarded to user"

    # 5. Assert 'First Steps Title' UserVirtualGood is created
    user_title_entry = UserVirtualGood.query.join(VirtualGood).filter(
        UserVirtualGood.user_id == new_user.id,
        VirtualGood.id == first_steps_title_vg.id
    ).first()
    assert user_title_entry is not None, "UserVirtualGood for 'First Steps Title' was not created"
    assert user_title_entry.virtual_good_id == first_steps_title_vg.id
    assert user_title_entry.is_equipped is False, "Newly awarded title should not be automatically equipped"
    assert user_title_entry.quantity == 1

    # 6. Test Idempotency: Call again, ensure no duplicates for title
    initial_uvg_count = UserVirtualGood.query.filter_by(user_id=new_user.id, virtual_good_id=first_steps_title_vg.id).count()

    check_and_award_badges(new_user) # Call again

    final_uvg_count = UserVirtualGood.query.filter_by(user_id=new_user.id, virtual_good_id=first_steps_title_vg.id).count()
    assert final_uvg_count == initial_uvg_count, "Duplicate UserVirtualGood created for title"
    assert final_uvg_count == 1, "UserVirtualGood count for title is not 1 after re-check"


@patch('app.utils.gamification_utils.socketio.emit')
@patch('app.utils.gamification_utils.current_app.logger')
def test_award_first_steps_title_fails_if_vg_not_found(mock_logger, mock_badge_socketio_emit, init_database, new_user, other_user): # Added other_user to avoid interference
    """
    Test that if the 'First Steps Title' VirtualGood doesn't exist,
    the badge is still awarded but the title is not.
    """
    seed_badges()
    # Ensure the specific title VG does NOT exist
    existing_title = VirtualGood.query.filter_by(name="First Steps Title", type="title").first()
    if existing_title:
        # If tests run in non-deterministic order or DB is not perfectly clean, remove it.
        # For more robust testing, ensure this VG is not created by other tests or is cleaned up.
        db.session.delete(existing_title)
        db.session.commit()

    # Use 'other_user' for this test to ensure clean slate regarding UserVirtualGood
    post = Post(body="My first post for no-title test!", author=other_user)
    db.session.add(post)
    db.session.commit()

    check_and_award_badges(other_user)

    # Assert badge is awarded
    first_steps_badge_db = Badge.query.filter_by(criteria_key='first_steps').first()
    assert first_steps_badge_db is not None
    assert first_steps_badge_db in other_user.badges

    # Assert title is NOT awarded
    user_title_entry = UserVirtualGood.query.join(VirtualGood).filter(
        UserVirtualGood.user_id == other_user.id,
        VirtualGood.name == "First Steps Title",
        VirtualGood.type == "title"
    ).first()
    assert user_title_entry is None, "UserVirtualGood title was created even though the VirtualGood for it should not exist"
    mock_logger.warning.assert_called_with("VirtualGood 'First Steps Title' of type 'title' not found. Cannot award title.")


@patch('app.utils.gamification_utils.socketio.emit')
@patch('app.utils.gamification_utils.db.session.add')
@patch('app.utils.gamification_utils.current_app.logger')
def test_award_first_steps_title_logs_error_on_db_exception(mock_logger, mock_db_add, mock_badge_socketio_emit, init_database, new_user):
    """
    Test that if adding UserVirtualGood for a title fails, an error is logged,
    but the badge is still awarded.
    """
    seed_badges()

    # Create the 'First Steps Title' VirtualGood
    first_steps_title_vg = VirtualGood(
        name="First Steps Title", type="title", title_text="Newcomer", price=0, currency="POINTS", is_active=True
    )
    db.session.add(first_steps_title_vg)
    db.session.commit()

    # User creates their first post
    post = Post(body="My first post for db error test!", author=new_user)
    db.session.add(post)
    db.session.commit()

    # Configure db.session.add to raise SQLAlchemyError only when adding UserVirtualGood
    def side_effect_add(instance):
        if isinstance(instance, UserVirtualGood):
            # Ensure we only raise for the specific title to avoid breaking other UVG creations if any
            if instance.virtual_good_id == first_steps_title_vg.id:
                raise SQLAlchemyError("Simulated DB error on UserVirtualGood add")
        # For other instances (like ActivityLog, Notification for the badge), proceed normally
        db.session.expunge(instance) # Remove from session to allow real add by original method if needed
        return db.session.real_add(instance) # type: ignore

    # Store real add method and then patch
    db.session.real_add = db.session.add # type: ignore
    mock_db_add.side_effect = side_effect_add

    check_and_award_badges(new_user)
    # The main commit in check_and_award_badges will likely be rolled back due to the error,
    # but the badge should have been added to the user.badges collection in memory.
    # If the commit inside check_and_award_badges is wrapped in a try-except that rollbacks,
    # then the badge association might also be rolled back. Let's check the current logic.
    # The current logic commits only if newly_awarded_badges_info is populated.
    # The title error happens before the final commit of badge-related items if the title is processed first.

    # Assert badge is awarded (even if title award failed)
    first_steps_badge_db = Badge.query.filter_by(criteria_key='first_steps').first()
    assert first_steps_badge_db is not None
    # Check if the badge is in the user's collection in memory, as commit might have failed or been rolled back
    # For a more robust check, one might need to query the association table if the main commit fails.
    # However, the current structure of check_and_award_badges appends to user.badges
    # and then commits at the end. If the title error causes a rollback before that,
    # then the badge itself might not be committed.
    # The `exc_info=True` implies the exception is caught and handled, allowing other operations to proceed.
    # The current `check_and_award_badges` has its final commit in a try-except block.
    # If the title awarding part (which is within the badge loop) raises an error
    # that isn't caught and handled *within* the title awarding part, it could disrupt the commit.
    # The added try-except around title awarding handles this.

    # We expect the badge to be committed because the error in title awarding is caught.
    db.session.commit() # Re-commit to be sure badge related changes are saved if not rolled back by title error
    assert first_steps_badge_db in User.query.get(new_user.id).badges

    # Assert logger.error was called
    mock_logger.error.assert_called_once()
    args, kwargs = mock_logger.error.call_args
    assert "Error awarding title for 'First Steps' badge" in args[0]
    assert kwargs.get('exc_info') is True

    # Assert title was NOT awarded
    user_title_entry = UserVirtualGood.query.filter_by(
        user_id=new_user.id, virtual_good_id=first_steps_title_vg.id
    ).first()
    assert user_title_entry is None

    # Restore original db.session.add
    db.session.add = db.session.real_add # type: ignore
    delattr(db.session, 'real_add')


# --- Tests for New Level-Based Badges ---

@patch('app.utils.gamification_utils.socketio.emit')
def test_award_level_5_gamer_badge(mock_socketio_emit, init_database, new_user):
    seed_badges() # Ensure all badges, including level-based ones, are in DB

    # Award points to reach Level 5. Level 5 starts at 1000 points.
    # award_points calls update_user_level and check_and_award_badges internally.
    award_points(new_user, 'reach_level_5', 1000)
    db.session.commit()

    gamer_badge = Badge.query.filter_by(criteria_key='level_5_reached').first()
    assert gamer_badge is not None
    assert gamer_badge in new_user.badges

    # Check for 'new_badge' notification for the Gamer badge
    badge_notification = Notification.query.filter_by(
        recipient_id=new_user.id,
        type='new_badge'
        # To be more specific, we might need to check related_id if it's set to badge_id in check_and_award_badges
    ).order_by(Notification.timestamp.desc()).first() # Get the latest one

    # Check if any of the calls to emit was for the Gamer badge
    gamer_badge_emitted = False
    for call_args in mock_socketio_emit.call_args_list:
        args, kwargs = call_args
        if args[0] == 'new_notification' and args[1].get('type') == 'new_badge' and args[1].get('badge_name') == 'Gamer':
            gamer_badge_emitted = True
            break
    assert gamer_badge_emitted

@patch('app.utils.gamification_utils.socketio.emit')
def test_award_level_10_veteran_badge(mock_socketio_emit, init_database, new_user):
    seed_badges()
    # Award points to reach Level 10. Level 10 starts at 25000 points.
    award_points(new_user, 'reach_level_10', 25000)
    db.session.commit()

    veteran_badge = Badge.query.filter_by(criteria_key='level_10_reached').first()
    assert veteran_badge is not None
    assert veteran_badge in new_user.badges

    veteran_badge_emitted = False
    for call_args in mock_socketio_emit.call_args_list:
        args, kwargs = call_args
        if args[0] == 'new_notification' and args[1].get('type') == 'new_badge' and args[1].get('badge_name') == 'Veteran':
            veteran_badge_emitted = True
            break
    assert veteran_badge_emitted

@patch('app.utils.gamification_utils.socketio.emit')
def test_level_badges_not_awarded_prematurely(mock_socketio_emit, init_database, new_user):
    seed_badges()
    # Award points for Level 4 (e.g., 500 points), should not award Level 5 or Level 10 badges.
    # Level 4 is 500-999 points.
    award_points(new_user, 'reach_level_4', 500)
    db.session.commit()

    gamer_badge = Badge.query.filter_by(criteria_key='level_5_reached').first()
    veteran_badge = Badge.query.filter_by(criteria_key='level_10_reached').first()

    assert gamer_badge not in new_user.badges
    assert veteran_badge not in new_user.badges

    # Check that no badge notifications were emitted for these specific badges
    for call_args in mock_socketio_emit.call_args_list:
        args, kwargs = call_args
        if args[0] == 'new_notification' and args[1].get('type') == 'new_badge':
            assert args[1].get('badge_name') != 'Gamer'
            assert args[1].get('badge_name') != 'Veteran'


# --- Tests for Leveling System ---
class TestLevelingSystem:

    @patch('app.utils.gamification_utils.socketio.emit')
    def test_user_levels_up_correctly(self, mock_socketio_emit, init_database, new_user):
        # User starts with 0 points, level 1 (implicitly, UserPoints created by award_points)

        # Award points just below Level 2 threshold (100 points)
        award_points(new_user, 'action1', 90)
        db.session.commit()

        user_points = UserPoints.query.filter_by(user_id=new_user.id).first()
        assert user_points is not None
        assert user_points.points == 90
        assert user_points.level == 1 # Should still be Level 1
        mock_socketio_emit.assert_not_called() # No level up event yet

        # Award more points to cross the threshold for Level 2
        award_points(new_user, 'action2', 15) # Total 105 points
        db.session.commit()

        user_points_updated = UserPoints.query.filter_by(user_id=new_user.id).first()
        assert user_points_updated.points == 105
        assert user_points_updated.level == 2 # Should be Level 2

        # Check for 'level_up' notification
        level_up_notification = Notification.query.filter_by(
            recipient_id=new_user.id,
            type='level_up'
        ).order_by(Notification.timestamp.desc()).first()
        assert level_up_notification is not None

        # Assert socketio.emit was called for level up
        mock_socketio_emit.assert_called_with(
            'new_notification',
            {
                'type': 'level_up',
                'message': "Congratulations! You've reached Level 2!",
                'level': 2,
            },
            room=str(new_user.id)
        )

    @patch('app.utils.gamification_utils.socketio.emit')
    def test_level_up_skipping_thresholds(self, mock_socketio_emit, init_database, new_user):
        # Award 600 points, should take user from Level 1 (default) to Level 4 (500-999 points)
        award_points(new_user, 'massive_points_action', 600)
        db.session.commit()

        user_points = UserPoints.query.filter_by(user_id=new_user.id).first()
        assert user_points is not None
        assert user_points.points == 600
        assert user_points.level == 4 # Based on LEVEL_THRESHOLDS

        # Check notification and socket event for reaching Level 4
        level_up_notification = Notification.query.filter_by(
            recipient_id=new_user.id,
            type='level_up'
        ).order_by(Notification.timestamp.desc()).first()
        assert level_up_notification is not None

        mock_socketio_emit.assert_called_with(
            'new_notification',
            {
                'type': 'level_up',
                'message': "Congratulations! You've reached Level 4!",
                'level': 4,
            },
            room=str(new_user.id)
        )

    @patch('app.utils.gamification_utils.socketio.emit')
    def test_no_level_up_if_not_enough_points(self, mock_socketio_emit, init_database, new_user):
        # Initial points, creates UserPoints object at Level 1
        award_points(new_user, 'action1', 10)
        db.session.commit()

        user_points_initial = UserPoints.query.filter_by(user_id=new_user.id).first()
        assert user_points_initial.level == 1
        mock_socketio_emit.reset_mock() # Reset mock after initial setup if any events fired

        # Add more points, but not enough to level up from Level 1 (threshold is 100 for L2)
        award_points(new_user, 'action2', 50) # Total 60 points
        db.session.commit()

        user_points_updated = UserPoints.query.filter_by(user_id=new_user.id).first()
        assert user_points_updated.points == 60
        assert user_points_updated.level == 1 # Still Level 1

        # Assert no 'level_up' notification or socket event was triggered for this second action
        # Querying for notifications specifically for this action is tricky without more context.
        # Instead, ensure no *new* level_up notification was created beyond any potential initial one.
        # For this test, since we reset_mock, we can assert not_called.
        mock_socketio_emit.assert_not_called()

        level_up_notifications_after_action2 = Notification.query.filter_by(
            recipient_id=new_user.id,
            type='level_up',
            # Ideally, filter by timestamp if possible, or check count if we know initial state.
            # For this test, if initial action didn't level up, count should be 0.
        ).count()
        assert level_up_notifications_after_action2 == 0 # Assuming action1 didn't cause level up


# --- Tests for Leaderboard Logic ---
class TestLeaderboards:

    def test_leaderboard_all_time(self, init_database, new_user, other_user):
        # Create a third user for more variety
        user3 = User(username='user3', email='user3@example.com')
        user3.set_password('password')
        db.session.add(user3)
        db.session.commit()

        # Assign points directly to UserPoints (or create UserPoints if they don't exist)
        # UserPoints are typically created when award_points is first called for a user.
        # To ensure UserPoints records exist:
        award_points(new_user, 'initial', 0)
        award_points(other_user, 'initial', 0)
        award_points(user3, 'initial', 0)
        db.session.commit()


        up1 = UserPoints.query.filter_by(user_id=new_user.id).first()
        up1.points = 150
        up1.level = 2 # Corresponds to 150 points

        up2 = UserPoints.query.filter_by(user_id=other_user.id).first()
        up2.points = 250
        up2.level = 3 # Corresponds to 250 points

        up3 = UserPoints.query.filter_by(user_id=user3.id).first()
        up3.points = 50
        up3.level = 1 # Corresponds to 50 points
        db.session.commit()

        leaderboard = get_leaderboard(time_period='all', limit=3)

        assert len(leaderboard) == 3
        assert leaderboard[0]['username'] == other_user.username # 250 points
        assert leaderboard[0]['score'] == 250
        assert leaderboard[0]['level'] == 3
        assert leaderboard[0]['rank'] == 1

        assert leaderboard[1]['username'] == new_user.username # 150 points
        assert leaderboard[1]['score'] == 150
        assert leaderboard[1]['level'] == 2
        assert leaderboard[1]['rank'] == 2

        assert leaderboard[2]['username'] == user3.username # 50 points
        assert leaderboard[2]['score'] == 50
        assert leaderboard[2]['level'] == 1
        assert leaderboard[2]['rank'] == 3

    @patch('app.utils.gamification_utils.datetime')
    def test_leaderboard_periodic_daily_weekly_monthly(self, mock_datetime, init_database, new_user, other_user):
        # Mock current time for consistent testing of periods
        # Ensure date is also imported: from datetime import datetime, timedelta, timezone, date
        mock_now = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc) # Friday, March 15, 2024
        mock_datetime.now.return_value = mock_now
        # Ensure UserPoints records exist for level display
        award_points(new_user, 'initial_np', 0)
        award_points(other_user, 'initial_op', 0)
        db.session.commit()

        new_user_points = UserPoints.query.filter_by(user_id=new_user.id).first()
        new_user_points.level = 1 # Set a default level
        other_user_points = UserPoints.query.filter_by(user_id=other_user.id).first()
        other_user_points.level = 1 # Set a default level
        db.session.commit()


        # --- Create ActivityLog entries ---
        # new_user:
        # Today: 10 points
        db.session.add(ActivityLog(user_id=new_user.id, activity_type='daily_action', points_earned=10, timestamp=mock_now - timedelta(hours=1)))
        # This week (but not today): 20 points (e.g., Monday of this week)
        db.session.add(ActivityLog(user_id=new_user.id, activity_type='weekly_action', points_earned=20, timestamp=mock_now - timedelta(days=4))) # Monday
        # This month (but not this week): 30 points (e.g., March 1st)
        db.session.add(ActivityLog(user_id=new_user.id, activity_type='monthly_action', points_earned=30, timestamp=mock_now.replace(day=1)))
        # Older: 100 points
        db.session.add(ActivityLog(user_id=new_user.id, activity_type='old_action', points_earned=100, timestamp=mock_now - timedelta(days=40)))

        # other_user:
        # Today: 15 points
        db.session.add(ActivityLog(user_id=other_user.id, activity_type='daily_action', points_earned=15, timestamp=mock_now - timedelta(hours=2)))
        # This week (but not today): 5 points
        db.session.add(ActivityLog(user_id=other_user.id, activity_type='weekly_action', points_earned=5, timestamp=mock_now - timedelta(days=3))) # Tuesday
        # This month (but not this week): 50 points
        db.session.add(ActivityLog(user_id=other_user.id, activity_type='monthly_action', points_earned=50, timestamp=mock_now.replace(day=2)))
        # Older: 200 points
        db.session.add(ActivityLog(user_id=other_user.id, activity_type='old_action', points_earned=200, timestamp=mock_now - timedelta(days=50)))
        db.session.commit()

        # Test Daily Leaderboard
        daily_lb = get_leaderboard(time_period='daily', limit=2)
        assert len(daily_lb) == 2
        assert daily_lb[0]['user_id'] == other_user.id # other_user: 15 points today
        assert daily_lb[0]['score'] == 15
        assert daily_lb[1]['user_id'] == new_user.id   # new_user: 10 points today
        assert daily_lb[1]['score'] == 10

        # Test Weekly Leaderboard
        weekly_lb = get_leaderboard(time_period='weekly', limit=2)
        # new_user: 10 (today) + 20 (this week) = 30
        # other_user: 15 (today) + 5 (this week) = 20
        assert len(weekly_lb) == 2
        assert weekly_lb[0]['user_id'] == new_user.id
        assert weekly_lb[0]['score'] == 30
        assert weekly_lb[1]['user_id'] == other_user.id
        assert weekly_lb[1]['score'] == 20

        # Test Monthly Leaderboard
        monthly_lb = get_leaderboard(time_period='monthly', limit=2)
        # new_user: 10 (today) + 20 (this week) + 30 (this month) = 60
        # other_user: 15 (today) + 5 (this week) + 50 (this month) = 70
        assert len(monthly_lb) == 2
        assert monthly_lb[0]['user_id'] == other_user.id
        assert monthly_lb[0]['score'] == 70
        assert monthly_lb[1]['user_id'] == new_user.id
        assert monthly_lb[1]['score'] == 60

    def test_leaderboard_empty_for_period_with_no_activity(self, init_database, new_user):
        # Ensure UserPoints exists for level display, even if no activity for period
        award_points(new_user, 'initial_points', 10) # This creates UserPoints
        db.session.commit()

        # No ActivityLog entries for 'daily' period
        with patch('app.utils.gamification_utils.datetime') as mock_datetime:
            mock_now = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now

            daily_lb = get_leaderboard(time_period='daily', limit=5)
            assert len(daily_lb) == 0

    def test_leaderboard_limit_parameter(self, init_database, new_user, other_user):
        user3 = User(username='user3', email='user3@example.com', password_hash='pw')
        db.session.add(user3)
        award_points(new_user, 'initial_np', 100)
        award_points(other_user, 'initial_op', 150)
        award_points(user3, 'initial_u3', 120)
        db.session.commit() # Commits UserPoints records

        leaderboard_limit_2 = get_leaderboard(time_period='all', limit=2)
        assert len(leaderboard_limit_2) == 2
        assert leaderboard_limit_2[0]['user_id'] == other_user.id # 150 points
        assert leaderboard_limit_2[1]['user_id'] == user3.id      # 120 points

        leaderboard_limit_1 = get_leaderboard(time_period='all', limit=1)
        assert len(leaderboard_limit_1) == 1
        assert leaderboard_limit_1[0]['user_id'] == other_user.id # 150 points


# --- Tests for Leaderboard Badges ---
class TestLeaderboardBadges:

    @patch('app.utils.gamification_utils.socketio.emit')
    @patch('app.utils.gamification_utils.get_leaderboard')
    def test_award_weekly_top_10_badge(self, mock_get_leaderboard, mock_socketio_emit, init_database, new_user):
        seed_badges()  # Ensure badges, including 'Weekly Contender', are in DB

        # Mock get_leaderboard to include the user in the weekly top 10
        mock_get_leaderboard.return_value = [
            {'user_id': new_user.id, 'username': new_user.username, 'score': 100, 'level': 1, 'rank': 1, 'profile_picture_url': ''},
            # ... add more users if needed for a full list of 10
        ]

        check_and_award_badges(new_user)
        db.session.commit()

        weekly_contender_badge = Badge.query.filter_by(criteria_key='weekly_top_10').first()
        assert weekly_contender_badge is not None
        assert weekly_contender_badge in new_user.badges

        # Verify ActivityLog
        activity_log = ActivityLog.query.filter_by(user_id=new_user.id, activity_type='earn_badge', related_id=weekly_contender_badge.id).first()
        assert activity_log is not None

        # Verify Notification
        notification = Notification.query.filter_by(recipient_id=new_user.id, type='new_badge').order_by(Notification.timestamp.desc()).first()
        assert notification is not None

        # Verify SocketIO emit (basic check, details depend on exact emit structure for badges)
        # Check if any call to emit was for the 'Weekly Contender' badge
        weekly_badge_emitted = False
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs_emit = call_args
            if args[0] == 'new_notification' and args[1].get('type') == 'new_badge' and args[1].get('badge_name') == 'Weekly Contender':
                weekly_badge_emitted = True
                break
        assert weekly_badge_emitted

        mock_get_leaderboard.assert_called_once_with(time_period='weekly', limit=10)

    @patch('app.utils.gamification_utils.socketio.emit')
    @patch('app.utils.gamification_utils.get_leaderboard')
    def test_not_award_weekly_top_10_if_not_in_list(self, mock_get_leaderboard, mock_socketio_emit, init_database, new_user, other_user):
        seed_badges()

        # Mock get_leaderboard to NOT include the user in the weekly top 10
        mock_get_leaderboard.return_value = [
            {'user_id': other_user.id, 'username': other_user.username, 'score': 120, 'level': 2, 'rank': 1, 'profile_picture_url': ''},
            # ... up to 10 users, none of them new_user
        ]

        check_and_award_badges(new_user)
        db.session.commit()

        weekly_contender_badge = Badge.query.filter_by(criteria_key='weekly_top_10').first()
        assert weekly_contender_badge is not None
        assert weekly_contender_badge not in new_user.badges

        # Ensure no socket event for this badge for this user
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs_emit = call_args
            if args[0] == 'new_notification' and args[1].get('type') == 'new_badge':
                assert args[1].get('badge_name') != 'Weekly Contender'


    @patch('app.utils.gamification_utils.socketio.emit')
    @patch('app.utils.gamification_utils.get_leaderboard')
    def test_award_monthly_top_3_badge(self, mock_get_leaderboard, mock_socketio_emit, init_database, new_user):
        seed_badges()

        mock_get_leaderboard.return_value = [
            {'user_id': new_user.id, 'username': new_user.username, 'score': 500, 'level': 3, 'rank': 1, 'profile_picture_url': ''},
            # ... other users if needed for top 3
        ]

        check_and_award_badges(new_user)
        db.session.commit()

        monthly_champion_badge = Badge.query.filter_by(criteria_key='monthly_top_3').first()
        assert monthly_champion_badge is not None
        assert monthly_champion_badge in new_user.badges

        monthly_badge_emitted = False
        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs_emit = call_args
            if args[0] == 'new_notification' and args[1].get('type') == 'new_badge' and args[1].get('badge_name') == 'Monthly Champion':
                monthly_badge_emitted = True
                break
        assert monthly_badge_emitted

        mock_get_leaderboard.assert_called_once_with(time_period='monthly', limit=3)

    @patch('app.utils.gamification_utils.socketio.emit')
    @patch('app.utils.gamification_utils.get_leaderboard')
    def test_not_award_monthly_top_3_if_not_in_list(self, mock_get_leaderboard, mock_socketio_emit, init_database, new_user, other_user):
        seed_badges()

        mock_get_leaderboard.return_value = [
            {'user_id': other_user.id, 'username': other_user.username, 'score': 600, 'level': 4, 'rank': 1, 'profile_picture_url': ''},
        ] # new_user is not in this list

        check_and_award_badges(new_user)
        db.session.commit()

        monthly_champion_badge = Badge.query.filter_by(criteria_key='monthly_top_3').first()
        assert monthly_champion_badge is not None
        assert monthly_champion_badge not in new_user.badges

        for call_args in mock_socketio_emit.call_args_list:
            args, kwargs_emit = call_args
            if args[0] == 'new_notification' and args[1].get('type') == 'new_badge':
                assert args[1].get('badge_name') != 'Monthly Champion'


# --- Basic UI Route Tests ---
class TestUIRoutesGamification:

    def test_leaderboard_route_loads(self, test_client, logged_in_user):
        # Ensure user is "logged in" for routes that require it.
        # The logged_in_user fixture should handle session setup if test_client uses it.
        # If not, a manual login post might be needed here.
        # For now, assuming @login_required is on leaderboard and logged_in_user is sufficient.
        # If leaderboard is public, logged_in_user is not strictly needed but doesn't hurt.

        # Simulate login for test_client if not handled by fixture globally
        with test_client.session_transaction() as sess:
            sess['user_id'] = logged_in_user.id
            sess['_fresh'] = True

        response = test_client.get('/leaderboard', follow_redirects=True)
        assert response.status_code == 200
        # More detailed checks could verify content, e.g., "Leaderboard" in response.data

    def test_profile_page_loads_with_level_info(self, test_client, new_user, init_database):
        # Give user some points and a level
        award_points(new_user, 'profile_test_points', 120) # Should be Level 2
        db.session.commit()

        user_points = UserPoints.query.filter_by(user_id=new_user.id).first()
        assert user_points is not None
        assert user_points.level == 2

        # Simulate login for test_client if accessing profile that might be restricted
        # or if parts of profile are current_user dependent.
        # For a public profile view, login might not be needed.
        # Assuming profile route is /user/<username>
        with test_client.session_transaction() as sess: # Ensure session for current_user context if profile template uses it
            sess['user_id'] = new_user.id # Viewing own profile for simplicity, or another user if testing privacy
            sess['_fresh'] = True

        response = test_client.get(f'/user/{new_user.username}', follow_redirects=True)
        assert response.status_code == 200
        # Asserting specific HTML content is more complex and fragile.
        # A basic check that "Level: 2" is in the response can be done.
        # Ensure response.data is bytes, so decode or use `b"Level: 2"`
        assert b"Level: 2" in response.data
        assert b"Points: 120" in response.data # Check points also
