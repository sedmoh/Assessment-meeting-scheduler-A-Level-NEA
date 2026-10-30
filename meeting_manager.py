from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from models import db, Meeting, Availability
from algorithms import validate_booking, PriorityQueue


class MeetingValidator:
    #validates meeting bookings

    @staticmethod
    def validate_time_slot(start_time, end_time):
        #check time is valid
        if start_time >= end_time:
            return False, "End time must be after start time"
        
        if start_time < datetime.now():
            return False, "Cannot book meetings in the past"
        
        return True, None
    
    @staticmethod
    def validate_availability(slot):
        #check availability slot is valid
        if slot.booked:
            return False, "This slot is already booked"
        
        if slot.start_time < datetime.now():
            return False, "This slot is in the past"
        
        return True, None
    
    @staticmethod
    def validate_tutor_availability(tutor_id, start_time, end_time, exclude_meeting_id=None):
        #check tutor availability for the time slot
        
        return validate_booking(tutor_id, start_time, end_time, exclude_meeting_id)


class MeetingNotesManager:
    #manages meeting notes (public and private)
    def __init__(self, meeting):
        #initialise with meeting
        self._meeting = meeting
    
    @property
    def meeting(self):
        #protected meeting access
        return self._meeting
    
    def get_public_notes(self):
        #get public notes
        return self._meeting.public_notes or ""
    
    def get_private_notes(self):
        #get private notes (tutor only)
        return self._meeting.private_notes or ""
    
    def set_public_notes(self, notes):
        #set public notes
        self._meeting.public_notes = notes.strip() if notes else None
    
    def set_private_notes(self, notes):
        #set private notes (tutor only)
        self._meeting.private_notes = notes.strip() if notes else None
    
    def has_public_notes(self):
        #check if meeting has public notes
        return bool(self._meeting.public_notes)
    
    def has_private_notes(self):
        #check if meeting has private notes
        return bool(self._meeting.private_notes)
    
    def update_notes(self, public_notes=None, private_notes=None):
        #update both note types
        if public_notes is not None:
            self.set_public_notes(public_notes)
        
        if private_notes is not None:
            self.set_private_notes(private_notes)
        
        try:
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error updating notes: {str(e)}")
            return False


class MeetingBooking(ABC):
    #abstract base class for different types of meeting bookings
    def __init__(self, student, slot):
        #initialise booking
        self._student = student
        self._slot = slot
        self._validator = MeetingValidator()
    
    @property
    def student(self):
        return self._student
    
    @property
    def slot(self):
        return self._slot
    
    def calculate_duration(self):
        #calculate meeting duration
        return int((self.slot.end_time - self.slot.start_time).total_seconds() / 60)
    
    @abstractmethod
    def get_booking_type(self):
        #get type of booking
        pass

    @abstractmethod
    def get_priority(self):
        #get booking priority
        pass
    
    def validate(self):
        #validate booking

        #validate slot
        is_valid, error = self._validator.validate_availability(self.slot)
        if not is_valid:
            return False, error
        
        #validate tutor availability
        duration = self.calculate_duration()
        end_time = self.slot.start_time + timedelta(minutes=duration)
        
        is_valid, error = self._validator.validate_tutor_availability(
            self.slot.tutor_id,
            self.slot.start_time,
            end_time
        )
        
        return is_valid, error
    
    def create_meeting(self):
        #create meeting record

        #validate booking
        is_valid, error = self.validate()
        if not is_valid:
            return None, error
        
        #calculate duration
        duration = self.calculate_duration()
        
        #create meeting
        meeting = Meeting(
            student_id=self.student.user_id,
            tutor_id=self.slot.tutor_id,
            availability_id=self.slot.availability_id,
            start_time=self.slot.start_time,
            duration=duration,
            adjustment_flag=False,
            status="Confirmed",
            notes=self.get_booking_notes()
        )
        
        #mark slot as booked
        self.slot.booked = True
        
        #save to database
        try:
            db.session.add(meeting)
            db.session.commit()
            return meeting, None
        except Exception as e:
            db.session.rollback()
            return None, str(e)
    
    @abstractmethod
    def get_booking_notes(self):
        #get booking notes (system notes)
        pass


class RegularBooking(MeetingBooking):
    #regular meeting booking -> inherits from MeetingBooking
    
    def get_booking_type(self):
        return "regular"
    
    def get_priority(self):
        return 3  #normal priority
    
    def get_booking_notes(self):
        return "Regular booking"


class UrgentBooking(MeetingBooking):
    #urgent meeting booking -> inherits from MeetingBooking
    
    def get_booking_type(self):
        return "urgent"
    
    def get_priority(self):
        return 1  #high priority
    
    def get_booking_notes(self):
        time_until = (self.slot.start_time - datetime.now()).total_seconds() / 3600
        return f"URGENT BOOKING: Meeting within {int(time_until)} hours"


class AdjustedBooking(MeetingBooking):
    #booking with reasonable adjustments
    
    def __init__(self, student, slot, adjustment_percentage=0.25):
        super().__init__(student, slot)
        self._adjustment_percentage = adjustment_percentage
    
    def calculate_duration(self):
        #add adjustment time

        base_duration = super().calculate_duration()
        extra_time = int(base_duration * self._adjustment_percentage)
        return base_duration + extra_time
    
    def get_booking_type(self):
        return "adjusted"
    
    def get_priority(self):
        return 2  #higher priority due to adjustment
    
    def get_booking_notes(self):
        base_duration = int((self.slot.end_time - self.slot.start_time).total_seconds() / 60)
        extra_time = int(base_duration * self._adjustment_percentage)
        return f"REASONABLE ADJUSTMENT: +{extra_time} minutes (+{int(self._adjustment_percentage * 100)}%)"
    
    def create_meeting(self):
        #override to set adjustment flag
        meeting, error = super().create_meeting()
        if meeting:
            meeting.adjustment_flag = True
            db.session.commit()
        return meeting, error


class MeetingScheduler:
    def __init__(self):
        self._priority_queue = PriorityQueue()
    
    def schedule_meeting(self, student, slot, is_urgent=False, has_adjustment=False):
        #schedule a meeting using appropriate booking type

        #choose appropriate booking type
        if has_adjustment:
            booking = AdjustedBooking(student, slot)
        elif is_urgent:
            booking = UrgentBooking(student, slot)
        else:
            booking = RegularBooking(student, slot)
        
        #add to priority queue
        self._priority_queue.push(booking, booking.get_priority())
        
        #create meeting
        meeting, error = booking.create_meeting()
        
        return meeting, error
    
    def get_next_priority_booking(self):
        #get next booking from priority queue
        return self._priority_queue.pop()
    
    def has_pending_bookings(self):
        #check if there are pending bookings
        return not self._priority_queue.is_empty()


class MeetingRescheduler:
    #class responsible for rescheduling meetings
    def __init__(self, meeting):
        #initialise rescheduler

        self._meeting = meeting
        self._validator = MeetingValidator()
        self._old_slot = None
    
    def reschedule(self, new_slot):
        #reschedule meeting to new slot

        #validate new slot
        is_valid, error = self._validator.validate_availability(new_slot)
        if not is_valid:
            return False, error
        
        #validate tutor availability (excluding current meeting)
        is_valid, error = self._validator.validate_tutor_availability(
            new_slot.tutor_id,
            new_slot.start_time,
            new_slot.end_time,
            exclude_meeting_id=self._meeting.meeting_id
        )
        
        if not is_valid:
            return False, error
        
        #store old slot
        self._old_slot = Availability.query.get(self._meeting.availability_id)
        
        #free old slot
        if self._old_slot:
            self._old_slot.booked = False
        
        #update meeting
        self._meeting.availability_id = new_slot.availability_id
        self._meeting.tutor_id = new_slot.tutor_id
        self._meeting.start_time = new_slot.start_time
        
        duration = int((new_slot.end_time - new_slot.start_time).total_seconds() / 60)
        self._meeting.duration = duration
        
        #book new slot
        new_slot.booked = True
        
        try:
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            return False, str(e)
    
    def get_old_time(self):
        #get old meeting time
        return self._old_slot.start_time if self._old_slot else None


#convenience function for Flask routes
def create_meeting_booking(student, slot, is_urgent=False, has_adjustment=False):
    #factory function to create appropriate booking

    if has_adjustment:
        return AdjustedBooking(student, slot)
    elif is_urgent:
        return UrgentBooking(student, slot)
    else:
        return RegularBooking(student, slot)