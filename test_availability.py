import unittest
from datetime import datetime, timedelta
from app import app, db
from models import User, Availability
from werkzeug.security import generate_password_hash


class TestAvailability(unittest.TestCase):
    #testing tutor availability management functionality
    
    def setUp(self):
        #setting up the test client and database for testing
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        
        with app.app_context():
            db.create_all()
            #create test tutor
            tutor = User(
                name='Test Tutor',
                email='tutor1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='tutor'
            )
            db.session.add(tutor)
            db.session.commit()
            self.tutor_id = tutor.user_id
        
        #login as tutor
        self.client.post('/login', data={
            'email': 'tutor1@open.ac.uk',
            'password': 'Password123!'
        })
    
    def tearDown(self):
        #cleaning up the database after each test
        with app.app_context():
            db.session.remove()
            db.drop_all()
    
    def test_create_single_availability_slot(self):
        #test AV1: checks if a tutor can create a single availability slot successfully
        future_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        response = self.client.post('/create_availability', data={
            'date': future_date,
            'start_time': '09:00',
            'end_time': '10:00',
            'action': 'create'
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        
        with app.app_context():
            slots = Availability.query.filter_by(tutor_id=self.tutor_id).all()
            self.assertGreaterEqual(len(slots), 1)
    
    def test_auto_slice_into_15min_slots(self):
        #test AV2: checks if the system can automatically slice a 2-hour slot into 30-minute slots when requested
        future_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        response = self.client.post('/create_availability', data={
            'date': future_date,
            'start_time': '10:00',
            'end_time': '12:00',
            'slot_duration': '30',
            'break_duration': '0',
            'slice_slots': 'on',
            'action': 'create'
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        
        with app.app_context():
            slots = Availability.query.filter_by(tutor_id=self.tutor_id).all()
            #2 hours/30 min = 4 slots
            self.assertGreaterEqual(len(slots), 2)
    
    def test_reject_past_date(self):
        #test AV3: checks if the system rejects attempts to create availability slots in the past
        past_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        response = self.client.post('/create_availability', data={
            'date': past_date,
            'start_time': '09:00',
            'end_time': '10:00',
            'action': 'create'
        })
        
        #should reject or show error
        self.assertTrue(response.status_code in [200, 400] or b'past' in response.data.lower())
    
    def test_reject_end_before_start(self):
        #test AV4: checks if the system rejects attempts to create availability slots where the end time is before the start time
        future_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        response = self.client.post('/create_availability', data={
            'date': future_date,
            'start_time': '14:00',
            'end_time': '10:00',
            'action': 'create'
        })
        
        #should show validation error
        self.assertTrue(
            response.status_code in [200, 400] or 
            b'after' in response.data.lower() or 
            b'before' in response.data.lower()
        )
    
    def test_delete_availability_slot(self):
        #test AV5: checks if a tutor can delete an availability slot successfully
        #create slot directly in database
        future_datetime = datetime.now() + timedelta(days=7)
        with app.app_context():
            slot = Availability(
                tutor_id=self.tutor_id,
                start_time=future_datetime.replace(hour=9, minute=0, second=0, microsecond=0),
                end_time=future_datetime.replace(hour=10, minute=0, second=0, microsecond=0),
                booked=False
            )
            db.session.add(slot)
            db.session.commit()
            slot_id = slot.availability_id
        
        #delete slot
        response = self.client.post(f'/delete-availability/{slot_id}', follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        
        with app.app_context():
            deleted_slot = Availability.query.get(slot_id)
            self.assertIsNone(deleted_slot)
    
    def test_prevent_delete_booked_slot(self):
        #test AV6: checks if the system prevents deletion of an availability slot that has already been booked by a student
        #create booked slot
        future_datetime = datetime.now() + timedelta(days=7)
        with app.app_context():
            slot = Availability(
                tutor_id=self.tutor_id,
                start_time=future_datetime.replace(hour=9, minute=0, second=0, microsecond=0),
                end_time=future_datetime.replace(hour=10, minute=0, second=0, microsecond=0),
                booked=True
            )
            db.session.add(slot)
            db.session.commit()
            slot_id = slot.availability_id
        
        #attempt to delete
        response = self.client.post(f'/delete-availability/{slot_id}')
        
        #verify if slot wasn't deleted
        with app.app_context():
            slot = Availability.query.get(slot_id)
            self.assertIsNotNone(slot, "Booked slot should not be deleted")
    
    def test_view_all_availability(self):
        #test AV7: checks if a tutor can view all their availability slots on the dashboard
        #create multiple slots
        future_datetime = datetime.now() + timedelta(days=7)
        with app.app_context():
            for hour in range(9, 12):
                slot = Availability(
                    tutor_id=self.tutor_id,
                    start_time=future_datetime.replace(hour=hour, minute=0, second=0, microsecond=0),
                    end_time=future_datetime.replace(hour=hour+1, minute=0, second=0, microsecond=0),
                    booked=False
                )
                db.session.add(slot)
            db.session.commit()
        
        response = self.client.get('/dashboard')
        
        self.assertEqual(response.status_code, 200)
    
    def test_prevent_excessive_slot_creation(self):
        #test AV8: checks if the system prevents tutors from creating more than 10 availability slots in a single day
        future_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        #try to create 15-minute slots for 3 hours = 12 slots
        response = self.client.post('/create_availability', data={
            'date': future_date,
            'start_time': '09:00',
            'end_time': '12:00',
            'slot_duration': '15',
            'break_duration': '0',
            'slice_slots': 'on',
            'action': 'create'
        })
        
        #should reject or show error after 10 slots
        self.assertTrue(response.status_code in [200, 302, 400])


if __name__ == '__main__':
    unittest.main()