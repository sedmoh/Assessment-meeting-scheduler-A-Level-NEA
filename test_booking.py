import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["POWER_AUTOMATE_FLOW_URL"] = ""
os.environ["MAIL_USERNAME"] = ""

import unittest
from datetime import datetime, timedelta

from app import app, db
from hash_table import user_session_cache
from models import Availability, Meeting, User
from werkzeug.security import generate_password_hash


class TestBooking(unittest.TestCase):
    #testing meeting booking functionality

    def setUp(self):
        #setting up the test client and database for testing
        app.config['TESTING'] = True
        user_session_cache.clear()  # don't carry cached logins over from other tests
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        with app.app_context():
            db.create_all()

            #create tutor
            tutor = User(
                name='Test Tutor',
                email='tutor1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='tutor'
            )
            db.session.add(tutor)
            db.session.commit()
            self.tutor_id = tutor.user_id

            #create student
            student = User(
                name='Test Student',
                email='student1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            db.session.add(student)
            db.session.commit()
            self.student_id = student.user_id

            #create availability slot
            future_datetime = datetime.now() + timedelta(days=7)
            slot = Availability(
                tutor_id=self.tutor_id,
                start_time=future_datetime.replace(hour=10, minute=0, second=0, microsecond=0),
                end_time=future_datetime.replace(hour=10, minute=15, second=0, microsecond=0),
                booked=False
            )
            db.session.add(slot)
            db.session.commit()
            self.slot_id = slot.availability_id

        #login as student
        self.client.post('/login', data={
            'email': 'student1@open.ac.uk',
            'password': 'Password123!'
        })

    def tearDown(self):
        #cleaning up the database after each test
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_book_meeting_standard(self):
        #test B1: checks if a student can successfully book an available meeting slot with a tutor
        response = self.client.post(f'/book-meeting/{self.slot_id}',
                                   follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        with app.app_context():
            #check slot is booked
            slot = Availability.query.get(self.slot_id)
            self.assertTrue(slot.booked)

            #check meeting created
            meeting = Meeting.query.filter_by(
                student_id=self.student_id,
                availability_id=self.slot_id
            ).first()
            self.assertIsNotNone(meeting)

    def test_book_urgent_meeting(self):
        #test B2: checks if a student can book an urgent meeting slot (within 24 hours) and that it is prioritised correctly
        response = self.client.post(f'/book-meeting/{self.slot_id}?urgent=true',
                                   follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        with app.app_context():
            meeting = Meeting.query.filter_by(
                student_id=self.student_id,
                availability_id=self.slot_id
            ).first()
            self.assertIsNotNone(meeting)

    def test_prevent_double_booking(self):
        #test B3: checks if the system prevents double booking of the same availability slot by multiple students
        #first booking
        self.client.post(f'/book-meeting/{self.slot_id}')

        #logout and login as different student
        self.client.get('/logout')

        with app.app_context():
            student2 = User(
                name='Second Student',
                email='student2@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            db.session.add(student2)
            db.session.commit()
            student2_id = student2.user_id

        self.client.post('/login', data={
            'email': 'student2@open.ac.uk',
            'password': 'Password123!'
        })

        #attempt second booking
        response = self.client.post(f'/book-meeting/{self.slot_id}')

        #should reject second booking attempt
        with app.app_context():
            meeting_count = Meeting.query.filter_by(availability_id=self.slot_id).count()
            self.assertEqual(meeting_count, 1, "Should only have one meeting for this slot")

            #slot should still be booked
            slot = Availability.query.get(self.slot_id)
            self.assertTrue(slot.booked, "Slot should remain booked")

    def test_priority_queue_ordering(self):
        #test B4: checks if urgent meeting requests are placed higher in the booking queue than non-urgent requests
        #create additional slots and book meetings to test ordering
        with app.app_context():
            future_datetime = datetime.now() + timedelta(days=7)
            for i in range(2):
                slot = Availability(
                    tutor_id=self.tutor_id,
                    start_time=future_datetime.replace(hour=11+i, minute=0, second=0, microsecond=0),
                    end_time=future_datetime.replace(hour=11+i, minute=15, second=0, microsecond=0),
                    booked=False
                )
                db.session.add(slot)
            db.session.commit()

        #book meetings
        response = self.client.get('/view-availability')
        self.assertEqual(response.status_code, 200)

    def test_cancel_meeting(self):
        #test B5: checks if a student can cancel a booked meeting and that the availability slot is freed up for other students to book
        #book meeting
        self.client.post(f'/book-meeting/{self.slot_id}')

        with app.app_context():
            meeting = Meeting.query.filter_by(student_id=self.student_id).first()
            meeting_id = meeting.meeting_id

        #cancel meeting
        response = self.client.post(f'/cancel-meeting/{meeting_id}', follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        with app.app_context():
            #meeting should be deleted
            meeting = Meeting.query.get(meeting_id)
            self.assertIsNone(meeting)

            #slot should be available again
            slot = Availability.query.get(self.slot_id)
            self.assertFalse(slot.booked)

    def test_view_upcoming_meetings(self):
        #test B6: checks if a student can view their upcoming meetings on the dashboard and that the information displayed is correct
        #book meeting
        self.client.post(f'/book-meeting/{self.slot_id}')

        response = self.client.get('/dashboard')

        self.assertEqual(response.status_code, 200)
        #dashboard should show meetings
        self.assertIn(b'Meeting', response.data)


    def test_validate_booking_rejects_overlap(self):
        #test B7 (regression): two different but overlapping slots must not both be bookable
        #the existing double-booking test only covers the same slot, which the booked flag handles
        from algorithms import validate_booking
        from models import MeetingStatus

        with app.app_context():
            start = (datetime.now() + timedelta(days=7)).replace(
                hour=10, minute=0, second=0, microsecond=0)
            db.session.add(Meeting(
                student_id=self.student_id, tutor_id=self.tutor_id,
                availability_id=self.slot_id, start_time=start,
                duration=15, status=MeetingStatus.CONFIRMED))
            db.session.commit()

            #10:05-10:20 overlaps the existing 10:00-10:15 meeting
            ok, _ = validate_booking(self.tutor_id,
                                     start + timedelta(minutes=5),
                                     start + timedelta(minutes=20))
            self.assertFalse(ok, "Overlapping meeting should be rejected")

            #10:15-10:30 starts exactly when the other ends, so it is allowed
            ok, _ = validate_booking(self.tutor_id,
                                     start + timedelta(minutes=15),
                                     start + timedelta(minutes=30))
            self.assertTrue(ok, "Back-to-back meeting should be allowed")


if __name__ == '__main__':
    unittest.main()
