import unittest
from app import create_app, db
from app.models import User, Post, Group, GroupMembership
from flask import url_for

class SearchTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_class='config.TestingConfig')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create test users
        self.user1 = User(username='testuser1', email='test1@example.com')
        self.user1.set_password('password123')
        self.user2 = User(username='search_me', email='search@example.com')
        self.user2.set_password('password456')
        db.session.add_all([self.user1, self.user2])
        db.session.commit()

        # Create test posts
        self.post1 = Post(body='This is a test post by user1', author=self.user1)
        self.post2 = Post(body='Another post, searchable content here.', author=self.user2)
        db.session.add_all([self.post1, self.post2])
        db.session.commit()

        # Create test groups
        self.group1 = Group(name='Test Group Alpha', description='A group for testing purposes.', creator_id=self.user1.id)
        self.group2 = Group(name='Searchable Group Beta', description='Find this group by its description.', creator_id=self.user2.id)
        db.session.add_all([self.group1, self.group2])
        db.session.commit()

        # Add user1 as a member of group1 (creator is auto-added as admin, but let's be explicit for other tests if needed)
        # membership1 = GroupMembership(user_id=self.user1.id, group_id=self.group1.id, role='admin')
        # db.session.add(membership1)
        # db.session.commit()


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_search_setup_works(self):
        # A simple test to ensure setup is creating users, posts, and groups
        self.assertEqual(User.query.count(), 2)
        self.assertEqual(Post.query.count(), 2)
        self.assertEqual(Group.query.count(), 2)

    def test_search_users(self):
        # Test searching for an existing user by username
        response = self.client.get(url_for('main.search', q='testuser1'))
        self.assertEqual(response.status_code, 200)
        response_data = response.data.decode()
        self.assertIn('testuser1', response_data)
        self.assertIn(f'/user/{self.user1.username}', response_data) # Check for relative path
        self.assertNotIn('search_me', response_data) # Ensure other users not matching are not present

        # Test searching for an existing user by email
        response = self.client.get(url_for('main.search', q='search@example.com'))
        self.assertEqual(response.status_code, 200)
        response_data = response.data.decode()
        self.assertIn('search_me', response_data) # Username should be displayed
        self.assertIn(f'/user/{self.user2.username}', response_data) # Check for relative path
        self.assertNotIn('testuser1', response_data)

        # Test searching for a partial username
        response = self.client.get(url_for('main.search', q='testuser'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('testuser1', response.data.decode())

        # Test searching for a non-existent user
        response = self.client.get(url_for('main.search', q='nonexistentuser'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('testuser1', response.data.decode())
        self.assertNotIn('search_me', response.data.decode())
        # Depending on template, check for "No users found" or ensure user list is empty if possible

    def test_search_posts(self):
        # Test searching for a post by its body content
        response = self.client.get(url_for('main.search', q='searchable content here'))
        self.assertEqual(response.status_code, 200)
        response_data = response.data.decode()
        self.assertIn('searchable content here', response_data)
        self.assertIn(self.user2.username, response_data) # Author's username
        # Check for link to post (if your _post.html has a permalink or similar)
        # e.g. self.assertIn(url_for('main.view_post', post_id=self.post2.id), response_data)
        self.assertNotIn('This is a test post by user1', response_data)

        # Test searching for a partial post body
        response = self.client.get(url_for('main.search', q='test post'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('This is a test post by user1', response.data.decode())

        # Test searching for a non-existent post
        response = self.client.get(url_for('main.search', q='nonexistent post content'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('searchable content here', response.data.decode())
        self.assertNotIn('This is a test post by user1', response.data.decode())

    def test_search_groups(self):
        # Test searching for a group by its name
        response = self.client.get(url_for('main.search', q='Test Group Alpha'))
        self.assertEqual(response.status_code, 200)
        response_data = response.data.decode()
        self.assertIn('Test Group Alpha', response_data)
        self.assertIn(f'/group/{self.group1.id}', response_data) # Check for relative path
        self.assertNotIn('Searchable Group Beta', response_data)

        # Test searching for a group by its description
        response = self.client.get(url_for('main.search', q='Find this group'))
        self.assertEqual(response.status_code, 200)
        response_data = response.data.decode()
        self.assertIn('Searchable Group Beta', response_data) # Group name should be in results
        self.assertIn('Find this group by its description.', response_data) # Description might be there too
        self.assertIn(f'/group/{self.group2.id}', response_data) # Check for relative path
        self.assertNotIn('Test Group Alpha', response_data)

        # Test searching for a partial group name
        response = self.client.get(url_for('main.search', q='Test Group'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Test Group Alpha', response.data.decode())

        # Test searching for a non-existent group
        response = self.client.get(url_for('main.search', q='nonexistent group name'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Test Group Alpha', response.data.decode())
        self.assertNotIn('Searchable Group Beta', response.data.decode())

    def test_search_empty_query(self):
        response = self.client.get(url_for('main.search', q=''))
        self.assertEqual(response.status_code, 200)
        response_data = response.data.decode()
        # Updated assertion based on actual template output for empty query
        self.assertIn('<h1>Search</h1>', response_data)
        self.assertIn('<p>Please enter a term to search for.</p>', response_data)
        # Ensure it doesn't accidentally list all users/posts/groups
        self.assertNotIn(self.user1.username, response_data)
        self.assertNotIn('This is a test post by user1', response_data)
        self.assertNotIn('Test Group Alpha', response_data)
        # It might be better to check if the sections for users, posts, groups are present but empty or specific message.
        # Based on current search_results.html, it would show "Search Results for """ and then nothing else if query is empty.
        # Let's verify no "No users, posts, or groups found matching your query" as that's for non-empty, no-result queries.
        self.assertNotIn('No users, posts, or groups found matching your query', response_data)


    def test_search_no_results(self):
        response = self.client.get(url_for('main.search', q='zzzzxxxxnonexistentquery'))
        self.assertEqual(response.status_code, 200)
        response_data = response.data.decode()
        self.assertIn('No users, posts, or groups found matching your query "zzzzxxxxnonexistentquery"', response_data)
        self.assertNotIn('testuser1', response_data)
        self.assertNotIn('This is a test post by user1', response_data)
        self.assertNotIn('Test Group Alpha', response_data)

    def test_search_results_page_links(self):
        # Search for user 'testuser1'
        response_user = self.client.get(url_for('main.search', q='testuser1'))
        self.assertEqual(response_user.status_code, 200)
        self.assertIn(f'/user/{self.user1.username}', response_user.data.decode())

        # Search for post 'searchable content'
        response_post = self.client.get(url_for('main.search', q='searchable content'))
        self.assertEqual(response_post.status_code, 200)
        # The _post.html template might not have a direct permalink to the post itself,
        # but rather displays the post. If it does, like:
        # self.assertIn(f'/post/{self.post2.id}', response_post.data.decode())
        # For now, we'll assume the post body presence implies it's correctly displayed.
        # A more robust test would be if _post.html includes a permalink like:
        # <a href="{{ url_for('main.view_post', post_id=post.id) }}">View Post</a>
        # Currently, _post.html does not have such a link. It displays content.
        # The main check is that the *post content* is there.
        self.assertIn('searchable content here', response_post.data.decode())


        # Search for group 'Test Group Alpha'
        response_group = self.client.get(url_for('main.search', q='Test Group Alpha'))
        self.assertEqual(response_group.status_code, 200)
        self.assertIn(f'/group/{self.group1.id}', response_group.data.decode())


if __name__ == '__main__':
    unittest.main()
