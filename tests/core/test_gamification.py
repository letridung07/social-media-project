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
from app.core.models import User, Post, Reaction, UserPoints, Badge, ActivityLog, Notification, Story, Poll, Article, AudioPost, Comment, Group, Event, VirtualGood, UserVirtualGood # Add all models used in badge criteria
from app.utils.helpers import award_points
from app.utils.gamification_utils import seed_badges, check_and_award_badges, INITIAL_BADGES
from config import TestingConfig
from datetime import datetime, timedelta, timezone
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
def test_award_first_steps_title_fails_if_vg_not_found(mock_badge_socketio_emit, init_database, new_user, other_user): # Added other_user to avoid interference
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
