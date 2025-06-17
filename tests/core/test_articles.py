import unittest
import os
from flask import current_app, get_flashed_messages
from app import create_app, db
from app.core.models import User, Article # Import Article
from config import TestingConfig
from datetime import datetime, timedelta

class ArticleTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create test users
        self.user1 = User(username='testuser1', email='testuser1@example.com')
        self.user1.set_password('password')
        self.user2 = User(username='testuser2', email='testuser2@example.com')
        self.user2.set_password('password')
        db.session.add_all([self.user1, self.user2])
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

    def _create_db_article(self, title, body, user, timestamp=None, slug_override=None):
        """Helper to create an article directly in the DB for test setup."""
        from app.utils.helpers import slugify # Local import to avoid issues if utils imports models

        if timestamp is None:
            timestamp = datetime.utcnow()

        final_slug = slug_override
        if not final_slug:
            original_slug = slugify(title, model_to_check=Article, target_column_name='slug')
            # Simplified uniqueness for test helper - assumes direct creation doesn't often clash
            # For route tests, the route's uniqueness logic is tested.
            slug_candidate = original_slug
            counter = 1
            while Article.query.filter_by(slug=slug_candidate).first():
                slug_candidate = f"{original_slug}-{counter}"
                counter +=1
            final_slug = slug_candidate

        article = Article(title=title, body=body, author=user, timestamp=timestamp, slug=final_slug)
        db.session.add(article)
        db.session.commit()
        return article

    def test_create_article(self):
        # Success Case (Logged In)
        self._login('testuser1@example.com', 'password')
        response = self.client.post('/article/create', data={
            'title': 'My First Article',
            'body': 'This is the body of my first article.'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Article published successfully!', response.data)

        article1 = Article.query.filter_by(title='My First Article').first()
        self.assertIsNotNone(article1)
        self.assertEqual(article1.author, self.user1)
        self.assertEqual(article1.body, 'This is the body of my first article.')
        self.assertTrue(article1.slug.startswith('my-first-article'))
        # Check redirection to view_article page
        self.assertTrue(f'/article/{article1.slug}' in response.request.path)

        # Slug Uniqueness
        response2 = self.client.post('/article/create', data={
            'title': 'My First Article', # Same title
            'body': 'Another article with the same title.'
        }, follow_redirects=True)
        self.assertEqual(response2.status_code, 200)
        article2 = Article.query.filter_by(body='Another article with the same title.').first()
        self.assertIsNotNone(article2)
        self.assertNotEqual(article1.slug, article2.slug)
        self.assertTrue(article2.slug.startswith('my-first-article-'))
        self._logout()

        # Not Logged In
        response_not_logged_in = self.client.post('/article/create', data={
            'title': 'Attempt by Guest', 'body': 'Should fail.'
        }, follow_redirects=True)
        self.assertTrue(response_not_logged_in.request.path.startswith('/login'))

        # Invalid Data (Missing Title)
        self._login('testuser1@example.com', 'password')
        response_invalid = self.client.post('/article/create', data={
            'title': '', 'body': 'Body without title.'
        }, follow_redirects=True)
        self.assertEqual(response_invalid.status_code, 200) # Should re-render form
        self.assertIn(b'This field is required.', response_invalid.data) # WTForms default error
        self.assertIsNone(Article.query.filter_by(body='Body without title.').first())
        self._logout()

    def test_view_article(self):
        article = self._create_db_article('View Test Article', 'Body of view test.', self.user1)

        response = self.client.get(f'/article/{article.slug}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'View Test Article', response.data)
        self.assertIn(b'Body of view test.', response.data)
        self.assertIn(self.user1.username.encode(), response.data)

        # Not Found
        response_404 = self.client.get('/article/non-existent-slug-here')
        self.assertEqual(response_404.status_code, 404)

    def test_edit_article(self):
        article = self._create_db_article('Editable Article', 'Original Body.', self.user1)
        original_slug = article.slug

        # Success Case (Author Logged In)
        self._login('testuser1@example.com', 'password')
        response_edit = self.client.post(f'/article/{article.slug}/edit', data={
            'title': 'Updated Title',
            'body': 'Updated Body Content.'
        }, follow_redirects=True)
        self.assertEqual(response_edit.status_code, 200)
        self.assertIn(b'Article updated successfully!', response_edit.data)

        updated_article = Article.query.get(article.id)
        self.assertEqual(updated_article.title, 'Updated Title')
        self.assertEqual(updated_article.body, 'Updated Body Content.')
        self.assertEqual(updated_article.slug, original_slug) # Slug should not change
        self.assertTrue(f'/article/{original_slug}' in response_edit.request.path)
        self._logout()

        # Unauthorized (Different User Logged In)
        self._login('testuser2@example.com', 'password')
        response_unauth = self.client.post(f'/article/{article.slug}/edit', data={
            'title': 'Attempted Hack', 'body': 'Should not work.'
        }, follow_redirects=True)
        self.assertEqual(response_unauth.status_code, 403) # Forbidden
        db.session.refresh(article) # Ensure it wasn't changed
        self.assertEqual(article.title, 'Updated Title') # Should be the title from user1's edit
        self._logout()

        # Unauthorized (Not Logged In)
        response_guest = self.client.post(f'/article/{article.slug}/edit', data={
            'title': 'Guest Edit', 'body': 'No way.'
        }, follow_redirects=True)
        self.assertTrue(response_guest.request.path.startswith('/login'))

    def test_delete_article(self):
        article = self._create_db_article('Deletable Article', 'Body to delete.', self.user1)
        article_id = article.id

        # Unauthorized (Different User Logged In)
        self._login('testuser2@example.com', 'password')
        response_unauth_del = self.client.post(f'/article/{article.slug}/delete', follow_redirects=True)
        self.assertEqual(response_unauth_del.status_code, 403)
        self.assertIsNotNone(Article.query.get(article_id)) # Still exists
        self._logout()

        # Unauthorized (Not Logged In)
        response_guest_del = self.client.post(f'/article/{article.slug}/delete', follow_redirects=True)
        self.assertTrue(response_guest_del.request.path.startswith('/login'))
        self.assertIsNotNone(Article.query.get(article_id)) # Still exists

        # Success Case (Author Logged In)
        self._login('testuser1@example.com', 'password')
        response_del = self.client.post(f'/article/{article.slug}/delete', follow_redirects=True)
        self.assertEqual(response_del.status_code, 200)
        self.assertIn(b'Article deleted successfully!', response_del.data)
        self.assertIsNone(Article.query.get(article_id))
        self.assertTrue('/articles' in response_del.request.path) # Redirects to articles list
        self._logout()

    def test_list_all_articles(self):
        self._create_db_article('Article Alpha', 'Content Alpha', self.user1, timestamp=datetime.utcnow() - timedelta(days=1))
        self._create_db_article('Article Beta', 'Content Beta', self.user2, timestamp=datetime.utcnow())

        response = self.client.get('/articles')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Article Alpha', response.data)
        self.assertIn(b'Content Alpha', response.data) # Assuming snippet shows some content
        self.assertIn(b'Article Beta', response.data)
        self.assertIn(b'Content Beta', response.data)
        self.assertIn(self.user1.username.encode(), response.data)
        self.assertIn(self.user2.username.encode(), response.data)

        # Test Pagination (simple check: create more than ARTICLES_PER_PAGE)
        # Assuming ARTICLES_PER_PAGE is 10 (default in route)
        for i in range(12):
            self._create_db_article(f'Paged Article {i}', f'Body {i}', self.user1, slug_override=f'paged-article-{i}')

        response_page1 = self.client.get('/articles')
        self.assertIn(b'Paged Article 11', response_page1.data) # Newest should be on page 1
        self.assertNotIn(b'Paged Article 0', response_page1.data)
        self.assertIn(b'Next', response_page1.data) # Pagination link

        response_page2 = self.client.get('/articles?page=2')
        self.assertNotIn(b'Paged Article 11', response_page2.data)
        self.assertIn(b'Paged Article 0', response_page2.data) # Oldest of the 12 on page 2
        self.assertIn(b'Previous', response_page2.data)

    def test_list_user_articles(self):
        self._create_db_article('User1 Article 1', 'U1A1', self.user1, timestamp=datetime.utcnow() - timedelta(seconds=10))
        self._create_db_article('User1 Article 2', 'U1A2', self.user1)
        self._create_db_article('User2 Article 1', 'U2A1', self.user2)

        response = self.client.get(f'/user/{self.user1.username}/articles')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User1 Article 1', response.data)
        self.assertIn(b'User1 Article 2', response.data)
        self.assertIn(f'Articles by {self.user1.username}'.encode(), response.data)
        self.assertNotIn(b'User2 Article 1', response.data)

    def test_article_body_rendering_safe_filter(self):
        html_body = "<p>This is a paragraph.</p><ul><li>List item</li></ul><b>Bold text</b>"
        article = self._create_db_article('HTML Content Article', html_body, self.user1)

        response = self.client.get(f'/article/{article.slug}')
        self.assertEqual(response.status_code, 200)
        # Check for actual HTML tags, not escaped versions
        self.assertIn(b'<p>This is a paragraph.</p>', response.data)
        self.assertIn(b'<ul><li>List item</li></ul>', response.data)
        self.assertIn(b'<b>Bold text</b>', response.data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
