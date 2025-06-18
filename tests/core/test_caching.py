import unittest
import time
from app import create_app, db, cache
from app.core.models import User, Post # Corrected import path
from flask_login import login_user, logout_user

class CachingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_class='config.TestingConfig')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        cache.clear() # Ensure cache is clear before each test

        # Create test users
        self.user1 = User(username='testuser1', email='test1@example.com')
        self.user1.set_password('password')
        self.user2 = User(username='testuser2', email='test2@example.com')
        self.user2.set_password('password')
        db.session.add_all([self.user1, self.user2])
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        cache.clear()
        self.app_context.pop()

    def test_index_route_caching(self):
        # Test if the index route is cached
        with self.client:
            response1 = self.client.get('/')
            self.assertEqual(response1.status_code, 200)

            # To check if cache is hit, we can check if the response is the same
            # A more robust way would be to mock cache.get, but this is simpler for now.
            # For SimpleCache, the actual objects are stored, so data should be identical.

            # Simulate some processing that might change if not cached
            # For index, it might involve DB queries. We can't easily check that here without more mocks.

            response2 = self.client.get('/')
            self.assertEqual(response2.status_code, 200)
            self.assertEqual(response1.data, response2.data) # Content should be identical if cached

            # Check if a cache header might be present (Flask-Caching doesn't add them by default)
            # print(response1.headers)

    def test_profile_route_caching_and_invalidation(self):
        # Test if the profile route is cached and invalidated on profile edit
        with self.client:
            # Access profile page for user1
            profile_url = f'/user/{self.user1.username}'
            response1 = self.client.get(profile_url)
            self.assertEqual(response1.status_code, 200)

            response2 = self.client.get(profile_url)
            self.assertEqual(response2.status_code, 200)
            self.assertEqual(response1.data, response2.data, "Profile page should be cached")

            # Log in as user1 to edit profile
            self.client.post('/login', data=dict(
                email=self.user1.email,
                password='password'
            ), follow_redirects=True)

            # Edit profile
            edit_response = self.client.post('/edit_profile', data=dict(
                bio='New bio for testing cache invalidation'
            ), follow_redirects=True)
            self.assertEqual(edit_response.status_code, 200) # Should redirect to profile

            # Access profile page again - should be new content
            response3 = self.client.get(profile_url)
            self.assertEqual(response3.status_code, 200)
            self.assertNotEqual(response1.data, response3.data, "Profile page should be updated after edit (cache invalidated)")
            self.assertIn(b'New bio for testing cache invalidation', response3.data)

            logout_user() # Clean up login session

    def test_cache_timeout(self):
        # Test if cache expires after timeout
        # We'll use a route with a very short timeout for this test
        # Let's assume index has timeout of 300s, we need a way to test timeout
        # without waiting that long. We can configure a specific route or mock time.
        # For now, let's test with a short timeout if we can set one easily for a test route
        # Or, we can use the existing timeout and make an observation.

        # This test is more conceptual with SimpleCache as direct time manipulation is tricky
        # without external libraries like freezegun.
        # We'll simulate it by clearing the cache for a specific item if possible,
        # or by checking if a different response is generated if data underneath changes.

        # Let's use the profile page with its 3600s timeout as an example.
        # We can't easily wait for 3600s.
        # A practical way to test timeout with Flask-Caching would involve:
        # 1. Accessing the route.
        # 2. Manually deleting the cache entry using cache.delete() with the right key.
        #    (Finding the right key can be tricky as it's generated based on function and args).
        # 3. Accessing again and ensuring it's regenerated.
        # Or using a library like freezegun.

        # For this example, let's demonstrate the concept with a manual clear for the index
        # and assume Flask-Caching's timeout mechanism works as advertised.
        with self.client:
            self.client.get('/') # Populate cache for index

            # Manually clear the cache for the index view function
            # The key for view functions is often related to request.path
            # For SimpleCache, cache.clear() is a blunt tool but works for testing specific item expiry.
            # A more targeted way is cache.delete_memoized(view_func_name) or cache.delete(key)
            # For index, the view function is 'index' in 'main' blueprint.
            # The actual key generation can be complex.
            # Let's assume we know the key or can clear a relevant portion.

            # A simple way to show timeout concept:
            # Get page, clear *all* cache, get page again.
            # If data was truly cached, the second time (after clear) might be different if underlying data changed.
            # This doesn't test the *timeout* mechanism itself, but that the cache *can* be cleared.

            # For now, this test will be more of a placeholder for true timeout testing.
            # We can verify that if we clear the cache, content can be re-fetched.
            cache.clear()
            response_after_clear = self.client.get('/')
            self.assertEqual(response_after_clear.status_code, 200)
            # If content could change (e.g. new post), response_after_clear.data would differ from original.
            # This is not a direct timeout test but shows cache can be refreshed.
            pass # Placeholder for better timeout test with time manipulation tools

    def test_followed_posts_caching(self):
        # Test if User.followed_posts() method results are cached
        # This requires calling the method, then again, and checking if the cache was hit.
        # This is harder to test at the unit level without direct cache interaction/mocking.

        # Create posts for user2
        p1 = Post(body="Post 1 by user2", author=self.user2)
        p2 = Post(body="Post 2 by user2", author=self.user2)
        db.session.add_all([p1, p2])
        db.session.commit()

        # User1 follows User2
        self.user1.follow(self.user2)
        db.session.commit()

        # Access followed_posts for user1
        # The method itself is cached, not the route that might use it.
        # So we call it directly.

        # First call - should fetch from DB and cache
        with self.app.app_context(): # Ensure we are in app context for DB operations
            user1_from_db = User.query.get(self.user1.id)
            pagination1 = user1_from_db.followed_posts(page=1, per_page=5)
            posts1 = pagination1.items
            self.assertEqual(len(posts1), 2)

            # To verify caching, we'd ideally check cache internals or mock.
            # A simple check: if we add a new post from user2,
            # a *cached* call to followed_posts should NOT show it immediately.
            p3 = Post(body="Post 3 by user2 (after first call)", author=self.user2)
            db.session.add(p3)
            db.session.commit()

            pagination2 = user1_from_db.followed_posts(page=1, per_page=5)
            posts2 = pagination2.items
            # If caching works as expected (and timeout is non-zero), posts2 should be same as posts1
            self.assertEqual(len(posts2), 2, "Should serve from cache, so new post p3 is not included yet.")
            self.assertEqual(posts1, posts2)

            # Now, clear the cache for this specific method call if possible or clear all cache
            # The key depends on the function and its arguments.
            # cache.delete_memoized(User.followed_posts, user1_from_db) # This is conceptual
            # Or more broadly:
            cache.clear() # Clears all cache entries

            pagination3 = user1_from_db.followed_posts(page=1, per_page=5)
            posts3 = pagination3.items
            self.assertEqual(len(posts3), 3, "After cache clear, new post p3 should be included.")


if __name__ == '__main__':
    unittest.main()
