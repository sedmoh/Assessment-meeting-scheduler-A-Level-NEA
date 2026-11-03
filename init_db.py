#database initialisation script
#populates empty tables with proper relationships
from app import app, db
from models import Admin, Availability, Meeting, StaffTutor, Student, Tutor, User
from werkzeug.security import generate_password_hash


def init_database():
    with app.app_context():
        print("Initialising database...")

        #create all tables first
        db.create_all()
        print("All tables created/verified")

        #get all existing users
        all_users = User.query.all()

        if not all_users:
            print("\nNo users found in database. Please register some users first!")
            return

        for user in all_users:
            print(f"\nProcessing user: {user.name} ({user.role})")

            #create tutor profile if user is tutor and doesn't have one
            if user.role == 'tutor':
                existing_tutor = Tutor.query.filter_by(user_id=user.user_id).first()
                if not existing_tutor:
                    tutor_profile = Tutor(
                        user_id=user.user_id,
                        daily_limit=4,
                        weekly_limit=10
                    )
                    db.session.add(tutor_profile)
                    print(f"Created Tutor profile for {user.name}")

            #create staff tutor profile if user is staff_tutor and doesn't have one
            elif user.role == 'staff_tutor':
                existing_staff = StaffTutor.query.filter_by(user_id=user.user_id).first()
                if not existing_staff:
                    staff_profile = StaffTutor(
                        user_id=user.user_id,
                        department="Computing",
                        can_override_limits=True
                    )
                    db.session.add(staff_profile)
                    print(f"Created Staff Tutor profile for {user.name}")

            #create admin profile if user is admin and doesn't have one
            elif user.role == 'admin':
                existing_admin = Admin.query.filter_by(user_id=user.user_id).first()
                if not existing_admin:
                    admin_profile = Admin(
                        user_id=user.user_id,
                        access_level='full',
                        permissions='all'
                    )
                    db.session.add(admin_profile)
                    print(f"Created Admin profile for {user.name}")

            #create student profile if user is student and doesn't have one
            elif user.role == 'student':
                existing_student = Student.query.filter_by(user_id=user.user_id).first()
                if not existing_student:
                    student_profile = Student(
                        user_id=user.user_id,
                        has_adjustment=False
                    )
                    db.session.add(student_profile)
                    print(f"Created Student profile for {user.name}")

        #commit all changes
        db.session.commit()
        print("\nDatabase initialisation complete!")

        #print summary
        print("\n=== Database Summary ===")
        print(f"Total Users: {User.query.count()}")
        print(f"Students: {Student.query.count()}")
        print(f"Tutors: {Tutor.query.count()}")
        print(f"Staff Tutors: {StaffTutor.query.count()}")
        print(f"Admins: {Admin.query.count()}")
        print(f"Meetings: {Meeting.query.count()}")
        print(f"Availability Slots: {Availability.query.count()}")

if __name__ == "__main__":
    init_database()
