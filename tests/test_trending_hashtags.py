import unittest
from app import create_app, db
from app.models import User, Hashtag
from unittest.mock import patch

class TrendingHashtagsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create a dummy user for login if needed by any part of the page rendering
        user = User(username='testuser', email='test@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()


    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_trending_hashtags_page_loads(self):
        response = self.client.get('/trending_hashtags')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Trending Hashtags', response.data)

    @patch('app.routes.Hashtag.query') # Mocking at the point of use in app.routes
    def test_trending_hashtags_displays_hashtags(self, mock_query):
        # Create some mock hashtag objects
        mock_hashtag1 = Hashtag(id=1, tag_text='python')
        mock_hashtag2 = Hashtag(id=2, tag_text='flask')
        mock_hashtag3 = Hashtag(id=3, tag_text='testing')

        # Configure the mock for all()
        mock_query.all.return_value = [mock_hashtag1, mock_hashtag2, mock_hashtag3]

        response = self.client.get('/trending_hashtags')
        self.assertEqual(response.status_code, 200)

        # Check if hashtag texts are present in the response
        self.assertIn(b'#python', response.data)
        self.assertIn(b'#flask', response.data)
        self.assertIn(b'#testing', response.data)

        # Check if links are correct
        self.assertIn(b'href="/hashtag/python"', response.data)
        self.assertIn(b'href="/hashtag/flask"', response.data)
        self.assertIn(b'href="/hashtag/testing"', response.data)

    @patch('app.routes.Hashtag.query')
    @patch('app.routes.random.sample') # Mock random.sample
    def test_trending_hashtags_random_sample_logic(self, mock_random_sample, mock_query):
        # Create more than 10 mock hashtags
        mock_hashtags = []
        for i in range(15):
            mock_hashtags.append(Hashtag(id=i, tag_text=f'tag{i}'))

        mock_query.all.return_value = mock_hashtags

        # Define what random.sample should return (a subset of 10)
        # For simplicity, let's say it returns the first 10
        mock_random_sample.return_value = mock_hashtags[:10]

        response = self.client.get('/trending_hashtags')
        self.assertEqual(response.status_code, 200)

        # Verify random.sample was called with the correct arguments
        # The first argument to random.sample will be the list of all_hashtags,
        # and the second argument will be 10.
        mock_random_sample.assert_called_once_with(mock_hashtags, 10)

        # Check that only 10 hashtags (those returned by the mocked sample) are displayed
        for i in range(10):
            self.assertIn(f'#tag{i}'.encode('utf-8'), response.data)
        for i in range(10, 15):
            self.assertNotIn(f'#tag{i}'.encode('utf-8'), response.data)

    def test_trending_hashtags_less_than_10(self, mock_query):
        # Create fewer than 10 mock hashtags
        mock_hashtags = []
        for i in range(5):
            mock_hashtags.append(Hashtag(id=i, tag_text=f'smalltag{i}'))

        mock_query.all.return_value = mock_hashtags

        response = self.client.get('/trending_hashtags')
        self.assertEqual(response.status_code, 200)

        # Check that all 5 hashtags are displayed
        for i in range(5):
            self.assertIn(f'#smalltag{i}'.encode('utf-8'), response.data)
            self.assertIn(f'href="/hashtag/smalltag{i}"'.encode('utf-8'), response.data)

    @patch('app.routes.Hashtag.query')
    def test_trending_hashtags_no_hashtags(self, mock_query):
        mock_query.all.return_value = []

        response = self.client.get('/trending_hashtags')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No hashtags to display at the moment.', response.data)

if __name__ == '__main__':
    unittest.main()
