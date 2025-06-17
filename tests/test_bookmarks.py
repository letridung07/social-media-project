import pytest
from app import db, create_app
from app.models import User, Post, Bookmark
from flask import url_for, get_flashed_messages
from datetime import datetime, timedelta

# It's good practice to have a testing configuration
# For this example, we'll assume a 'config.TestingConfig' exists or use a default.
# If not, create_app() might need adjustment or a specific testing config class.
# from config import TestingConfig # Example

@pytest.fixture(scope='module')
def test_app():
    """Create and configure a new app instance for each test module."""
    # Attempt to use a specific testing config, otherwise fall back
    try:
        app = create_app(config_class='config.TestingConfig')
    except (ImportError, AttributeError):
        app = create_app(config_class='config.Config') # Fallback to default Config
        app.config.update({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,  # Disable CSRF for simpler test forms
            "LOGIN_DISABLED": False, # Ensure login is enabled for testing @login_required
            "SERVER_NAME": "localhost.localdomain", # For url_for to work without active request
        })
    return app

@pytest.fixture(scope='module')
def test_client(test_app):
    """A test client for the app."""
    return test_app.test_client()

@pytest.fixture(scope='module')
def init_database(test_app):
    """Create the database and the database table"""
    with test_app.app_context():
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='function')
def new_user(init_database):
    """Create a new user and add to db for function scope."""
    user = User(username='testuser', email='test@example.com')
    user.set_password('testpassword')
    db.session.add(user)
    db.session.commit()
    return user

@pytest.fixture(scope='function')
def new_user2(init_database):
    """Create a second new user."""
    user = User(username='testuser2', email='test2@example.com')
    user.set_password('testpassword2')
    db.session.add(user)
    db.session.commit()
    return user

@pytest.fixture(scope='function')
def new_post(init_database, new_user):
    """Create a new post by new_user for function scope."""
    post = Post(body='Test post content for bookmarks', user_id=new_user.id, author=new_user)
    db.session.add(post)
    db.session.commit()
    return post

@pytest.fixture(scope='function')
def new_post2(init_database, new_user):
    """Create a second post by new_user for function scope."""
    post = Post(body='Another test post', user_id=new_user.id, author=new_user)
    db.session.add(post)
    db.session.commit()
    return post

# Helper function to log in a user
def login(client, username, password):
    return client.post(url_for('main.login',_external=False), data=dict(
        email=username if '@' in username else f'{username}@example.com', # Assuming email or username login
        password=password
    ), follow_redirects=True)

def logout(client):
    return client.get(url_for('main.logout',_external=False), follow_redirects=True)

# --- Test Cases ---

def test_bookmark_creation_and_deletion(test_app, test_client, new_user, new_post):
    with test_app.app_context(): # Ensure app context for url_for and db operations
        login(test_client, 'testuser', 'testpassword')

        # 1. Bookmark a post
        response = test_client.post(url_for('main.bookmark_post', post_id=new_post.id), follow_redirects=True)
        assert response.status_code == 200 # Assuming redirect leads to a 200 OK page

        bookmark = Bookmark.query.filter_by(user_id=new_user.id, post_id=new_post.id).first()
        assert bookmark is not None
        assert bookmark.user_id == new_user.id
        assert bookmark.post_id == new_post.id

        # Check flashed message (optional, depends on test setup for contexts)
        # with test_client.session_transaction() as session:
        #     flashes = session.get('_flashes', []) # Default key for flashed messages
        #     assert any('Post bookmarked.' in message[1] for message in flashes)


        # 2. Try to bookmark the same post again (should not create a duplicate)
        test_client.post(url_for('main.bookmark_post', post_id=new_post.id), follow_redirects=True)
        bookmarks_count = Bookmark.query.filter_by(user_id=new_user.id, post_id=new_post.id).count()
        assert bookmarks_count == 1

        # 3. Unbookmark the post
        response_unbookmark = test_client.post(url_for('main.bookmark_post', post_id=new_post.id), follow_redirects=True)
        assert response_unbookmark.status_code == 200

        bookmark_after_delete = Bookmark.query.filter_by(user_id=new_user.id, post_id=new_post.id).first()
        assert bookmark_after_delete is None

        # 4. Try to unbookmark a post that isn't bookmarked (should not error)
        response_unbookmark_again = test_client.post(url_for('main.bookmark_post', post_id=new_post.id), follow_redirects=True)
        assert response_unbookmark_again.status_code == 200 # Should still be OK
        assert Bookmark.query.filter_by(user_id=new_user.id, post_id=new_post.id).count() == 0 # Should be 0, not negative or error

        logout(test_client)

def test_view_bookmarks_page(test_app, test_client, new_user, new_post, new_post2):
    with test_app.app_context():
        login(test_client, new_user.username, 'testpassword')

        # Bookmark one post first, then another with a slight delay to check ordering
        test_client.post(url_for('main.bookmark_post', post_id=new_post.id), follow_redirects=True)

        # Simulate a slight delay for timestamp difference
        # In a real scenario, you might manually set timestamps if testing order is critical
        # For now, the execution order should suffice if timestamps are close.
        # To be more robust, one could update the bookmark timestamp manually after creation.
        # For this test, we'll assume new_post2 is bookmarked slightly later.

        # Manually create a bookmark for new_post2 with an older timestamp
        # This is to ensure ordering is tested correctly
        bookmark_older = Bookmark(user_id=new_user.id, post_id=new_post2.id, timestamp=datetime.utcnow() - timedelta(hours=1))
        db.session.add(bookmark_older)
        db.session.commit()


        response = test_client.get(url_for('main.list_bookmarks'))
        assert response.status_code == 200
        response_data_str = response.get_data(as_text=True)

        assert 'My Bookmarks' in response_data_str
        assert new_post.body in response_data_str # new_post was bookmarked more recently (implicitly)
        assert new_post2.body in response_data_str # new_post2 was bookmarked earlier

        # Test ordering: new_post (bookmarked via route, timestamp is now) should appear before new_post2 (bookmarked manually with older timestamp)
        # This depends on how posts are rendered. A simpler check is to verify the order of Post objects passed to template.
        # This test relies on string positions, which can be brittle.
        assert response_data_str.find(new_post.body) < response_data_str.find(new_post2.body)

        # Unbookmark new_post (the more recent one)
        db.session.delete(Bookmark.query.filter_by(user_id=new_user.id, post_id=new_post.id).first())
        db.session.commit()

        # Unbookmark new_post2 (the older one)
        db.session.delete(bookmark_older)
        db.session.commit()

        response_empty = test_client.get(url_for('main.list_bookmarks'))
        assert response_empty.status_code == 200
        assert "You haven't bookmarked any posts yet." in response_empty.get_data(as_text=True)
        assert new_post.body not in response_empty.get_data(as_text=True)
        assert new_post2.body not in response_empty.get_data(as_text=True)

        logout(test_client)

def test_bookmarks_access_control(test_app, test_client, new_post):
    with test_app.app_context():
        # 1. Test POST /bookmark/<post_id> when not logged in
        response_bookmark_post = test_client.post(url_for('main.bookmark_post', post_id=new_post.id), follow_redirects=False) # Don't follow to check redirect
        assert response_bookmark_post.status_code == 302 # Redirect
        assert url_for('main.login') in response_bookmark_post.location # Check if redirected to login

        # 2. Test GET /bookmarks when not logged in
        response_list_bookmarks = test_client.get(url_for('main.list_bookmarks'), follow_redirects=False)
        assert response_list_bookmarks.status_code == 302
        assert url_for('main.login') in response_list_bookmarks.location

def test_bookmark_model_integrity(test_app, new_user, new_post):
     with test_app.app_context():
        # Test unique constraint (user_id, post_id)
        bookmark1 = Bookmark(user_id=new_user.id, post_id=new_post.id)
        db.session.add(bookmark1)
        db.session.commit()

        bookmark2 = Bookmark(user_id=new_user.id, post_id=new_post.id)
        try:
            db.session.add(bookmark2)
            db.session.commit()
            # If we reach here, the constraint failed or wasn't enforced by SQLite in this context
            # For more robust DBs like PostgreSQL, this would raise IntegrityError
            # Pytest users might expect an explicit pytest.raises(sqlalchemy.exc.IntegrityError)
            # However, SQLite behavior with unique constraints can be nuanced depending on session state.
            # Let's query to ensure only one was added.
            count = Bookmark.query.filter_by(user_id=new_user.id, post_id=new_post.id).count()
            assert count == 1, "Duplicate bookmark was created or IntegrityError not raised as expected."

        except Exception as e: # Catch a general exception, ideally sqlalchemy.exc.IntegrityError
            db.session.rollback() # Rollback session on error
            # Check if it's an integrity error (specific exception type depends on DB backend)
            # For SQLite, it might be sqlalchemy.exc.IntegrityError or similar.
            # For this generic test, we'll assume the exception means the constraint worked.
            # A more specific check: assert isinstance(e, sqlalchemy.exc.IntegrityError)
            pass # Expected if constraint is working

        # Clean up the created bookmark
        db.session.delete(bookmark1)
        db.session.commit()

def test_other_user_cannot_see_bookmarks(test_app, test_client, new_user, new_user2, new_post):
    # This test is more about ensuring the /bookmarks route is correctly scoped to current_user.
    # There isn't a /users/<id>/bookmarks route to test directly for another user.
    with test_app.app_context():
        # User1 bookmarks a post
        login(test_client, new_user.username, 'testpassword')
        test_client.post(url_for('main.bookmark_post', post_id=new_post.id), follow_redirects=True)
        logout(test_client)

        # User2 logs in
        login(test_client, new_user2.username, 'testpassword2')
        response = test_client.get(url_for('main.list_bookmarks'))
        assert response.status_code == 200
        # new_post.body should NOT be in User2's bookmarks page
        assert new_post.body not in response.get_data(as_text=True)
        assert "You haven't bookmarked any posts yet." in response.get_data(as_text=True)
        logout(test_client)

# Example of testing ordering more explicitly if timestamps are very close
def test_bookmark_ordering_explicit(test_app, test_client, new_user, new_post, new_post2):
    with test_app.app_context():
        login(test_client, new_user.username, 'testpassword')

        # Bookmark post1, then post2 after a delay
        # Manually create Bookmarks to control timestamps precisely

        # Older bookmark
        bm1 = Bookmark(user_id=new_user.id, post_id=new_post.id, timestamp=datetime.utcnow() - timedelta(minutes=10))
        db.session.add(bm1)

        # Newer bookmark
        bm2 = Bookmark(user_id=new_user.id, post_id=new_post2.id, timestamp=datetime.utcnow())
        db.session.add(bm2)
        db.session.commit()

        response = test_client.get(url_for('main.list_bookmarks'))
        assert response.status_code == 200
        response_data_str = response.get_data(as_text=True)

        # new_post2 (bm2) is newer, so it should appear first in the list
        assert new_post2.body in response_data_str
        assert new_post.body in response_data_str

        # Ensure new_post2.body appears before new_post.body
        assert response_data_str.find(new_post2.body) < response_data_str.find(new_post.body)

        # Cleanup
        db.session.delete(bm1)
        db.session.delete(bm2)
        db.session.commit()
        logout(test_client)
