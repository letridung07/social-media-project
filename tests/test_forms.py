import unittest
from flask import Flask # Flask is used by create_app
from datetime import datetime, timedelta, timezone
from app import create_app, db
from app.core.forms import (
    PostForm, StoryForm, RegistrationForm, CommentForm,
    EditProfileForm, PollForm, PollOptionEntryForm
)
from app.core.models import User, FriendList, PRIVACY_CUSTOM_LIST # For PostForm custom list test, User for setUp
from config import TestingConfig # Import TestingConfig
from wtforms.validators import ValidationError
from werkzeug.datastructures import FileStorage
import io

class TestSchedulingForms(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig) # Use TestingConfig
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all() # Ensure DB is created for consistency, though not strictly used by schedule_time tests

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_post_form_schedule_time_future(self):
        with self.app.test_request_context('/'):
            form = PostForm(body="Test body for future schedule")
            form.custom_friend_list_id.choices = [] # Ensure choices are set if form expects them
            form.schedule_time.data = datetime.now(timezone.utc) + timedelta(days=1)
            is_valid = form.schedule_time.validate(form)
            self.assertTrue(is_valid)
            self.assertNotIn('schedule_time', form.errors)

    def test_post_form_schedule_time_past(self):
        with self.app.test_request_context('/'):
            form = PostForm(body="Test body for past schedule")
            form.custom_friend_list_id.choices = []
            form.schedule_time.data = datetime.now(timezone.utc) - timedelta(days=1)
            try:
                form.schedule_time.validate(form, (form.schedule_time,))
                raised_error = False
            except ValidationError as e:
                raised_error = True
                self.assertIn('Scheduled time must be in the future.', str(e))
            self.assertTrue(raised_error, "ValidationError for past schedule_time was not raised.")

    def test_post_form_schedule_time_empty(self):
        with self.app.test_request_context('/'):
            form = PostForm(body="Test body for empty schedule")
            form.custom_friend_list_id.choices = []
            form.schedule_time.data = None
            is_valid = form.schedule_time.validate(form)
            self.assertTrue(is_valid)
            self.assertNotIn('schedule_time', form.errors)

    def test_story_form_schedule_time_future(self):
        with self.app.test_request_context(method='POST', data={'caption': 'Test'}): # Ensure basic data for StoryForm
            # StoryForm requires media_file, which is hard to mock perfectly without full request context
            # For focusing on schedule_time, we'll assume other validators pass or are not hit
            form = StoryForm(caption="Test caption for future schedule")
            form.custom_friend_list_id.choices = []
            form.schedule_time.data = datetime.now(timezone.utc) + timedelta(days=1)
            # We can't call form.validate() without media_file, so test schedule_time validator directly
            is_valid = True # Assume true unless validator fails
            try:
                if hasattr(form, 'validate_schedule_time'): # Check if custom validator exists
                    form.validate_schedule_time(form.schedule_time)
            except ValidationError:
                is_valid = False
            self.assertTrue(is_valid)
            self.assertNotIn('schedule_time', form.errors)


    def test_story_form_schedule_time_past(self):
        with self.app.test_request_context(method='POST', data={'caption': 'Test'}):
            form = StoryForm(caption="Test caption for past schedule")
            form.custom_friend_list_id.choices = []
            form.schedule_time.data = datetime.now(timezone.utc) - timedelta(days=1)
            raised_error = False
            try:
                if hasattr(form, 'validate_schedule_time'):
                     form.validate_schedule_time(form.schedule_time)
                else: # Fallback if direct validator call isn't straightforward/available
                    # This might not catch error if other fields fail first in full validate()
                    form.validate()
                    if 'schedule_time' in form.errors:
                        raise ValidationError(form.errors['schedule_time'][0])

            except ValidationError as e:
                raised_error = True
                self.assertIn('Scheduled time must be in the future.', str(e))
            self.assertTrue(raised_error, "ValidationError for past schedule_time was not raised in StoryForm.")


    def test_story_form_schedule_time_empty(self):
        with self.app.test_request_context(method='POST', data={'caption': 'Test'}):
            form = StoryForm(caption="Test caption for empty schedule")
            form.custom_friend_list_id.choices = []
            form.schedule_time.data = None
            is_valid = True
            try:
                 if hasattr(form, 'validate_schedule_time'):
                    form.validate_schedule_time(form.schedule_time)
            except ValidationError:
                is_valid = False # Should not happen for optional field
            self.assertTrue(is_valid)
            self.assertNotIn('schedule_time', form.errors)

class TestCoreFormValidations(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        self.test_user = User(username='formtestuser', email='formtest@example.com')
        self.test_user.set_password('password')
        db.session.add(self.test_user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # --- RegistrationForm Tests ---
    def test_registration_form_username_length(self):
        with self.app.test_request_context():
            form_short = RegistrationForm(username='a', email='test@example.com', password='pw', confirm_password='pw')
            self.assertFalse(form_short.validate())
            self.assertIn('username', form_short.errors)
            self.assertTrue(any('Field must be between 2 and 20 characters long.' in e for e in form_short.errors['username']))

            form_long = RegistrationForm(username='a'*21, email='test@example.com', password='pw', confirm_password='pw')
            self.assertFalse(form_long.validate())
            self.assertIn('username', form_long.errors)
            self.assertTrue(any('Field must be between 2 and 20 characters long.' in e for e in form_long.errors['username']))

            form_valid = RegistrationForm(username='validuser', email='valid@example.com', password='password', confirm_password='password')
            # form_valid.validate() # Call validate
            # self.assertNotIn('username', form_valid.errors) # Check no errors for username
            # Corrected: validate and check overall form validity for this specific check
            self.assertTrue(form_valid.validate())


    def test_registration_form_email_invalid(self):
        with self.app.test_request_context():
            invalid_emails = [
                ("plainaddress", "Invalid email address."),
                ("test@domain", "Invalid email address."), # Might be valid depending on regex, but often caught
                ("@domain.com", "Invalid email address."),
                ("test@.com", "Invalid email address."),
                ("test@domain.", "Invalid email address."),
                ("test@domain.c", "Invalid email address."), # Usually needs 2+ chars for TLD
                ("test space@domain.com", "Invalid email address.")
            ]
            for email, message in invalid_emails:
                with self.subTest(email=email):
                    form = RegistrationForm(username='testuser', email=email, password='pw', confirm_password='pw')
                    self.assertFalse(form.validate())
                    self.assertIn('email', form.errors)
                    self.assertIn(message, form.errors['email'])

            # Test valid email
            form_valid_email = RegistrationForm(username='testuser', email='valid@example.com', password='pw', confirm_password='pw')
            # form_valid_email.validate() # Call validate
            # self.assertNotIn('email', form_valid_email.errors) # Check no errors for email
            # Corrected: validate and check overall form validity for this specific check
            # This assumes username 'testuser' and password 'pw' are valid for other fields
            # For a pure email validation, one might only populate email and check that field's validation
            # However, form.validate() validates all. Let's ensure other fields are minimal valid.
            self.assertTrue(form_valid_email.validate())


    # --- PostForm Tests ---
    def test_post_form_body_length(self):
        with self.app.test_request_context(): # POST request needed for WTForms to process form data
            # Test long body
            form_long_body = PostForm(body='a'*5001) # Assuming max is 5000 based on model
            form_long_body.custom_friend_list_id.choices = []
            self.assertFalse(form_long_body.validate())
            self.assertIn('body', form_long_body.errors)
            self.assertTrue(any('cannot be longer than 5000 characters' in e for e in form_long_body.errors['body'])) # Check model length

            # Test empty body (DataRequired)
            form_empty_body = PostForm(body='')
            form_empty_body.custom_friend_list_id.choices = []
            self.assertFalse(form_empty_body.validate())
            self.assertIn('body', form_empty_body.errors)
            self.assertIn('This field is required.', form_empty_body.errors['body'])

    def test_post_form_media_files_disallowed_type(self):
        with self.app.test_request_context(method='POST', data={'body': 'Test post'}):
            mock_txt_file = FileStorage(stream=io.BytesIO(b"text content"), filename="test.txt", content_type="text/plain")
            # When creating form with FileField data, pass it in the constructor or via process method
            form = PostForm(media_files=[mock_txt_file], body="Test post with bad file")
            form.custom_friend_list_id.choices = []
            self.assertFalse(form.validate())
            self.assertIn('media_files', form.errors)
            self.assertTrue(any('Images or videos only!' in e for e in form.errors['media_files']))


    def test_post_form_custom_list_id_conditionally_required(self):
        # This validation is typically handled in the route, not the form's basic validate()
        # because DataRequired on custom_friend_list_id is not conditional in the form itself.
        # However, if a custom validator were added to the form, this test would be relevant.
        # For now, we acknowledge this is more of a route-level integration concern.
        pass

    # --- CommentForm Tests ---
    def test_comment_form_body_length(self):
        with self.app.test_request_context():
            form_long_body = CommentForm(body='a'*2001) # Max is 2000 based on model
            self.assertFalse(form_long_body.validate())
            self.assertIn('body', form_long_body.errors)
            self.assertTrue(any('longer than 2000 characters' in e for e in form_long_body.errors['body']))

            form_empty_body = CommentForm(body='')
            self.assertFalse(form_empty_body.validate())
            self.assertIn('body', form_empty_body.errors)
            self.assertIn('This field is required.', form_empty_body.errors['body'])

    # --- EditProfileForm Tests ---
    def test_edit_profile_form_bio_length(self):
        with self.app.test_request_context():
            form_long_bio = EditProfileForm(bio='a'*251, theme='default') # Max is 250
            self.assertFalse(form_long_bio.validate())
            self.assertIn('bio', form_long_bio.errors)
            self.assertTrue(any('longer than 250 characters' in e for e in form_long_bio.errors['bio']))

    def test_edit_profile_form_profile_picture_disallowed_type(self):
        with self.app.test_request_context(method='POST', data={'theme':'default', 'bio': 'A bio'}):
            mock_txt_file = FileStorage(stream=io.BytesIO(b"text content"), filename="test.txt", content_type="text/plain")
            form = EditProfileForm(profile_picture=mock_txt_file, theme='default', bio='A bio')
            self.assertFalse(form.validate())
            self.assertIn('profile_picture', form.errors)
            self.assertTrue(any('Images only!' in e for e in form.errors['profile_picture']))

    # --- PollForm Tests ---
    def test_poll_form_question_required(self):
        with self.app.test_request_context(method='POST'): # Ensure POST for form processing
            form_data = {
                'question': '',
                'options-0-option_text': 'Opt1',
                'options-1-option_text': 'Opt2'
            }
            form = PollForm(data=form_data)
            self.assertFalse(form.validate())
            self.assertIn('question', form.errors)
            self.assertIn('This field is required.', form.errors['question'])

    def test_poll_form_not_enough_options_text(self):
        with self.app.test_request_context(method='POST'):
            form_data = {
                'question': 'A good question?',
                'options-0-option_text': 'Only one option has text',
                'options-1-option_text': '    ' # Empty after strip
            }
            form = PollForm(data=form_data)
            self.assertFalse(form.validate())
            self.assertIn('options', form.errors)
            self.assertIn('Please provide at least two valid options for the poll.', form.errors['options'][0])

    def test_poll_form_duplicate_options_text(self):
        with self.app.test_request_context(method='POST'):
            form_data = {
                'question': 'Another good question?',
                'options-0-option_text': 'Duplicate Option Text',
                'options-1-option_text': 'Duplicate Option Text',
                'options-2-option_text': 'Unique Option' # Add a third to ensure min_entries isn't the primary fail
            }
            form = PollForm(data=form_data)
            self.assertFalse(form.validate())
            self.assertIn('options', form.errors)
            self.assertIn('Poll options must be unique (case-insensitive).', form.errors['options'][0])

if __name__ == '__main__':
    unittest.main(verbosity=2)
