import unittest
import json
from app import create_app, db
from app.core.models import User, Post, Group, Poll, PollOption, PollVote # Corrected import path
from config import TestingConfig

class PollTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Create test users
        self.user1 = User(username='polluser1', email='polluser1@example.com')
        self.user1.set_password('password')
        self.user2 = User(username='polluser2', email='polluser2@example.com')
        self.user2.set_password('password')
        db.session.add_all([self.user1, self.user2])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self, username, password):
        return self.client.post('/login', data=dict(
            email=f'{username}@example.com',
            password=password
        ), follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_poll_model_creation(self):
        poll = Poll(question="What's your favorite color?", user_id=self.user1.id)
        db.session.add(poll)
        db.session.flush() # To get poll.id for options

        opt1 = PollOption(poll_id=poll.id, option_text="Blue")
        opt2 = PollOption(poll_id=poll.id, option_text="Red")
        db.session.add_all([opt1, opt2])
        db.session.commit()

        self.assertIsNotNone(poll.id)
        self.assertEqual(poll.question, "What's your favorite color?")
        self.assertEqual(poll.author, self.user1)
        self.assertEqual(len(poll.options.all()), 2)
        self.assertEqual(poll.options.first().option_text, "Blue")

    def test_poll_vote_model_creation_and_unique_constraint(self):
        poll = Poll(question="Test poll for voting", user_id=self.user1.id)
        db.session.add(poll)
        db.session.flush()
        option = PollOption(poll_id=poll.id, option_text="Option 1")
        db.session.add(option)
        db.session.commit()

        # First vote
        vote1 = PollVote(user_id=self.user2.id, option_id=option.id, poll_id=poll.id)
        db.session.add(vote1)
        db.session.commit()
        self.assertIsNotNone(vote1.id)

        # Try to vote again on the same poll (should fail due to unique constraint on user_id, poll_id)
        vote2 = PollVote(user_id=self.user2.id, option_id=option.id, poll_id=poll.id)
        db.session.add(vote2)
        with self.assertRaises(Exception): # sqlalchemy.exc.IntegrityError
            db.session.commit()
        db.session.rollback() # Rollback the failed commit

    def test_poll_model_helpers(self):
        poll = Poll(question="Helper methods test", user_id=self.user1.id)
        db.session.add(poll)
        db.session.flush()
        opt1 = PollOption(poll_id=poll.id, option_text="Opt A")
        opt2 = PollOption(poll_id=poll.id, option_text="Opt B")
        db.session.add_all([opt1, opt2])
        db.session.commit()

        # user2 votes for Opt A
        vote = PollVote(user_id=self.user2.id, option_id=opt1.id, poll_id=poll.id)
        db.session.add(vote)
        db.session.commit()

        self.assertTrue(poll.user_has_voted(self.user2))
        self.assertFalse(poll.user_has_voted(self.user1))
        self.assertEqual(opt1.vote_count(), 1)
        self.assertEqual(opt2.vote_count(), 0)
        self.assertEqual(poll.total_votes(), 1)

    def test_create_poll_page_load(self):
        self.login('polluser1', 'password')
        response = self.client.get('/poll/create')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Create a New Poll', response.data)

    def test_create_poll_post(self):
        self.login('polluser1', 'password')
        data = {
            'question': 'Which is better, Cats or Dogs?',
            'options-0-option_text': 'Cats',
            'options-1-option_text': 'Dogs',
            'options-2-option_text': '', # Empty option, should be ignored by route
        }
        response = self.client.post('/poll/create', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Poll created successfully!', response.data)

        poll = Poll.query.filter_by(user_id=self.user1.id).first()
        self.assertIsNotNone(poll)
        self.assertEqual(poll.question, 'Which is better, Cats or Dogs?')
        self.assertEqual(len(poll.options.all()), 2) # Only two valid options
        self.assertEqual(poll.options[0].option_text, 'Cats')
        self.assertEqual(poll.options[1].option_text, 'Dogs')

    def test_poll_vote_post_and_change_vote(self):
        # Setup poll
        poll = Poll(question="Vote test", user_id=self.user1.id)
        db.session.add(poll)
        db.session.flush()
        opt1 = PollOption(poll_id=poll.id, option_text="Yes")
        opt2 = PollOption(poll_id=poll.id, option_text="No")
        db.session.add_all([opt1, opt2])
        db.session.commit()

        self.login('polluser2', 'password')

        # First vote (for Yes)
        response = self.client.post(f'/poll/{poll.id}/vote', data={'option_id': opt1.id})
        self.assertEqual(response.status_code, 200)
        json_response = json.loads(response.data.decode('utf-8'))
        self.assertTrue(json_response['success'])
        self.assertEqual(json_response['message'], 'Your vote has been recorded.')

        vote = PollVote.query.filter_by(user_id=self.user2.id, poll_id=poll.id).first()
        self.assertIsNotNone(vote)
        self.assertEqual(vote.option_id, opt1.id)

        # Change vote (to No)
        response_change = self.client.post(f'/poll/{poll.id}/vote', data={'option_id': opt2.id})
        self.assertEqual(response_change.status_code, 200)
        json_response_change = json.loads(response_change.data.decode('utf-8'))
        self.assertTrue(json_response_change['success'])
        self.assertEqual(json_response_change['message'], 'Your vote has been updated.')

        vote_changed = PollVote.query.filter_by(user_id=self.user2.id, poll_id=poll.id).first()
        self.assertEqual(vote_changed.option_id, opt2.id)
        self.assertEqual(PollVote.query.count(), 1) # Still only one vote record for this user/poll

    def test_poll_vote_invalid_option(self):
        poll = Poll(question="Invalid vote test", user_id=self.user1.id)
        db.session.add(poll)
        db.session.commit() # No options added

        self.login('polluser2', 'password')
        response = self.client.post(f'/poll/{poll.id}/vote', data={'option_id': 999}) # 999 is an invalid option_id
        self.assertEqual(response.status_code, 400) # Bad request
        json_response = json.loads(response.data.decode('utf-8'))
        self.assertFalse(json_response['success'])
        self.assertIn('Invalid option selected', json_response['error'])

    def test_poll_vote_no_option_selected(self):
        poll = Poll(question="No option selected test", user_id=self.user1.id)
        # Add at least one option so the poll is valid to vote on in principle
        opt1 = PollOption(poll_id=poll.id, option_text="Option A")
        db.session.add_all([poll, opt1])
        db.session.commit()

        self.login('polluser2', 'password')
        response = self.client.post(f'/poll/{poll.id}/vote', data={}) # No option_id submitted
        self.assertEqual(response.status_code, 400)
        json_response = json.loads(response.data.decode('utf-8'))
        self.assertFalse(json_response['success'])
        self.assertIn('Please select an option to vote', json_response['error'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
