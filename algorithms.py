from models import Meeting, Availability, Student, db
from datetime import datetime, timedelta
import heapq
from sqlalchemy import and_


def check_time_overlap(self, start1, end1, start2, end2):
    #checks if two time intervals overlap using mathematical interval logic
    #two intervals overlap if the max of their start times is less than the min of their end times
    return max(start1, start2) < min(end1, end2)

def check_tutor_conflicts(tutor_id, start_time, end_time, exclude_meeting_id=None):
    # check if tutor has any conflicting meetings
    # get scheduled meetings
    query = Meeting.query.filter_by(tutor_id=tutor_id, status="Confirmed")

    # exclude current meeting if rescheduling
    if exclude_meeting_id:
        query = query.filter(Meeting.meeting_id != exclude_meeting_id)
    existing_meetings = query.all()

    for meeting in existing_meetings:
        if check_time_overlap(
            start_time, end_time, meeting.start_time, meeting.end_time
        ):
            return (
                True,
                f"Conflict with existing meeting at {meeting.start_time.strftime('%H:%M')}",
            )
    return False, None


def check_daily_limit(tutor_id, date):
    # check if tutor has reached daily limit of 4 meetings
    start_of_day = datetime.combine(date, datetime.min.time())
    end_of_day = datetime.combine(date, datetime.max.time())

    meeting_count = Meeting.query.filter(
        Meeting.tutor_id == tutor_id,
        Meeting.status == "Confirmed",
        Meeting.start_time >= start_of_day,
        Meeting.start_time <= end_of_day,
    ).count()

    if meeting_count >= 4:
        return True, "Tutor has reached daily limit of 4 meetings"
    return False, None


def check_weekly_limit(tutor_id, date):
    # check if tutor has reached weekly limit of 10 meetings

    # get start of week (Monday)
    days_since_monday = date.weekday()
    week_start = date - timedelta(days=days_since_monday)
    week_start = datetime.combine(week_start, datetime.min.time())

    # get end of week (Sunday)
    week_end = week_start + timedelta(days=7)

    meeting_count = Meeting.query.filter(
        Meeting.tutor_id == tutor_id,
        Meeting.status == "Confirmed",
        Meeting.start_time >= week_start,
        Meeting.start_time < week_end,
    ).count()

    if meeting_count >= 10:
        return True, "Tutor has reached weekly limit of 10 meetings"
    return False, None


class PriorityQueue:
    # priority queue for urgent meeting scheduling
    def __init__(self):
        self.heap = []
        self.counter = 0

    def push(self, meeting, priority):
        # add meeting to queue
        # use counter to break ties and maintain insertion order
        heapq.heappush(self.heap, (priority, self.counter, meeting))
        self.counter += 1

    def pop(self):
        # remove and return highest priority meeting
        if self.heap:
            return heapq.heappop(self.heap)[2]
        return None

    def peek(self):
        # return highest priority meeting without removing
        if self.heap:
            return self.heap[0][2]
        return None

    def is_empty(self):
        return len(self.heap) == 0


def get_priority(meeting, student):
    # calculate priority for meeting booking
    priority = 3  # default: normal

    # check if student has reasonable adjustments
    if student.student_profile and student.student_profile.has_adjustment:
        priority = 2  # adjustment needed

    # check if meeting is urgent (within 24 hours)
    time_until = meeting.start_time - datetime.now()
    if time_until.total_seconds() < 86400:  # 24 hours
        priority = 1  # urgent
    return priority


def validate_booking(tutor_id, start_time, end_time, ignored_meeting_id=None):
    # check overlap conflicts
    conflicts = Meeting.query.filter(
        Meeting.tutor_id == tutor_id,
        Meeting.status == "confirmed",
        Meeting.start_time < end_time,
    ).all()

    for meeting in conflicts:
        if meeting.end_time > start_time:
            if ignored_meeting_id and meeting.meeting_id == ignored_meeting_id:
                continue
            return False, "Time conflict with existing meeting"

    # check daily limit
    daily_exceeded, daily_msg = check_daily_limit(tutor_id, start_time.date())
    if daily_exceeded:
        return False, daily_msg

    # check weekly limit
    weekly_exceeded, weekly_msg = check_weekly_limit(tutor_id, start_time.date())
    if weekly_exceeded:
        return False, weekly_msg

    return True, "Slot available"


def slice_availability_into_slots(start_time, end_time, slot_duration, break_duration):
    # slice a large availability block into multiple smaller slots with optional breaks
    slots = []
    current_time = start_time

    # keep creating slots while there's enough time left
    while current_time + timedelta(minutes=slot_duration) <= end_time:
        slot_end = current_time + timedelta(minutes=slot_duration)
        slots.append((current_time, slot_end))

        if len(slots) > 10:
            raise ValueError(
                "You cannot create more than 10 availability slots in one session."
            )

        # move to next slot start time, adding break if specified
        current_time = slot_end + timedelta(minutes=break_duration)
        """
        #handle remaining time if it's at least 30 minutes (and no break would be added)
        remaining_minutes = (end_time - current_time).total_seconds() / 60
        if remaining_minutes >= 30 and break_duration == 0:
            slots.append((current_time, end_time))
        """
    return slots


def create_sliced_availability(
    tutor_id, start_time, end_time, slot_duration, break_duration=0, notes=""
):
    # create multiple availability slots from one time block with optional breaks

    # generate slot times using slicing algorithm
    slot_times = slice_availability_into_slots(
        start_time, end_time, slot_duration, break_duration
    )

    # create Availability objects for each slot
    availability_slots = []
    for slot_start, slot_end in slot_times:
        slot = Availability(
            tutor_id=tutor_id,
            start_time=slot_start,
            end_time=slot_end,
            booked=False,
            notes=notes,
        )
        availability_slots.append(slot)
    return availability_slots

def calculate_slot_score(slot, student_preferences, tutor_id, search_start_date):
    #give a score to a time slot, higher score = better slot
    
    score = 0  #start at 0

    days_away = (slot.start_time.date() - search_start_date).days
    earliness_points = 100 - (days_away * 5) #5 points less for each day away
    
    if earliness_points < 0:
        earliness_points = 0
    
    score = score + earliness_points
    
    #give 50 points if it's during their preferred hours
    if student_preferences:  #check preferences
        if 'preferred_hours' in student_preferences:
            slot_hour = slot.start_time.hour
            
            #check if this hour is in their preferred list
            if slot_hour in student_preferences['preferred_hours']:
                score = score + 50  # give points

    #count how many meetings the tutor already has on this day
    slot_date = slot.start_time.date()
    start_of_day = datetime.combine(slot_date, datetime.min.time())
    end_of_day = datetime.combine(slot_date + timedelta(days=1), datetime.min.time())
    
    meetings_on_day = Meeting.query.filter(
        and_(
            Meeting.tutor_id == tutor_id,
            Meeting.start_time >= start_of_day,
            Meeting.start_time < end_of_day,
            Meeting.status == "Confirmed"
        )
    ).count()
    
    #give points based on the day's workload
    if meetings_on_day < 3:
        score = score + 30
    elif meetings_on_day < 5:
        score = score + 15
    #if more than 5 meetings, no more points are given
    
    #give points for slots between 9am and 5pm the OU wokking hours
    slot_hour = slot.start_time.hour
    
    if slot_hour >= 9 and slot_hour <= 17:
        score = score + 20  #reasonable OU hours
    
    
    #return total score
    return score


def get_student_preferences(student_id):
    #get student from database
    student = Student.query.filter_by(user_id=student_id).first()
    
    # usually as most students prefer between 10 and 16
    preferences = {
        'preferred_hours': [10, 11, 12, 13, 14, 15, 16]
    }
    return preferences


def find_optimal_slot_recursive(
    tutor_id,
    duration,
    date,
    days,
    ignored_meeting_id=None,
    student_id=None,
    best_slot=None,
    best_score=-1,
    search_start_date=None
):

    
    #first call 
    if search_start_date is None:
        search_start_date = date
    
    # start then if no more days to check
    if days <= 0:
        #return best slot found
        return best_slot

    #get student preferences
    student_preferences = None
    if student_id:
        student_preferences = get_student_preferences(student_id)

    #get start and end of this specific day
    start_of_day = datetime.combine(date, datetime.min.time())
    end_of_day = datetime.combine(date, datetime.max.time())
    
    available_slots = Availability.query.filter(
        and_(
            Availability.tutor_id == tutor_id,
            Availability.booked == False,
            Availability.start_time >= start_of_day,
            Availability.start_time <= end_of_day
        )
    ).all()
    
    for slot in available_slots:
        
        #check the duration of teh meeting
        slot_duration = int((slot.end_time - slot.start_time).total_seconds() / 60)
        
        if slot_duration < duration:
            continue  #skip slot
        
        
        #conflict check and resolution
        conflicting_meetings = Meeting.query.filter(
            and_(
                Meeting.tutor_id == tutor_id,
                Meeting.start_time < slot.end_time,
                Meeting.start_time >= slot.start_time,
                Meeting.status == "Confirmed"
            )
        ).all()
        
        # if it is the one being rescheduled remove meeting from the conflicts list
        if ignored_meeting_id:
            conflicting_meetings = [
                m for m in conflicting_meetings 
                if m.meeting_id != ignored_meeting_id
            ]
        
        # if there are conflicts then skip this slot
        if conflicting_meetings:
            continue  #skip slot

        score = calculate_slot_score(
            slot, 
            student_preferences, 
            tutor_id,
            search_start_date
        )
        
        if score > best_score:
            best_slot = slot
            best_score = score
    
    #recursion here
    #move to the next day
    next_date = date + timedelta(days=1)
    
    #recursively check the next day
    return find_optimal_slot_recursive(
        tutor_id=tutor_id,
        duration=duration,
        date=next_date,
        days=days - 1,
        ignored_meeting_id=ignored_meeting_id,
        student_id=student_id,
        best_slot=best_slot,
        best_score=best_score,
        search_start_date=search_start_date
    )
    