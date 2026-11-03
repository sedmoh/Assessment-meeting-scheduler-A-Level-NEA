from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from models import Availability, Meeting, MeetingStatus, User, db
from models import Student as StudentModel
from sorting import merge_sort_meetings


class UserRole(ABC):
    #abstract base class for all user roles

    def __init__(self, user):
        #initialise user role
        self._user = user
        self._permissions = []

    @property
    def user(self):
        #get user model
        return self._user

    @property
    def name(self):
        #get user name
        return self._user.name

    @property
    def email(self):
        #get user email
        return self._user.email

    @property
    def user_id(self):
        #get user ID
        return self._user.user_id

    @abstractmethod
    def get_dashboard_data(self):
        pass

    @abstractmethod
    def can_manage_meetings(self):
        #check if role can manage meetings
        pass

    @abstractmethod
    def can_create_availability(self):
        #check if role can create availability slots
        pass

    def get_permissions(self):
        #get list of permissions for this role
        return self._permissions

    def has_permission(self, permission):
        #check if role has specific permission
        return permission in self._permissions

    def __str__(self):
        #string representation
        return f"{self.__class__.__name__}({self.name})"

    def __repr__(self):
        #detailed representation
        return f"{self.__class__.__name__}(user_id={self.user_id}, name='{self.name}')"


class StudentRole(UserRole):
    #student role class -> inherits from UserRole

    def __init__(self, user):
        super().__init__(user)
        self._permissions = ['view_availability', 'book_meeting', 'cancel_meeting', 'view_notes']
        self._student_profile = StudentModel.query.filter_by(user_id=user.user_id).first()

    def get_dashboard_data(self):
        #separate meetings into past and upcoming
        now = datetime.now()

        all_meetings = Meeting.query.filter_by(student_id=self.user_id).all()
        all_meetings = merge_sort_meetings(all_meetings, key="start_time")

        #separate into past and upcoming
        upcoming_meetings = []
        past_meetings = []

        for meeting in all_meetings:
            meeting_end = meeting.start_time + timedelta(minutes=meeting.duration)
            if meeting_end < now:
                #meeting has ended
                if meeting.status == MeetingStatus.CONFIRMED:
                    meeting.status = MeetingStatus.COMPLETED
                    db.session.commit()
                past_meetings.append(meeting)
            else:
                #meeting is in the future or currently happening
                upcoming_meetings.append(meeting)

        return {
            'template': 'student_dashboard.html',
            'upcoming_meetings': upcoming_meetings,
            'past_meetings': past_meetings,
            'has_adjustment': self.has_reasonable_adjustment()
        }

    def can_manage_meetings(self):
        #students can manage their own meetings
        return True

    def can_create_availability(self):
        #students cannot create availability
        return False

    def has_reasonable_adjustment(self):
        #check if student has reasonable adjustments enabled
        if not self._student_profile:
            return False
        return self._student_profile.has_adjustment

    def get_meetings(self):
        #get all student meetings
        meetings = Meeting.query.filter_by(student_id=self.user_id).all()
        return merge_sort_meetings(meetings, key="start_time")

    def book_meeting(self, slot, adjustment_flag=False):
        #book a meeting slot

        duration = int((slot.end_time - slot.start_time).total_seconds() / 60)

        #apply adjustment if needed
        if self.has_reasonable_adjustment():
            extra_time = int(duration * 0.25)
            duration += extra_time
            adjustment_flag = True

        meeting = Meeting(
            student_id=self.user_id,
            tutor_id=slot.tutor_id,
            availability_id=slot.availability_id,
            start_time=slot.start_time,
            duration=duration,
            adjustment_flag=adjustment_flag,
            status=MeetingStatus.CONFIRMED
        )

        return meeting


class TutorRole(UserRole):
    #tutor role class -> inherits from UserRole

    def __init__(self, user):
        super().__init__(user)
        self._permissions = [
            'view_availability',
            'create_availability',
            'manage_meetings',
            'cancel_meeting',
            'manage_notes',
            'view_private_notes'
        ]

    def get_dashboard_data(self):
        #separate meetings into past and upcoming
        now = datetime.now()

        availability_slots = Availability.query.filter_by(tutor_id=self.user_id).all()
        availability_slots = merge_sort_meetings(availability_slots, key="start_time")

        all_meetings = Meeting.query.filter_by(tutor_id=self.user_id).all()
        all_meetings = merge_sort_meetings(all_meetings, key="start_time")

        #separate into past and upcoming
        upcoming_meetings = []
        past_meetings = []

        for meeting in all_meetings:
            meeting_end = meeting.start_time + timedelta(minutes=meeting.duration)
            if meeting_end < now:
                #meeting has ended
                if meeting.status == MeetingStatus.CONFIRMED:
                    meeting.status = MeetingStatus.COMPLETED
                past_meetings.append(meeting)
            else:
                #meeting is in the future
                upcoming_meetings.append(meeting)

        #commit any status updates
        db.session.commit()

        return {
            'template': 'tutor_dashboard.html',
            'availability_slots': availability_slots,
            'upcoming_meetings': upcoming_meetings,
            'past_meetings': past_meetings,
            'timedelta': timedelta
        }

    def can_manage_meetings(self):
        #tutors can manage meetings
        return True

    def can_create_availability(self):
        #tutors can create availability
        return True

    def get_availability_slots(self):
        #get all tutor availability slots
        slots = Availability.query.filter_by(tutor_id=self.user_id).all()
        return merge_sort_meetings(slots, key="start_time")

    def get_meetings(self):
        #get all tutor meetings
        meetings = Meeting.query.filter_by(tutor_id=self.user_id).all()
        return merge_sort_meetings(meetings, key="start_time")

    def create_availability_slot(self, start_time, end_time, notes=""):
        #create an availability slot
        slot = Availability(
            tutor_id=self.user_id,
            start_time=start_time,
            end_time=end_time,
            booked=False,
            notes=notes
        )
        return slot

    def can_manage_notes(self, meeting):
        #check if tutor can manage notes for a meeting
        return meeting.tutor_id == self.user_id


class StaffTutorRole(TutorRole):
    #staff tutor role -> inherits from TutorRole (demonstrates inheritance hierarchy)
    #has all tutor permissions plus additional admin-like permissions

    def __init__(self, user):
        super().__init__(user)
        #extend permissions
        self._permissions.extend([
            'view_reports',
            'manage_other_tutors',
            'book_on_behalf',
            'override_limits'
        ])

    def get_dashboard_data(self):
        #get base tutor data
        data = super().get_dashboard_data()

        #override template
        data['template'] = 'staff_tutor_dashboard.html'

        #add additional data
        data['can_manage_others'] = True

        return data

    def can_override_limits(self):
        #staff tutors can override booking limits
        return True

    def can_manage_other_tutors(self):
        #staff tutors can manage other tutors
        return True


class AdminRole(UserRole):
    #admin role class -> inherits from UserRole

    def __init__(self, user):
        super().__init__(user)
        self._permissions = [
            'view_all_data',
            'manage_users',
            'view_reports',
            'manage_adjustments',
            'access_all_features',
            'create_users',
            'delete_users',
            'override_restrictions'
        ]

    def get_dashboard_data(self):
        #redirect to dedicated admin dashboard
        return {
            'template': 'admin_dashboard.html',
            'redirect_to': 'admin_dashboard'
        }

    def can_manage_meetings(self):
        #admins can manage all meetings
        return True

    def can_create_availability(self):
        #admins cannot directly create availability
        return False

    def can_access_reports(self):
        #admins can access all reports
        return True

    def can_manage_all_users(self):
        #admins can manage all user accounts
        return True


class UserRoleFactory:
    #factory pattern for creating user roles

    @staticmethod
    def create_role(user):
        #create appropriate role object based on user type
        role_map = {
            'student': StudentRole,
            'tutor': TutorRole,
            'staff_tutor': StaffTutorRole,
            'admin': AdminRole
        }

        role_class = role_map.get(user.role)

        if not role_class:
            raise ValueError(f"Invalid role: {user.role}")

        return role_class(user)

    @staticmethod
    def get_available_roles():
        #get list of available roles
        return ['student', 'tutor', 'staff_tutor', 'admin']


#helper function for Flask routes
def get_user_role(user):
    #getter function to get user role object
    return UserRoleFactory.create_role(user)
