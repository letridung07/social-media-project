import unittest
from datetime import datetime, timezone, timedelta
import uuid
from icalendar import Calendar, Event as IcsEvent

# Assuming app.utils and app.models.Event are structured such that they can be imported.
# For isolated unit testing, we might mock AppEventModel if it's complex to instantiate.
# from app.core.models import Event as AppEventModel # This might require Flask app context
from app.utils.helpers import generate_ics_file

# A simple mock class for Event model for utility testing
class MockAppEventModel:
    def __init__(self, name, start_datetime, end_datetime, calendar_uid, description=None, location=None):
        self.name = name
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.calendar_uid = calendar_uid
        self.description = description
        self.location = location
        # Add other fields if generate_ics_file uses them, e.g., organizer, attendees for different tests.
        # For current generate_ics_file, these are not directly used in ICS properties.

class TestIcsGenerationUtils(unittest.TestCase):

    def test_basic_event_ics_generation(self):
        """Test ICS generation for an event with basic details."""
        event_uid = str(uuid.uuid4())
        start_dt = datetime.now(timezone.utc) + timedelta(days=1)
        end_dt = start_dt + timedelta(hours=2)

        mock_event = MockAppEventModel(
            name="Basic Test Event",
            start_datetime=start_dt,
            end_datetime=end_dt,
            calendar_uid=event_uid
        )

        ics_content = generate_ics_file(mock_event)
        self.assertIsInstance(ics_content, bytes)

        cal = Calendar.from_ical(ics_content)

        self.assertEqual(len(cal.walk('VEVENT')), 1) # Check for one event

        ics_event_component = cal.walk('VEVENT')[0]
        self.assertEqual(ics_event_component.get('summary'), mock_event.name)
        self.assertEqual(ics_event_component.get('uid'), event_uid)

        # Verify DTSTART and DTEND (icalendar returns datetime objects)
        # These should be timezone-aware and in UTC
        self.assertEqual(ics_event_component.get('dtstart').dt, start_dt)
        self.assertEqual(ics_event_component.get('dtend').dt, end_dt)
        self.assertIsNotNone(ics_event_component.get('dtstart').dt.tzinfo)
        self.assertEqual(ics_event_component.get('dtstart').dt.tzinfo, timezone.utc)
        self.assertIsNotNone(ics_event_component.get('dtend').dt.tzinfo)
        self.assertEqual(ics_event_component.get('dtend').dt.tzinfo, timezone.utc)

        self.assertIsNotNone(ics_event_component.get('dtstamp'))


    def test_full_details_event_ics_generation(self):
        """Test ICS generation for an event with all details."""
        event_uid = str(uuid.uuid4())
        start_dt = datetime(2024, 8, 15, 14, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime(2024, 8, 15, 16, 0, 0, tzinfo=timezone.utc)

        mock_event = MockAppEventModel(
            name="Full Detail Event",
            description="This is a detailed description of the event.",
            start_datetime=start_dt,
            end_datetime=end_dt,
            location="Test Location, 123 Test St",
            calendar_uid=event_uid
        )

        ics_content = generate_ics_file(mock_event)
        cal = Calendar.from_ical(ics_content)
        self.assertEqual(len(cal.walk('VEVENT')), 1)

        ics_event_component = cal.walk('VEVENT')[0]
        self.assertEqual(ics_event_component.get('summary'), mock_event.name)
        self.assertEqual(ics_event_component.get('description'), mock_event.description)
        self.assertEqual(ics_event_component.get('location'), mock_event.location)
        self.assertEqual(ics_event_component.get('uid'), event_uid)
        self.assertEqual(ics_event_component.get('dtstart').dt, start_dt)
        self.assertEqual(ics_event_component.get('dtend').dt, end_dt)
        self.assertIsNotNone(ics_event_component.get('dtstamp').dt)

    def test_event_with_naive_datetimes(self):
        """Test ICS generation when event datetimes are naive (should be treated as UTC)."""
        event_uid = str(uuid.uuid4())
        # Naive datetime objects
        naive_start_dt = datetime(2024, 9, 1, 10, 0, 0)
        naive_end_dt = datetime(2024, 9, 1, 12, 0, 0)

        mock_event = MockAppEventModel(
            name="Naive Datetime Event",
            start_datetime=naive_start_dt,
            end_datetime=naive_end_dt,
            calendar_uid=event_uid
        )

        ics_content = generate_ics_file(mock_event)
        cal = Calendar.from_ical(ics_content)
        self.assertEqual(len(cal.walk('VEVENT')), 1)

        ics_event_component = cal.walk('VEVENT')[0]

        # Expected UTC datetimes
        expected_utc_start = naive_start_dt.replace(tzinfo=timezone.utc)
        expected_utc_end = naive_end_dt.replace(tzinfo=timezone.utc)

        dtstart_from_ics = ics_event_component.get('dtstart').dt
        dtend_from_ics = ics_event_component.get('dtend').dt

        self.assertEqual(dtstart_from_ics, expected_utc_start)
        self.assertIsNotNone(dtstart_from_ics.tzinfo)
        self.assertEqual(dtstart_from_ics.tzinfo, timezone.utc)

        self.assertEqual(dtend_from_ics, expected_utc_end)
        self.assertIsNotNone(dtend_from_ics.tzinfo)
        self.assertEqual(dtend_from_ics.tzinfo, timezone.utc)

        self.assertEqual(ics_event_component.get('uid'), event_uid)
        self.assertEqual(ics_event_component.get('summary'), mock_event.name)

if __name__ == '__main__':
    unittest.main()
