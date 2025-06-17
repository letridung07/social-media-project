import unittest
from datetime import datetime, timedelta
from app import create_app, db
from app.models import User, Event, Notification
# EventForm might be needed if we test form validation directly,
# but for route testing, we often just post data.
# from app.forms import EventForm
from config import TestingConfig

class EventTestCase(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # Create test users
        self.user1_username = 'user1'
        self.user1_email = 'user1@example.com'
        self.user1_password = 'password123'
        self.user1 = User(username=self.user1_username, email=self.user1_email)
        self.user1.set_password(self.user1_password)

        self.user2_username = 'user2'
        self.user2_email = 'user2@example.com'
        self.user2_password = 'password456'
        self.user2 = User(username=self.user2_username, email=self.user2_email)
        self.user2.set_password(self.user2_password)

        db.session.add_all([self.user1, self.user2])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.app.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.app.get('/logout', follow_redirects=True)

    # --- Test Cases Start Here ---

    def test_event_model_creation(self):
        # Test creating an Event model instance
        now = datetime.utcnow()
        event = Event(name='Test Event',
                      description='A great event',
                      start_datetime=now + timedelta(days=1),
                      end_datetime=now + timedelta(days=1, hours=2),
                      location='Online',
                      organizer_id=self.user1.id)
        db.session.add(event)
        db.session.commit()

        retrieved_event = Event.query.filter_by(name='Test Event').first()
        self.assertIsNotNone(retrieved_event)
        self.assertEqual(retrieved_event.description, 'A great event')
        self.assertEqual(retrieved_event.organizer_id, self.user1.id)
        self.assertEqual(retrieved_event.organizer, self.user1)

    def test_create_event_page_get(self):
        # Log in user1
        self._login(self.user1_email, self.user1_password)

        response = self.app.get('/event/create')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Create New Event', response.data)
        self.assertIn(b'Event Name', response.data) # Check for form field
        self._logout()

    def test_create_event_post_successful(self):
        self._login(self.user1_email, self.user1_password)

        event_name = "Charity Gala"
        event_description = "A wonderful evening for a good cause."
        start_time = datetime.utcnow() + timedelta(days=10)
        end_time = start_time + timedelta(hours=3)
        location = "Grand Ballroom"

        response = self.app.post('/event/create', data=dict(
            name=event_name,
            description=event_description,
            start_datetime=start_time.strftime('%Y-%m-%dT%H:%M'),
            end_datetime=end_time.strftime('%Y-%m-%dT%H:%M'),
            location=location
        ), follow_redirects=True)

        self.assertEqual(response.status_code, 200) # Should redirect to event view or list
        self.assertIn(b'Event created successfully!', response.data) # Flash message

        created_event = Event.query.filter_by(name=event_name).first()
        self.assertIsNotNone(created_event)
        self.assertEqual(created_event.organizer_id, self.user1.id)
        self.assertEqual(created_event.description, event_description)
        self.assertEqual(created_event.location, location)
        # Timestamps might have slight precision differences when stored and retrieved
        self.assertAlmostEqual(created_event.start_datetime, start_time, delta=timedelta(seconds=1))
        self.assertAlmostEqual(created_event.end_datetime, end_time, delta=timedelta(seconds=1))

        # Check if redirected to the event detail page (common pattern)
        self.assertIn(bytes(event_name, 'utf-8'), response.data) # Event name on detail page
        self.assertIn(bytes(location, 'utf-8'), response.data)

        self._logout()

    def test_create_event_not_logged_in(self):
        response = self.app.get('/event/create', follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Redirects to login
        self.assertIn(b'Sign In', response.data) # Check for login page content

        response_post = self.app.post('/event/create', data=dict(
            name="Unauthorized Event"
            # other fields...
        ), follow_redirects=True)
        self.assertEqual(response_post.status_code, 200)
        self.assertIn(b'Sign In', response_post.data)
        self.assertIsNone(Event.query.filter_by(name="Unauthorized Event").first())

    def test_join_event(self):
        # User1 (organizer) creates an event
        self._login(self.user1_email, self.user1_password)
        event_name = "Community Workshop"
        start_time = datetime.utcnow() + timedelta(days=5)
        end_time = start_time + timedelta(hours=2)
        self.app.post('/event/create', data=dict(
            name=event_name,
            description="Learn new skills!",
            start_datetime=start_time.strftime('%Y-%m-%dT%H:%M'),
            end_datetime=end_time.strftime('%Y-%m-%dT%H:%M'),
            location="Local Library"
        ), follow_redirects=True)
        self._logout()

        event = Event.query.filter_by(name=event_name).first()
        self.assertIsNotNone(event)

        # User2 joins the event
        self._login(self.user2_email, self.user2_password)
        response = self.app.post(f'/event/{event.id}/join', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You are now attending', response.data)
        self.assertIn(self.user2, event.attendees)

        # Check for notification to organizer (user1)
        notification = Notification.query.filter_by(recipient_id=self.user1.id, type='event_join').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.user2.id)
        # self.assertEqual(notification.related_event_id, event.id) # This was commented out in routes, so test accordingly

        self._logout()

    def test_leave_event(self):
        # User1 (organizer) creates an event
        self._login(self.user1_email, self.user1_password)
        event_name = "Book Club Meeting"
        start_time = datetime.utcnow() + timedelta(days=3)
        end_time = start_time + timedelta(hours=1)
        self.app.post('/event/create', data=dict(
            name=event_name,
            description="Discussing 'The Great Novel'",
            start_datetime=start_time.strftime('%Y-%m-%dT%H:%M'),
            end_datetime=end_time.strftime('%Y-%m-%dT%H:%M'),
            location="Cafe Central"
        ), follow_redirects=True)
        self._logout()

        event = Event.query.filter_by(name=event_name).first()
        self.assertIsNotNone(event)

        # User2 joins the event first
        self._login(self.user2_email, self.user2_password)
        self.app.post(f'/event/{event.id}/join', follow_redirects=True)
        self.assertIn(self.user2, event.attendees) # Verify user2 is an attendee

        # User2 leaves the event
        response = self.app.post(f'/event/{event.id}/leave', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You are no longer attending', response.data)
        self.assertNotIn(self.user2, event.attendees)
        self._logout()

    def test_join_event_already_attending(self):
        self._login(self.user1_email, self.user1_password) # user1 is organizer
        event = Event(name="Workshop", start_datetime=datetime.utcnow() + timedelta(days=1), end_datetime=datetime.utcnow() + timedelta(days=1, hours=2), organizer=self.user1)
        db.session.add(event)
        db.session.commit()
        self._logout()

        self._login(self.user2_email, self.user2_password) # user2 will join
        self.app.post(f'/event/{event.id}/join', follow_redirects=True) # First join

        response = self.app.post(f'/event/{event.id}/join', follow_redirects=True) # Attempt to join again
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You are already attending', response.data)
        self._logout()

    def test_leave_event_not_attending(self):
        self._login(self.user1_email, self.user1_password) # user1 is organizer
        event = Event(name="Meetup", start_datetime=datetime.utcnow() + timedelta(days=1), end_datetime=datetime.utcnow() + timedelta(days=1, hours=2), organizer=self.user1)
        db.session.add(event)
        db.session.commit()
        self._logout()

        self._login(self.user2_email, self.user2_password) # user2 is not attending
        response = self.app.post(f'/event/{event.id}/leave', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You were not attending', response.data)
        self._logout()

    def test_join_own_event_as_organizer(self):
        # Organizer should not typically "join" their own event through the join button,
        # as they are already implicitly involved. However, the current logic
        # in routes.py `join_event` doesn't prevent an organizer from being added to attendees.
        # This test verifies current behavior. If behavior should change, test needs adjustment.
        self._login(self.user1_email, self.user1_password) # user1 is organizer
        event = Event(name="My Own Event", start_datetime=datetime.utcnow() + timedelta(days=1), end_datetime=datetime.utcnow() + timedelta(days=1, hours=2), organizer=self.user1)
        db.session.add(event)
        db.session.commit()

        response = self.app.post(f'/event/{event.id}/join', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        # Current logic might say "You are now attending" or "already attending" if organizer is auto-added.
        # Based on current route logic, an organizer can be added to event.attendees.
        self.assertIn(b'You are now attending', response.data)
        self.assertIn(self.user1, event.attendees)
        self._logout()

    def test_view_events_list(self):
        # Create a couple of events
        event1 = Event(name="Tech Conference", start_datetime=datetime.utcnow() + timedelta(days=2), end_datetime=datetime.utcnow() + timedelta(days=2, hours=8), organizer=self.user1, location="Convention Center")
        event2 = Event(name="Art Exhibition", start_datetime=datetime.utcnow() + timedelta(days=4), end_datetime=datetime.utcnow() + timedelta(days=4, hours=4), organizer=self.user2, location="City Gallery")
        db.session.add_all([event1, event2])
        db.session.commit()

        self._login(self.user1_email, self.user1_password) # Login to view
        response = self.app.get('/events')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Upcoming Events', response.data)
        self.assertIn(b'Tech Conference', response.data)
        self.assertIn(b'Art Exhibition', response.data)
        self.assertIn(b'Convention Center', response.data)
        self.assertIn(b'City Gallery', response.data)
        self._logout()

    def test_view_event_detail(self):
        now = datetime.utcnow()
        event = Event(name="Music Festival",
                      description="Weekend of live music.",
                      start_datetime=now + timedelta(days=7),
                      end_datetime=now + timedelta(days=9, hours=2),
                      location="Open Air Park",
                      organizer=self.user1)
        event.attendees.append(self.user2) # user2 is an attendee
        db.session.add(event)
        db.session.commit()

        self._login(self.user1_email, self.user1_password) # Login to view
        response = self.app.get(f'/event/{event.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Music Festival', response.data)
        self.assertIn(b'Weekend of live music.', response.data)
        self.assertIn(b'Open Air Park', response.data)
        self.assertIn(bytes(self.user1.username, 'utf-8'), response.data) # Organizer
        self.assertIn(bytes(self.user2.username, 'utf-8'), response.data) # Attendee

        # Check for edit/delete buttons if current_user is organizer
        self.assertIn(b'Edit Event', response.data)
        self.assertIn(b'Delete Event', response.data)
        self._logout()

        # Check view as attendee (user2)
        self._login(self.user2_email, self.user2_password)
        response_user2 = self.app.get(f'/event/{event.id}')
        self.assertEqual(response_user2.status_code, 200)
        self.assertIn(b'Music Festival', response_user2.data)
        self.assertIn(b'Leave Event', response_user2.data) # Attendee should see leave button
        self.assertNotIn(b'Edit Event', response_user2.data)
        self._logout()

        # Check view as non-attendee, non-organizer (would need a user3 or test anonymous if allowed)
        # For now, this covers basic detail display and conditional buttons for organizer/attendee

    def test_edit_event_by_organizer(self):
        self._login(self.user1_email, self.user1_password) # user1 is organizer
        original_name = "Old Event Name"
        start_time = datetime.utcnow() + timedelta(days=1)
        event = Event(name=original_name, description="Original Description",
                      start_datetime=start_time,
                      end_datetime=start_time + timedelta(hours=2),
                      location="Old Location", organizer=self.user1)
        # Add an attendee to test notification later
        event.attendees.append(self.user2)
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        self._logout()

        self._login(self.user1_email, self.user1_password) # Log in as organizer again
        updated_name = "New Event Name"
        updated_description = "Updated Description"
        updated_location = "New Location"
        updated_start_time = start_time + timedelta(days=1)
        updated_end_time = updated_start_time + timedelta(hours=3)

        response_get = self.app.get(f'/event/{event_id}/edit')
        self.assertEqual(response_get.status_code, 200)
        self.assertIn(bytes(original_name, 'utf-8'), response_get.data)

        response_post = self.app.post(f'/event/{event_id}/edit', data=dict(
            name=updated_name,
            description=updated_description,
            start_datetime=updated_start_time.strftime('%Y-%m-%dT%H:%M'),
            end_datetime=updated_end_time.strftime('%Y-%m-%dT%H:%M'),
            location=updated_location
        ), follow_redirects=True)

        self.assertEqual(response_post.status_code, 200)
        self.assertIn(b'Event updated successfully!', response_post.data)
        self.assertIn(bytes(updated_name, 'utf-8'), response_post.data) # Check if new name is on detail page

        updated_event = Event.query.get(event_id)
        self.assertEqual(updated_event.name, updated_name)
        self.assertEqual(updated_event.description, updated_description)
        self.assertEqual(updated_event.location, updated_location)
        self.assertAlmostEqual(updated_event.start_datetime, updated_start_time, delta=timedelta(seconds=1))
        self.assertAlmostEqual(updated_event.end_datetime, updated_end_time, delta=timedelta(seconds=1))

        # Check for notification to attendee (user2)
        notification = Notification.query.filter_by(recipient_id=self.user2.id, type='event_updated', related_event_id=event_id).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.user1.id)
        self._logout()

    def test_edit_event_by_non_organizer(self):
        self._login(self.user1_email, self.user1_password) # user1 is organizer
        event = Event(name="Non-Organizer Edit Test", start_datetime=datetime.utcnow() + timedelta(days=1),
                      end_datetime=datetime.utcnow() + timedelta(days=1, hours=1), organizer=self.user1)
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        self._logout()

        self._login(self.user2_email, self.user2_password) # Log in as user2 (non-organizer)
        response_get = self.app.get(f'/event/{event_id}/edit')
        self.assertEqual(response_get.status_code, 403) # Forbidden

        response_post = self.app.post(f'/event/{event_id}/edit', data=dict(name="Attempted Update"), follow_redirects=True)
        self.assertEqual(response_post.status_code, 403) # Forbidden
        self._logout()

        # Verify event was not changed
        original_event = Event.query.get(event_id)
        self.assertEqual(original_event.name, "Non-Organizer Edit Test")


    def test_delete_event_by_organizer(self):
        self._login(self.user1_email, self.user1_password) # user1 is organizer
        event = Event(name="Event To Delete", start_datetime=datetime.utcnow() + timedelta(days=1),
                      end_datetime=datetime.utcnow() + timedelta(days=1, hours=1), organizer=self.user1)
        event.attendees.append(self.user2) # Add an attendee for notification testing
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        self._logout()

        self._login(self.user1_email, self.user1_password) # Log in as organizer
        response = self.app.post(f'/event/{event_id}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200) # Should redirect to events list
        self.assertIn(b'Event deleted successfully!', response.data)
        self.assertIsNone(Event.query.get(event_id))

        # Check for notification to attendee (user2)
        # Note: related_event_id might not be set in 'event_cancelled' if event is already deleted from DB before notification creation
        # The current implementation in routes.py for delete_event creates notifications *before* final deletion,
        # but related_event_id is commented out for cancellation notifs.
        # It stores event_name_for_notification. We test for the notification type and actor.
        notification = Notification.query.filter_by(recipient_id=self.user2.id, type='event_cancelled').first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.actor_id, self.user1.id)
        # self.assertIsNone(notification.related_event_id) # As per current route logic for delete.
                                                        # If related_event_id were to be set (e.g. if event id is passed differently), this would change.
                                                        # Actually, related_event_id is NOT set for 'event_cancelled' in the route code.

        self._logout()

    def test_delete_event_by_non_organizer(self):
        self._login(self.user1_email, self.user1_password) # user1 is organizer
        event = Event(name="Non-Organizer Delete Test", start_datetime=datetime.utcnow() + timedelta(days=1),
                      end_datetime=datetime.utcnow() + timedelta(days=1, hours=1), organizer=self.user1)
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        self._logout()

        self._login(self.user2_email, self.user2_password) # Log in as user2 (non-organizer)
        response = self.app.post(f'/event/{event_id}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 403) # Forbidden
        self._logout()

        self.assertIsNotNone(Event.query.get(event_id)) # Event should still exist


# --- Test Class for Event Calendar Export ---
from flask import url_for # Already imported globally in routes.py but good practice for test files
import icalendar # For parsing ICS content
import uuid # For generating calendar_uid for test event

class TestEventCalendarExportRoutes(unittest.TestCase):
    def setUp(self):
        self.app_instance = create_app(TestingConfig)
        self.app = self.app_instance.test_client()
        self.app_context = self.app_instance.app_context()
        self.app_context.push()
        db.create_all()

        # Create users
        self.organizer = User(username='organizer', email='organizer@example.com')
        self.organizer.set_password('password')
        self.attendee1 = User(username='attendee1', email='attendee1@example.com')
        self.attendee1.set_password('password')
        self.other_user = User(username='otheruser', email='other@example.com')
        self.other_user.set_password('password')

        db.session.add_all([self.organizer, self.attendee1, self.other_user])
        db.session.commit()

        # Create an event
        self.test_event = Event(
            name="Test Export Event",
            description="Event for ICS export testing.",
            start_datetime=datetime.utcnow() + timedelta(days=5),
            end_datetime=datetime.utcnow() + timedelta(days=5, hours=3),
            location="Test Location",
            organizer_id=self.organizer.id,
            calendar_uid=str(uuid.uuid4())
        )
        self.test_event.attendees.append(self.attendee1)
        db.session.add(self.test_event)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self, email, password):
        return self.app.post('/login', data=dict(
            email=email,
            password=password
        ), follow_redirects=True)

    def _logout(self):
        return self.app.get('/logout', follow_redirects=True)

    def test_export_calendar_by_organizer(self):
        self._login('organizer@example.com', 'password')
        with self.app_instance.app_context(): # Ensure url_for has app context
            response = self.app.get(url_for('main.export_calendar', event_id=self.test_event.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'text/calendar; charset=utf-8')
        self.assertIn('attachment; filename=', response.headers['Content-Disposition'])
        self.assertIn('.ics', response.headers['Content-Disposition'])

        # Check flash message
        # To check flash messages, we need to follow redirects if the route flashes and then returns a response
        # However, this route directly returns a file response, so flash messages might not be processed in the same way
        # by the test client unless the response is then fed into another request or the session is inspected.
        # For now, we'll assume the flash message is set. A more involved test could capture it.

        try:
            cal = icalendar.Calendar.from_ical(response.data)
            self.assertEqual(len(cal.walk('VEVENT')), 1)
            event_component = cal.walk('VEVENT')[0]
            self.assertEqual(str(event_component.get('uid')), self.test_event.calendar_uid)
            self.assertEqual(str(event_component.get('summary')), self.test_event.name)
        except Exception as e:
            self.fail(f"ICS content parsing failed: {e}")
        self._logout()

    def test_export_calendar_by_attendee(self):
        self._login('attendee1@example.com', 'password')
        with self.app_instance.app_context():
            response = self.app.get(url_for('main.export_calendar', event_id=self.test_event.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'text/calendar; charset=utf-8')
        self.assertIn('.ics', response.headers['Content-Disposition'])

        try:
            cal = icalendar.Calendar.from_ical(response.data)
            event_component = cal.walk('VEVENT')[0]
            self.assertEqual(str(event_component.get('uid')), self.test_event.calendar_uid)
        except Exception as e:
            self.fail(f"ICS content parsing failed for attendee: {e}")
        self._logout()

    def test_export_calendar_unauthorized_non_attendee(self):
        self._login('other@example.com', 'password')
        with self.app_instance.app_context():
            response = self.app.get(url_for('main.export_calendar', event_id=self.test_event.id), follow_redirects=True)

        # The route flashes and redirects. Status code after redirect might be 200.
        # We should check for the flash message content.
        self.assertIn(b'You are not authorized to export this event.', response.data)
        # Check if it redirected to the event view page or index (depends on route logic)
        # For this test, checking the flash message is a good indicator.
        self._logout()

    def test_export_calendar_anonymous_user(self):
        with self.app_instance.app_context():
            response = self.app.get(url_for('main.export_calendar', event_id=self.test_event.id), follow_redirects=True)

        self.assertIn(b'Sign In', response.data) # Should redirect to login page
        self.assertNotIn(b'event_Test_Export_Event.ics', response.data) # ICS content should not be there

    def test_export_calendar_event_not_found(self):
        self._login('organizer@example.com', 'password')
        non_existent_event_id = 99999
        with self.app_instance.app_context():
            response = self.app.get(url_for('main.export_calendar', event_id=non_existent_event_id))

        self.assertEqual(response.status_code, 404)
        self._logout()

if __name__ == '__main__':
    unittest.main(verbosity=2)
