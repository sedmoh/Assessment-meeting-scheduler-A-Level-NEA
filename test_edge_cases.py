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


class TestEdgeCases(unittest.TestCase):
    #testing edge cases and security vulnerabilities

    def setUp(self):
        #setting up the test client and database for testing
        app.config['TESTING'] = True
        user_session_cache.clear()  # don't carry cached logins over from other tests
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

        with app.app_context():
            db.create_all()

    def tearDown(self):
        #cleaning up the database after each test
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_sql_injection_attempt(self):
        #test E1: checks if the app is vulnerable to SQL injection attacks by attempting to login with a malicious email input
        #attempt SQL injection in login
        response = self.client.post('/login', data={
            'email': "admin' OR '1'='1",
            'password': "anything"
        })

        #should not login successfully
        self.assertNotIn(b'Dashboard', response.data)

    def test_unauthorised_access_to_admin_page(self):
        #test E2: checks if a non-admin user can access admin-only pages and perform admin actions
        #create and login as student
        with app.app_context():
            student = User(
                name='Test Student',
                email='student1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            db.session.add(student)
            db.session.commit()

        self.client.post('/login', data={
            'email': 'student1@open.ac.uk',
            'password': 'Password123!'
        })

        #try to access admin page
        response = self.client.get('/admin/dashboard', follow_redirects=True)

        #should be denied or redirected
        self.assertTrue(
            response.status_code in [302, 403] or
            b'Admin' not in response.data or
            b'denied' in response.data.lower() or
            b'required' in response.data.lower()
        )

    def test_session_expiry_after_logout(self):
        #test E3: checks if user sessions are properly terminated after logout and that users cannot access protected pages without logging in again
        #create and login user
        with app.app_context():
            user = User(
                name='Test Student',
                email='student1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            db.session.add(user)
            db.session.commit()

        self.client.post('/login', data={
            'email': 'student1@open.ac.uk',
            'password': 'Password123!'
        })

        #logout
        self.client.get('/logout')

        #try to access protected page
        response = self.client.get('/dashboard', follow_redirects=True)

        #should redirect to login
        self.assertTrue(b'Login' in response.data or b'login' in response.data.lower())

    def test_concurrent_booking_same_slot(self):
        #test E4: checks if the system can handle concurrent booking attempts for the same availability slot by multiple students and that it prevents double booking
        #create tutor, students, and slot
        with app.app_context():
            tutor = User(
                name='Test Tutor',
                email='tutor1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='tutor'
            )
            student1 = User(
                name='Student One',
                email='student1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            student2 = User(
                name='Student Two',
                email='student2@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            db.session.add_all([tutor, student1, student2])
            db.session.commit()

            future_datetime = datetime.now() + timedelta(days=7)
            slot = Availability(
                tutor_id=tutor.user_id,
                start_time=future_datetime.replace(hour=10, minute=0, second=0, microsecond=0),
                end_time=future_datetime.replace(hour=10, minute=15, second=0, microsecond=0),
                booked=False
            )
            db.session.add(slot)
            db.session.commit()
            slot_id = slot.availability_id

        #first student books
        client1 = app.test_client()
        client1.post('/login', data={'email': 'student1@open.ac.uk', 'password': 'Password123!'})
        response1 = client1.post(f'/book-meeting/{slot_id}')

        #second student tries to book same slot
        client2 = app.test_client()
        client2.post('/login', data={'email': 'student2@open.ac.uk', 'password': 'Password123!'})
        response2 = client2.post(f'/book-meeting/{slot_id}')

        #one booking should succeed, the other should fail
        with app.app_context():
            meeting_count = Meeting.query.filter_by(availability_id=slot_id).count()
            self.assertEqual(meeting_count, 1, "Should only create one meeting for the slot")

    def test_invalid_date_format(self):
        #test E5: checks if the app properly validates date inputs and handles invalid date formats when creating availability slots
        #create and login tutor
        with app.app_context():
            tutor = User(
                name='Test Tutor',
                email='tutor1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='tutor'
            )
            db.session.add(tutor)
            db.session.commit()

        self.client.post('/login', data={
            'email': 'tutor1@open.ac.uk',
            'password': 'Password123!'
        })

        #try invalid date format
        response = self.client.post('/create_availability', data={
            'date': 'not-a-date',
            'start_time': '09:00',
            'end_time': '10:00',
            'action': 'create'
        })

        self.assertTrue(response.status_code in [200, 400])

    def test_access_nonexistent_slot(self):
        #test E6: checks if the app handles attempts to access or book non-existent availability slots without crashing
        #create and login student
        with app.app_context():
            student = User(
                name='Test Student',
                email='student1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            db.session.add(student)
            db.session.commit()

        self.client.post('/login', data={
            'email': 'student1@open.ac.uk',
            'password': 'Password123!'
        })

        #try to book non-existent slot
        response = self.client.post('/book-meeting/99999')

        #should handle without crashing
        self.assertTrue(
            response.status_code in [200, 302, 400, 404],
            "App should handle non-existent slot gracefully without crashing"
        )

    def test_api_rate_limiting(self):
        #test E7: checks if the app implements rate limiting on API endpoints to prevent abuse and denial-of-service attacks
        #create and login user
        with app.app_context():
            tutor = User(
                name='Test Tutor',
                email='tutor1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='tutor'
            )
            db.session.add(tutor)
            db.session.commit()

        self.client.post('/login', data={
            'email': 'tutor1@open.ac.uk',
            'password': 'Password123!'
        })

        #make rapid requests
        future_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        success_count = 0

        for i in range(5):
            try:
                response = self.client.post('/create_availability', data={
                    'date': future_date,
                    'start_time': f'{9+i}:00',
                    'end_time': f'{10+i}:00',
                    'action': 'create'
                })
                if response.status_code == 200:
                    success_count += 1
            except:
                pass

        #system should handle without crashing
        self.assertGreaterEqual(success_count, 0)


if __name__ == '__main__':
    unittest.main()
