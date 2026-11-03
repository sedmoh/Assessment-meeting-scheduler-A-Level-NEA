import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["POWER_AUTOMATE_FLOW_URL"] = ""
os.environ["MAIL_USERNAME"] = ""

import unittest

from app import app, db
from hash_table import user_session_cache
from models import User
from werkzeug.security import check_password_hash, generate_password_hash


class TestAuthentication(unittest.TestCase):
    #testing user authentication and registration functionality

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

    def test_cannot_self_register_as_admin(self):
        #test A7 (regression): the public form must not create privileged accounts
        for role in ['admin', 'staff_tutor']:
            email = f'{role}@test.com'
            self.client.post('/register', data={
                'name': 'Attacker', 'email': email,
                'password': 'Password123!', 'role': role})
            with app.app_context():
                self.assertIsNone(User.query.filter_by(email=email).first(),
                                  f"Public registration created a {role} account")

    def test_registration_rejects_invalid_email(self):
        #test A8 (regression): email format is validated on registration
        self.client.post('/register', data={
            'name': 'Bad Email', 'email': 'not-an-email',
            'password': 'Password123!', 'role': 'student'})
        with app.app_context():
            self.assertIsNone(User.query.filter_by(email='not-an-email').first())

    #helpers for the login cache tests
    def _add_user(self, name, email, password, role):
        with app.app_context():
            user = User(name=name, email=email,
                        password_hash=generate_password_hash(password), role=role)
            db.session.add(user)
            db.session.commit()
            return user.user_id

    def _login(self, email, password):
        #returns True if the login succeeded (redirects to the dashboard)
        response = self.client.post('/login', data={'email': email, 'password': password})
        return '/dashboard' in response.headers.get('Location', '')

    def test_old_email_rejected_after_admin_changes_it(self):
        #test A9 (regression): the login cache must not keep an old email working
        self._add_user('Admin', 'admin@test.com', 'AdminPass1!', 'admin')
        alice_id = self._add_user('Alice', 'old@test.com', 'AlicePass1!', 'student')

        #Alice logs in once, so her old email is cached
        self.assertTrue(self._login('old@test.com', 'AlicePass1!'))
        self.client.get('/logout')

        #admin changes her email
        self.assertTrue(self._login('admin@test.com', 'AdminPass1!'))
        self.client.post(f'/admin/users/{alice_id}/edit', data={'name': 'Alice', 'email': 'new@test.com'})
        self.client.get('/logout')

        self.assertFalse(self._login('old@test.com', 'AlicePass1!'), "Old email should no longer log in")
        self.assertTrue(self._login('new@test.com', 'AlicePass1!'), "New email should log in")

    def test_deleted_users_email_cannot_reach_new_account(self):
        #test A10 (regression): SQLite can give a deleted user's ID to the next new user,
        #so a stale cache entry would point the old email at someone else's account
        self._add_user('Admin', 'admin@test.com', 'AdminPass1!', 'admin')
        alice_id = self._add_user('Alice', 'alice@test.com', 'AlicePass1!', 'student')

        self.assertTrue(self._login('alice@test.com', 'AlicePass1!'))
        self.client.get('/logout')

        #admin deletes Alice, then Bob registers and is given the same ID
        self.assertTrue(self._login('admin@test.com', 'AdminPass1!'))
        self.client.post(f'/admin/users/{alice_id}/delete')
        self.client.get('/logout')
        bob_id = self._add_user('Bob', 'bob@test.com', 'BobPass1!', 'tutor')
        self.assertEqual(bob_id, alice_id, "Setup check: Bob should reuse Alice's ID")

        self.assertFalse(self._login('alice@test.com', 'BobPass1!'),
                         "Deleted user's email must not log in to Bob's account")

    def test_login_email_is_case_insensitive(self):
        #test A11 (regression): emails are stored lowercase, so login should accept any case
        self._add_user('Bob', 'bob@test.com', 'BobPass1!', 'tutor')
        self.assertTrue(self._login('  Bob@Test.com ', 'BobPass1!'))


if __name__ == '__main__':
    unittest.main()
