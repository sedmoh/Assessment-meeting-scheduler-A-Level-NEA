import random
from datetime import datetime, timedelta

from app import app, db
from models import (
    Admin,
    Availability,
    Meeting,
    MeetingStatus,
    StaffTutor,
    Student,
    Tutor,
    User,
)
from werkzeug.security import generate_password_hash


def clear_database():
    #clear existing data from database
    print("Clearing existing database...")
    with app.app_context():
        #delete in correct order to respect foreign keys
        Meeting.query.delete()
        Availability.query.delete()
        Student.query.delete()
        Tutor.query.delete()
        StaffTutor.query.delete()
        Admin.query.delete()
        User.query.delete()
        db.session.commit()
    print("Database cleared")

def create_students(count=50):
    #create student test accounts
    print(f"\nCreating {count} student accounts...")
    students = []

    with app.app_context():
        for i in range(count):
            #create base user
            user = User(
                name=f"Load Test Student {i}",
                email=f"loadtest_student{i}@test.com",
                password_hash=generate_password_hash("test123"),
                role="student"
            )
            db.session.add(user)
            db.session.flush()  #get user_id

            #create student profile
            #20% of students have reasonable adjustments
            has_adjustment = (i % 5 == 0)
            student_profile = Student(
                user_id=user.user_id,
                has_adjustment=has_adjustment
            )
            db.session.add(student_profile)
            students.append(user.user_id)

            #commit every 10 students
            if (i + 1) % 10 == 0:
                db.session.commit()
                print(f"Created {i + 1}/{count} students...")

        db.session.commit()

    print(f"Created {count} students ({count//5} with adjustments)")
    return students

def create_tutors(count=25):
    #create tutor test accounts
    print(f"\nCreating {count} tutor accounts...")
    tutors = []

    with app.app_context():
        for i in range(count):
            #create base user
            user = User(
                name=f"Load Test Tutor {i}",
                email=f"loadtest_tutor{i}@test.com",
                password_hash=generate_password_hash("test123"),
                role="tutor"
            )
            db.session.add(user)
            db.session.flush()

            #create tutor profile
            tutor_profile = Tutor(
                user_id=user.user_id,
                daily_limit=4,
                weekly_limit=10
            )
            db.session.add(tutor_profile)
            tutors.append(user.user_id)

            if (i + 1) % 10 == 0:
                db.session.commit()
                print(f"  Created {i + 1}/{count} tutors...")

        db.session.commit()

    print(f"Created {count} tutors")
    return tutors

def create_staff_tutors(count=15):
    #create staff tutor test accounts
    print(f"\nCreating {count} staff tutor accounts...")
    staff_tutors = []

    with app.app_context():
        for i in range(count):
            #create base user
            user = User(
                name=f"Load Test Staff Tutor {i}",
                email=f"loadtest_stafftutor{i}@test.com",
                password_hash=generate_password_hash("test123"),
                role="staff_tutor"
            )
            db.session.add(user)
            db.session.flush()

            #create staff tutor profile
            staff_profile = StaffTutor(
                user_id=user.user_id,
                department="Computing",
                can_override_limits=True
            )
            db.session.add(staff_profile)
            staff_tutors.append(user.user_id)

        db.session.commit()

    print(f"Created {count} staff tutors")
    return staff_tutors

def create_admins(count=10):
    #create admin test accounts
    print(f"\nCreating {count} admin accounts...")
    admins = []

    with app.app_context():
        for i in range(count):
            #create base user
            user = User(
                name=f"Load Test Admin {i}",
                email=f"loadtest_admin{i}@test.com",
                password_hash=generate_password_hash("test123"),
                role="admin"
            )
            db.session.add(user)
            db.session.flush()

            #create admin profile
            admin_profile = Admin(
                user_id=user.user_id,
                access_level="full",
                permissions="all"
            )
            db.session.add(admin_profile)
            admins.append(user.user_id)

        db.session.commit()

    print(f"Created {count} admins")
    return admins

def create_availability_slots(tutor_ids, staff_tutor_ids):
    #create availability slots for tutors and staff tutors
    print(f"\nCreating availability slots...")

    all_tutor_ids = tutor_ids + staff_tutor_ids
    total_slots = 0

    with app.app_context():
        base_date = datetime.now() + timedelta(days=7)

        for tutor_id in all_tutor_ids:
            #create 2 weeks of availability (14 days)
            for day in range(14):
                slot_date = base_date + timedelta(days=day)

                #create 4-6 slots per day
                num_slots = random.randint(4, 6)

                for slot_num in range(num_slots):
                    start_hour = 9 + slot_num  # 9am to 2pm start times
                    if start_hour >= 17:  # Don't go past 5pm
                        break

                    start_time = slot_date.replace(hour=start_hour, minute=0, second=0)

                    #random duration: 45min or 60min
                    duration_minutes = random.choice([45, 60])
                    end_time = start_time + timedelta(minutes=duration_minutes)

                    slot = Availability(
                        tutor_id=tutor_id,
                        start_time=start_time,
                        end_time=end_time,
                        booked=False,
                        notes=f"Load test slot {slot_num + 1}"
                    )
                    db.session.add(slot)
                    total_slots += 1

            #commit every 10 tutors
            if (all_tutor_ids.index(tutor_id) + 1) % 10 == 0:
                db.session.commit()
                print(f"Created slots for {all_tutor_ids.index(tutor_id) + 1}/{len(all_tutor_ids)} tutors...")

        db.session.commit()

    print(f"Created {total_slots} availability slots")
    return total_slots

def create_sample_meetings(student_ids, tutor_ids):
    #create some pre-booked meetings to simulate real usage and test booking functionality
    print(f"\nCreating sample meetings...")

    with app.app_context():
        #get available slots
        available_slots = Availability.query.filter_by(booked=False).limit(50).all()

        meetings_created = 0

        for slot in available_slots[:30]:  # Book 30 meetings
            #random student
            student_id = random.choice(student_ids)

            #get student profile to check for adjustments
            student = Student.query.filter_by(user_id=student_id).first()
            has_adjustment = student.has_adjustment if student else False

            #calculate duration
            base_duration = int((slot.end_time - slot.start_time).total_seconds() / 60)
            if has_adjustment:
                duration = int(base_duration * 1.25)  #+25% for adjustments
            else:
                duration = base_duration

            #create meeting
            meeting = Meeting(
                student_id=student_id,
                tutor_id=slot.tutor_id,
                availability_id=slot.availability_id,
                start_time=slot.start_time,
                duration=duration,
                meeting_link=f"https://teams.microsoft.com/test/{meetings_created}",
                adjustment_flag=has_adjustment,
                status=MeetingStatus.CONFIRMED,
                notes="Load test meeting"
            )

            #mark slot as booked
            slot.booked = True

            db.session.add(meeting)
            meetings_created += 1

        db.session.commit()

    print(f"Created {meetings_created} sample meetings")
    return meetings_created

def print_summary():
    #print summary of created data and test credentials for load testing
    print("\n" + "="*60)
    print("DATABASE POPULATION SUMMARY")
    print("="*60)

    with app.app_context():
        total_users = User.query.count()
        students = Student.query.count()
        tutors = Tutor.query.count()
        staff_tutors = StaffTutor.query.count()
        admins = Admin.query.count()
        availability = Availability.query.count()
        available_slots = Availability.query.filter_by(booked=False).count()
        booked_slots = Availability.query.filter_by(booked=True).count()
        meetings = Meeting.query.count()
        students_with_adjustments = Student.query.filter_by(has_adjustment=True).count()

        print(f"Total Users: {total_users}")
        print(f"  - Students: {students} ({students_with_adjustments} with adjustments)")
        print(f"  - Tutors: {tutors}")
        print(f"  - Staff Tutors: {staff_tutors}")
        print(f"  - Admins: {admins}")
        print(f"\nAvailability Slots: {availability}")
        print(f"  - Available: {available_slots}")
        print(f"  - Booked: {booked_slots}")
        print(f"\nMeetings: {meetings}")
        print("="*60)
        print("\nTEST CREDENTIALS:")
        print("  Email: loadtest_student0@test.com (or student1, student2, etc.)")
        print("  Email: loadtest_tutor0@test.com (or tutor1, tutor2, etc.)")
        print("  Email: loadtest_stafftutor0@test.com")
        print("  Email: loadtest_admin0@test.com")
        print("  Password: test123 (for all accounts)")
        print("="*60)
        print("\nREADY FOR LOAD TESTING!")
        print("Run: locust -f locustfile.py --host=http://localhost:5000")
        print("="*60 + "\n")

def main():
    #main function to execute database population
    print("\n" + "="*60)
    print("DATABASE POPULATION SCRIPT FOR LOAD TESTING")
    print("="*60)
    print("\nThis script will create:")
    print("  - 50 Students (10 with reasonable adjustments)")
    print("  - 25 Tutors")
    print("  - 15 Staff Tutors")
    print("  - 10 Admins")
    print("  - ~2000+ Availability slots")
    print("  - 30 Pre-booked meetings")
    print("\nTotal: 100 users")
    print("="*60)

    #confirm before proceeding
    response = input("\nProceed? This will clear existing data! (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return

    #execute population
    clear_database()

    student_ids = create_students(50)
    tutor_ids = create_tutors(25)
    staff_tutor_ids = create_staff_tutors(15)
    admin_ids = create_admins(10)

    total_slots = create_availability_slots(tutor_ids, staff_tutor_ids)
    meetings_created = create_sample_meetings(student_ids, tutor_ids)

    print_summary()

if __name__ == "__main__":
    main()
