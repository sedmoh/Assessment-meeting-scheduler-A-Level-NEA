from abc import ABC, abstractmethod
from datetime import datetime

from algorithms import slice_availability_into_slots
from models import Availability, db


class SlotGenerationStrategy(ABC):
    #abstract strategy for generating availability slots

    @abstractmethod
    def generate_slots(self, start_time, end_time, tutor_id, notes=""):
        #generate availability slots
        pass

    @abstractmethod
    def get_strategy_name(self):
        #get strategy name
        pass


class SingleSlotStrategy(SlotGenerationStrategy):
    #strategy for creating a single availability slot

    def generate_slots(self, start_time, end_time, tutor_id, notes=""):
        #generate a single slot

        slot = Availability(
            tutor_id=tutor_id,
            start_time=start_time,
            end_time=end_time,
            booked=False,
            notes=notes
        )
        return [slot]

    def get_strategy_name(self):
        return "single_slot"


class MultipleSlotStrategy(SlotGenerationStrategy):
    #strategy for slicing availability into multiple slots

    def __init__(self, slot_duration, break_duration=0):
        #initialise strategy
        self._slot_duration = slot_duration
        self._break_duration = break_duration

    def generate_slots(self, start_time, end_time, tutor_id, notes=""):
        #generate multiple slots using slicing algorithm

        #use slicing algorithm
        slot_times = slice_availability_into_slots(
            start_time,
            end_time,
            self._slot_duration,
            self._break_duration
        )

        slots = []
        for slot_start, slot_end in slot_times:
            slot = Availability(
                tutor_id=tutor_id,
                start_time=slot_start,
                end_time=slot_end,
                booked=False,
                notes=notes
            )
            slots.append(slot)

        return slots

    def get_strategy_name(self):
        return f"multiple_slots_{self._slot_duration}min"

    @property
    def slot_duration(self):
        #get slot duration
        return self._slot_duration

    @property
    def break_duration(self):
        #get break duration
        return self._break_duration


class AvailabilityValidator:
    #validate availability creation


    @staticmethod
    def validate_time_range(start_time, end_time):
        #validate time range

        if start_time >= end_time:
            return False, "End time must be after start time"

        if start_time < datetime.now():
            return False, "Cannot create availability in the past"

        return True, None

    @staticmethod
    def validate_tutor_permission(user):
        #validate user can create availability

        if user.role not in ["tutor", "staff_tutor"]:
            return False, "Only tutors can create availability"

        return True, None


class AvailabilitySlot:
    #wrapper class for Availability model with additional functionality

    def __init__(self, availability):
        #initialise availability slot wrapper
        self._availability = availability

    @property
    def availability(self):
        #get availability object
        return self._availability

    @property
    def slot_id(self):
        #get slot ID
        return self._availability.availability_id

    @property
    def tutor_id(self):
        #get tutor ID
        return self._availability.tutor_id

    @property
    def start_time(self):
        #get start time
        return self._availability.start_time

    @property
    def end_time(self):
        #get end time
        return self._availability.end_time

    @property
    def is_booked(self):
        #check if slot is booked
        return self._availability.booked

    @property
    def duration_minutes(self):
        #calculate duration in minutes
        return int((self.end_time - self.start_time).total_seconds() / 60)

    @property
    def is_past(self):
        #check if slot is in the past
        return self.start_time < datetime.now()

    @property
    def is_available(self):
        #check if slot is available for booking
        return not self.is_booked and not self.is_past

    def get_status(self):
        #get slot status
        if self.is_past:
            return "past"
        elif self.is_booked:
            return "booked"
        else:
            return "available"

    def get_formatted_time(self):
        #get formatted time string

        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"

    def book(self):
        #book slot
        self._availability.booked = True

    def unbook(self):
        #make slot available
        self._availability.booked = False

    def delete(self):
        #delete slot if not booked

        if self.is_booked:
            return False, "Cannot delete a booked slot"

        try:
            db.session.delete(self._availability)
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def __str__(self):
        #string representation
        return f"Slot({self.get_formatted_time()}, {self.get_status()})"

    def __repr__(self):
        #detailed representation
        return f"AvailabilitySlot(id={self.slot_id}, time={self.get_formatted_time()}, status={self.get_status()})"


class AvailabilityManager:
    #manager for availability operations

    def __init__(self, tutor_id):
        #initialise availability manager
        self._tutor_id = tutor_id
        self._validator = AvailabilityValidator()
        self._strategy = None

    def set_strategy(self, strategy):
        #set slot generation strategy
        if not isinstance(strategy, SlotGenerationStrategy):
            raise TypeError("Strategy must be instance of SlotGenerationStrategy")

        self._strategy = strategy

    def create_availability(self, start_time, end_time, notes=""):
        #create availability using current strategy
        #validate time range
        is_valid, error = self._validator.validate_time_range(start_time, end_time)
        if not is_valid:
            return None, error

        #check strategy is set
        if not self._strategy:
            return None, "No slot generation strategy set"

        #generate slots using strategy
        try:
            slots = self._strategy.generate_slots(
                start_time,
                end_time,
                self._tutor_id,
                notes
            )

            #save to database
            for slot in slots:
                db.session.add(slot)

            db.session.commit()

            return slots, None

        except Exception as e:
            db.session.rollback()
            return None, str(e)

    def get_all_slots(self):
        #get all availability slots for tutor
        from sorting import merge_sort_meetings

        slots = Availability.query.filter_by(tutor_id=self._tutor_id).all()
        slots = merge_sort_meetings(slots, key="start_time")

        #wrap in AvailabilitySlot objects
        return [AvailabilitySlot(slot) for slot in slots]

    def get_available_slots(self):
        #get only available (unbooked) slots in the future
        from sorting import merge_sort_meetings

        now = datetime.now()
        slots = Availability.query.filter(
            Availability.tutor_id == self._tutor_id,
            Availability.booked == False,
            Availability.start_time > now
        ).all()

        slots = merge_sort_meetings(slots, key="start_time")

        return [AvailabilitySlot(slot) for slot in slots]

    def get_booked_slots(self):
        #get booked slots
        from sorting import merge_sort_meetings

        slots = Availability.query.filter_by(
            tutor_id=self._tutor_id,
            booked=True
        ).all()

        slots = merge_sort_meetings(slots, key="start_time")

        return [AvailabilitySlot(slot) for slot in slots]

    def delete_slot(self, slot_id):
        #delete an availability slot
        slot = Availability.query.get(slot_id)

        if not slot:
            return False, "Slot not found"

        if slot.tutor_id != self._tutor_id:
            return False, "Cannot delete another tutor's slot"

        wrapped_slot = AvailabilitySlot(slot)
        return wrapped_slot.delete()


class AvailabilityPreview:
    #preview availability slots before creation

    def __init__(self, strategy):
        #initialise preview
        self._strategy = strategy

    def generate_preview(self, start_time, end_time):
        #generate preview data without saving to database
        temp_slots = self._strategy.generate_slots(start_time, end_time, 0, "")

        preview_data = []
        for i, slot in enumerate(temp_slots, 1):
            duration = int((slot.end_time - slot.start_time).total_seconds() / 60)

            preview_data.append({
                'number': i,
                'start': slot.start_time.strftime('%H:%M'),
                'end': slot.end_time.strftime('%H:%M'),
                'duration': duration
            })

            #add break info if applicable
            if isinstance(self._strategy, MultipleSlotStrategy):
                if i < len(temp_slots) and self._strategy.break_duration > 0:
                    preview_data[-1]['break_after'] = self._strategy.break_duration

        return preview_data


#function for creating managers
def create_availability_manager(tutor_id, slot_duration=None, break_duration=0):
    #function to create availability manager with strategy

    manager = AvailabilityManager(tutor_id)

    if slot_duration:
        strategy = MultipleSlotStrategy(slot_duration, break_duration)
    else:
        strategy = SingleSlotStrategy()

    manager.set_strategy(strategy)

    return manager
