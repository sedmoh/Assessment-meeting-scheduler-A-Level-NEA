from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    role = db.Column(db.String(50), nullable=False)  # student, tutor, staff_tutor, admin
    date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def get_id(self):
        return str(self.user_id)

class Availability(db.Model):
    __tablename__ = 'availability'
    availability_id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    booked = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(200))
    
    tutor = db.relationship('User', foreign_keys=[tutor_id], backref='availability_slots')

class Meeting(db.Model):
    __tablename__ = 'meeting'
    meeting_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    tutor_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    availability_id = db.Column(db.Integer, db.ForeignKey('availability.availability_id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # in minutes
    meeting_link = db.Column(db.String(200))
    adjustment_flag = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='confirmed')
    notes = db.Column(db.String(200))  # system notes (adjustments, urgent, etc.)
    public_notes = db.Column(db.Text)  # visible to both tutor and student
    private_notes = db.Column(db.Text)  # only visible to tutor
    
    student = db.relationship('User', foreign_keys=[student_id], backref='student_meetings')
    tutor = db.relationship('User', foreign_keys=[tutor_id], backref='tutor_meetings')
    availability = db.relationship('Availability', backref='meeting')
    
    # calculate end time
    @property
    def end_time(self):
        return self.start_time + timedelta(minutes=self.duration)

class Student(db.Model):
    __tablename__ = 'student'
    student_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    has_adjustment = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref='student_profile')

class Tutor(db.Model):
    __tablename__ = 'tutor'
    tutor_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    daily_limit = db.Column(db.Integer, default=4)
    weekly_limit = db.Column(db.Integer, default=10)
    
    user = db.relationship('User', backref='tutor_profile')

class StaffTutor(db.Model):
    __tablename__ = 'staff_tutor'
    staff_tutor_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    department = db.Column(db.String(100))
    can_override_limits = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref='staff_tutor_profile')

class Admin(db.Model):
    __tablename__ = 'admin'
    admin_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    access_level = db.Column(db.String(50), default='full')
    permissions = db.Column(db.String(500))
    
    user = db.relationship('User', backref='admin_profile')

class ReasonableAdjustment(db.Model):
    __tablename__ = 'reasonable_adjustment'
    adjustment_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.student_id'), nullable=False)
    notes = db.Column(db.String(500))
    
    student = db.relationship('Student', backref='adjustments')

class Notification(db.Model):
    __tablename__ = 'notification'
    notification_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meeting.meeting_id'), nullable=False)
    meeting_link = db.Column(db.String(200))
    notes = db.Column(db.String(200))
    
    meeting = db.relationship('Meeting', backref='notifications')
