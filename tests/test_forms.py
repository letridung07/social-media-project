import unittest
from flask import Flask
from datetime import datetime, timedelta, timezone # Added timezone for consistency
from app import create_app, db # Added db for completeness if any form needs it, though not directly used here
from app.forms import PostForm, StoryForm
from app.models import User # Required for PostForm/StoryForm if they access current_user or have User-dependent fields indirectly

class TestSchedulingForms(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_name='testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        # db.create_all() # Not strictly needed if forms don't interact with DB directly for these tests
        # However, if forms populate choices from DB (e.g. friend lists), it might be needed.
        # For schedule_time field, it's not directly needed.

        # A user might be needed if forms implicitly rely on current_user, even if not directly used in these fields
        # For simplicity, we'll assume forms can be instantiated without a logged-in user for these specific field tests.

    def tearDown(self):
        # db.session.remove()
        # db.drop_all()
        self.app_context.pop()

    def test_post_form_schedule_time_future(self):
        with self.app.test_request_context('/'): # Provides context for URL building if needed by forms, and session
            # Minimal data for PostForm to pass validation for other fields
            form = PostForm(body="Test body for future schedule")
            form.schedule_time.data = datetime.now() + timedelta(days=1)
            # Validate only the specific field if other fields have complex requirements not met here
            # For a full form.validate(), ensure all DataRequired fields are populated.
            # Here, we assume schedule_time validator can be tested somewhat independently or other fields are met.
            is_valid = form.schedule_time.validate(form) # This will call validate_schedule_time
            self.assertTrue(is_valid) # Should be true as it's a future date
            self.assertNotIn('schedule_time', form.errors)

    def test_post_form_schedule_time_past(self):
        with self.app.test_request_context('/'):
            form = PostForm(body="Test body for past schedule") # Provide data for required fields
            form.schedule_time.data = datetime.now() - timedelta(days=1)

            # To properly test form.validate() and populate form.errors:
            # We need to ensure the form is processed as it would be in a request.
            # WTForms typically populates .errors when form.validate() is called.
            # The custom validator raises ValidationError, which WTForms catches.

            # Simulate form submission for PostForm (body is required)
            # class MockField:
            #     def __init__(self, data):
            #         self.data = data
            # class MockForm:
            #     def __init__(self, schedule_time_data, body_data="Test"):
            #         self.schedule_time = MockField(schedule_time_data)
            #         self.body = MockField(body_data) # Assuming body is required

            # mock_form_data = MockForm(schedule_time_data = datetime.now() - timedelta(days=1))
            # form.process(formdata=None, obj=mock_form_data) # This is more for obj data, not form submission

            # Let's try validating the field directly for simplicity as per original goal
            # The validate_<fieldname> methods are called by field.validate() or form.validate()
            try:
                form.schedule_time.validate(form, (form.schedule_time,)) # Call field's validate method
                # If it doesn't raise an error, the test should fail
                raised_error = False
            except ValidationError as e:
                raised_error = True
                self.assertIn('Scheduled time must be in the future.', str(e))

            self.assertTrue(raised_error, "ValidationError for past schedule_time was not raised.")


    def test_post_form_schedule_time_empty(self):
        with self.app.test_request_context('/'):
            form = PostForm(body="Test body for empty schedule") # Provide data for required fields
            form.schedule_time.data = None
            is_valid = form.schedule_time.validate(form) # Optional validator should not raise error
            self.assertTrue(is_valid)
            self.assertNotIn('schedule_time', form.errors) # Should be no errors for this field as it's optional

    # Similar tests for StoryForm
    def test_story_form_schedule_time_future(self):
        with self.app.test_request_context('/'):
            # StoryForm requires media_file. For this unit test, we focus on schedule_time.
            # We can pass dummy data or mock the field if its absence prevents validation.
            # For simplicity, assume we can test schedule_time somewhat independently.
            form = StoryForm(caption="Test caption for future schedule") # media_file is DataRequired
            form.schedule_time.data = datetime.now() + timedelta(days=1)
            is_valid = form.schedule_time.validate(form)
            self.assertTrue(is_valid)
            self.assertNotIn('schedule_time', form.errors)

    def test_story_form_schedule_time_past(self):
        with self.app.test_request_context('/'):
            form = StoryForm(caption="Test caption for past schedule") # media_file is DataRequired
            form.schedule_time.data = datetime.now() - timedelta(days=1)
            try:
                form.schedule_time.validate(form, (form.schedule_time,))
                raised_error = False
            except ValidationError as e:
                raised_error = True
                self.assertIn('Scheduled time must be in the future.', str(e))
            self.assertTrue(raised_error, "ValidationError for past schedule_time was not raised in StoryForm.")

    def test_story_form_schedule_time_empty(self):
        with self.app.test_request_context('/'):
            form = StoryForm(caption="Test caption for empty schedule") # media_file is DataRequired
            form.schedule_time.data = None
            is_valid = form.schedule_time.validate(form) # Optional should not raise error
            self.assertTrue(is_valid)
            self.assertNotIn('schedule_time', form.errors)

if __name__ == '__main__':
    unittest.main(verbosity=2)
