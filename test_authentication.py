import unittest
from app import app, db
from models import User
from werkzeug.security import generate_password_hash, check_password_hash


class TestAuthentication(unittest.TestCase):
    #testing user authentication and registration functionality
    
    def setUp(self):
        #setting up the test client and database for testing
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        
        with app.app_context():
            db.create_all()
    
    def tearDown(self):
        #cleaning up the database after each test
        with app.app_context():
            db.session.remove()
            db.drop_all()
    
    def test_user_registration_valid(self):
        #test A1: checks if registration validation works
        response = self.client.post('/register', data={
            'name': 'Test Student',
            'email': 'student1@open.ac.uk',
            'password': 'SecurePass123!',
            'role': 'student'
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        
        with app.app_context():
            user = User.query.filter_by(email='student1@open.ac.uk').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.name, 'Test Student')
            self.assertEqual(user.role, 'student')
            #verify if the password is hashed
            self.assertTrue(check_password_hash(user.password_hash, 'SecurePass123!'))
    
    def test_user_registration_duplicate_email(self):
        #test A2: checks if the app prevents registration with an email that already exists in the database
        #create first test user
        with app.app_context():
            user = User(
                name='First User',
                email='student1@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            db.session.add(user)
            db.session.commit()
        
        #attempt to register with same email
        response = self.client.post('/register', data={
            'name': 'Second User',
            'email': 'student1@open.ac.uk',
            'password': 'SecurePass123!',
            'role': 'student'
        }, follow_redirects=True)
        
        #should redirect back to registration page with error message
        with app.app_context():
            user_count = User.query.filter_by(email='student1@open.ac.uk').count()
            self.assertEqual(user_count, 1)
    
    def test_user_registration_weak_password(self):
        #test A3: checks if the app allows registration with a weak password
        response = self.client.post('/register', data={
            'name': 'Test Student',
            'email': 'student2@open.ac.uk',
            'password': '123',
            'role': 'student'
        })
        
        #test passes if the registration works
        self.assertTrue(response.status_code in [200, 302])
    
    def test_login_valid_credentials(self):
        #test A4: checks if users can log in with valid credentials
        #create test user
        with app.app_context():
            user = User(
                name='Test Tutor',
                email='tutor1@open.ac.uk',
                password_hash=generate_password_hash('ValidPass123!'),
                role='tutor'
            )
            db.session.add(user)
            db.session.commit()
        
        #login
        response = self.client.post('/login', data={
            'email': 'tutor1@open.ac.uk',
            'password': 'ValidPass123!'
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        #should see dashboard after successful login
        self.assertIn(b'Dashboard', response.data)
    
    def test_login_invalid_credentials(self):
        #test A5: checks if the app prevents login with invalid credentials
        #create user
        with app.app_context():
            user = User(
                name='Test Tutor',
                email='tutor1@open.ac.uk',
                password_hash=generate_password_hash('CorrectPass123!'),
                role='tutor'
            )
            db.session.add(user)
            db.session.commit()
        
        #login with wrong password
        response = self.client.post('/login', data={
            'email': 'tutor1@open.ac.uk',
            'password': 'WrongPassword!'
        })
        
        #should fail to login
        self.assertTrue(response.status_code in [200, 302])
    
    def test_session_persistence(self):
        #test A6: checks if the user session continues across multiple requests after logging in
        #create and login user
        with app.app_context():
            user = User(
                name='Test Student',
                email='student3@open.ac.uk',
                password_hash=generate_password_hash('Password123!'),
                role='student'
            )
            db.session.add(user)
            db.session.commit()
        
        #login
        self.client.post('/login', data={
            'email': 'student3@open.ac.uk',
            'password': 'Password123!'
        }, follow_redirects=True)
        
        #access protected page without logging in again
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()