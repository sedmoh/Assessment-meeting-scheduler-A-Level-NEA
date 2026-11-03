import os
from datetime import datetime, timedelta

import click

from algorithms import (
    PriorityQueue,
    calculate_slot_score,
    find_optimal_slot_recursive,
    get_priority,
    get_student_preferences,
    validate_booking,
)
from auto_email import (
    mail,
    send_admin_created_meeting_email,
    send_admin_deleted_meeting_email,
    send_admin_modified_meeting_email,
    send_booking_confirmation,
    send_cancellation_email,
)
from availability_manager import (
    AvailabilityPreview,
    AvailabilityValidator,
    MultipleSlotStrategy,
    SingleSlotStrategy,
    create_availability_manager,
)
from config import Config
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from generate_teams import init_power_automate_service
from hash_table import user_session_cache
from meeting_manager import (
    MeetingNotesManager,
    MeetingRescheduler,
    create_meeting_booking,
)
from models import Admin, Availability, Meeting, MeetingStatus, StaffTutor, Student, Tutor, User, db
from reports_wip import ReportGenerator
from user_roles import StudentRole, get_user_role
from validation import EmailValidator
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
mail.init_app(app)  # initialise Flask Mail

#to clear session files on startup
def clear_sessions():
    session_dir = os.path.join(app.instance_path, 'flask_session')
    if os.path.exists(session_dir):
        for filename in os.listdir(session_dir):
            file_path = os.path.join(session_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    print(f"Cleared session file: {filename}")
            except Exception as e:
                print(f"Error clearing session file {filename}: {e}")
        print("All sessions cleared on startup")
    else:
        print("No session directory found")

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  #1 hour

#clear sessions on startup
with app.app_context():
    clear_sessions()

#clear cache on startup
with app.app_context():
    #clear the hash table cache
    user_session_cache.clear()
    print("User session cache cleared on startup")

def update_completed_meetings(meetings):
    # update meeting status from Confirmed -> Completed if past
    now = datetime.now()
    updated = False

    for meeting in meetings:
        meeting_end = meeting.start_time + timedelta(minutes=meeting.duration)
        if meeting.status == MeetingStatus.CONFIRMED and meeting_end < now:
            meeting.status = MeetingStatus.COMPLETED
            updated = True

    if updated:
        db.session.commit()

#initialise Power Automate service after app creation
power_automate_service = None

with app.app_context():
    db.create_all()
    print("Database created!")

    #initialise Power Automate service
    power_automate_service = init_power_automate_service(app)

#initialise Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()
    print("Database created!")


@app.route("/")
def home():
    return render_template("index.html")


#roles anyone can choose on the public registration form
#staff tutors and admins must be created by an admin (or the create-admin command)
SELF_REGISTER_ROLES = {"student", "tutor"}
#every valid role, used to check the admin create user form
ALL_ROLES = {"student", "tutor", "staff_tutor", "admin"}

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form.get("role", "")

        if role not in SELF_REGISTER_ROLES:
            flash("Invalid role selected.", "danger")
            return redirect(url_for("register"))

        #validate email using regex
        is_valid, error = EmailValidator.is_valid_email(email)

        if not is_valid:
            flash(error, "danger")
            return redirect(url_for("register"))

        #check if email already exists
        existing_user = User.query.filter_by(email=email.strip().lower()).first()

        if existing_user:
            flash("Email already registered!", "danger")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        new_user = User(
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=hashed_password,
            role=role
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        #emails are stored lowercase, so normalise what was typed the same way
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = None
        cache_hit = False

        #check hash table cache first -> O(1) lookup
        cached_user_id = user_session_cache.get(email)

        if cached_user_id:
            #found in cache, get user from database
            user = User.query.get(cached_user_id)

            #the cached entry can go stale if the user's email was changed or the account
            #was deleted (and its ID reused), so check it still points at the right account
            if user is None or user.email != email:
                user_session_cache.delete(email)
                user = None
                print(f"Stale cache entry for {email} - removed")
            else:
                cache_hit = True
                print(f"Cache HIT for {email}")

        if user is None:
            #not in cache (or stale), query database by email
            user = User.query.filter_by(email=email).first()
            if user:
                #cache for future lookups
                user_session_cache.insert(email, user.user_id)
                print(f"Cache MISS for {email} - now cached")

        #verify password and login
        if user and check_password_hash(user.password_hash, password):
            login_user(user)

            #print cache statistics
            stats = user_session_cache.get_stats()
            print("Cache Statistics")
            print(f"Total cached users: {stats['total_items']}")
            print(f"Load factor: {stats['load_factor']}")
            print(f"Cache hit: {cache_hit}")

            flash(f"Welcome {user.name}!")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password!")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully!")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    #each of the roles has its own get_dashboard_data() implementation

    #get user role object
    user_role = get_user_role(current_user)

    #get dashboard data
    dashboard_data = user_role.get_dashboard_data()

    #check if admin needs redirect to dedicated dashboard
    if dashboard_data.get('redirect_to') == 'admin_dashboard':
        return redirect(url_for('admin_dashboard'))

    #render appropriate template
    template = dashboard_data.pop("template")
    return render_template(template, **dashboard_data)

@app.route("/create_availability", methods=["GET", "POST"])
@login_required
def create_availability():
    #validate user can create availability
    validator = AvailabilityValidator()
    is_valid, error = validator.validate_tutor_permission(current_user)

    if not is_valid:
        flash(error)
        return redirect(url_for("dashboard"))

    #initialise preview data
    preview_slots = None
    form_data = {}

    if request.method == "POST":
        #extract form data
        date = request.form["date"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        notes = request.form.get("notes", "")
        slot_duration = int(request.form.get("slot_duration", 60))
        break_duration = int(request.form.get("break_duration", 0))
        slice_slots = request.form.get("slice_slots") == "on"

        #store form data
        form_data = {
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "notes": notes,
            "slot_duration": slot_duration,
            "break_duration": break_duration,
            "slice_slots": slice_slots
        }

        #parse datetime
        try:
            start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
            end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
        except ValueError as e:
            flash(f"Invalid date/time format: {e!s}")
            return render_template("create_availability.html",
                                 preview_slots=preview_slots,
                                 form_data=form_data)

        #validate time range
        is_valid, error = validator.validate_time_range(start_datetime, end_datetime)
        if not is_valid:
            flash(error)
            return render_template("create_availability.html",
                                 preview_slots=preview_slots,
                                 form_data=form_data)

        #handle preview request
        if request.form.get("action") == "preview":
            #create appropriate strategy
            if slice_slots:
                strategy = MultipleSlotStrategy(slot_duration, break_duration)
            else:
                strategy = SingleSlotStrategy()

            #generate preview
            preview = AvailabilityPreview(strategy)
            preview_slots = preview.generate_preview(start_datetime, end_datetime)

            return render_template("create_availability.html",
                                 preview_slots=preview_slots,
                                 form_data=form_data)

        #creation
        elif request.form.get("action") == "create":
            #create availability manager
            manager = create_availability_manager(
                current_user.user_id,
                slot_duration if slice_slots else None,
                break_duration
            )

            #create availability slots
            slots, error = manager.create_availability(start_datetime, end_datetime, notes)

            if error:
                flash(f"Error creating availability: {error}")
                return redirect(url_for("create_availability"))

            #success message
            break_info = f" with {break_duration}-minute breaks" if break_duration > 0 else ""
            flash(f"Successfully created {len(slots)} availability slot(s){break_info}!")

            return redirect(url_for("dashboard"))

    return render_template("create_availability.html",
                         preview_slots=preview_slots,
                         form_data=form_data)

@app.route("/view-availability")
@login_required
def view_availability():
    # get all available slots
    slots = (
        Availability.query.filter(
            Availability.booked.is_(False),
            Availability.start_time > datetime.now()
        )
        .order_by(Availability.start_time)
        .all()
    )
    return render_template("view_availability.html", slots=slots)

@app.route("/book-meeting/<int:slot_id>", methods=["POST", "GET"])
@login_required
def book_meeting(slot_id):
    #get user role
    user_role = get_user_role(current_user)

    #check for thenpermissions
    if not user_role.has_permission('book_meeting'):
        flash("You don't have permission to book meetings!")
        return redirect(url_for("dashboard"))

    #getthe slot
    slot = Availability.query.get_or_404(slot_id)

    if slot.booked:
        flash("This slot is already booked!")
        return redirect(url_for("view_availability"))

    #determine the booking type
    is_urgent = request.args.get('urgent') == 'true'
    has_adjustment = False

    # check if teh student needs adjustment
    if hasattr(user_role, 'has_reasonable_adjustment'):
        has_adjustment = user_role.has_reasonable_adjustment()

    #create the booking
    booking = create_meeting_booking(
        current_user,
        slot,
        is_urgent=is_urgent,
        has_adjustment=has_adjustment
    )

    #create the meeting
    meeting, error = booking.create_meeting()

    if error:
        flash(f"Cannot book: {error}")
        return redirect(url_for("view_availability"))

    #get student and tutor objects to send the email
    student = User.query.get(current_user.user_id)
    tutor = User.query.get(slot.tutor_id)

    #generate Microsoft Teams meeting link
    teams_link = None
    try:
        if power_automate_service:
            subject = f"Meeting: {student.name} with {tutor.name}"
            if has_adjustment:
                duration = int((slot.end_time - slot.start_time).total_seconds() / 60)
                extra_time = int(duration * 0.25)
                subject += f" [ADJUSTMENT +{extra_time}min]"

            meeting_info = power_automate_service.create_teams_meeting(
                subject=subject,
                start_time=slot.start_time,
                end_time=meeting.end_time,
                student_email=student.email,
                tutor_email=tutor.email,
                student_name=student.name,
                tutor_name=tutor.name,
            )

            if meeting_info and meeting_info.get("success"):
                teams_link = meeting_info["join_url"]
                meeting.meeting_link = teams_link
                db.session.commit()
    except Exception as e:
        print(f"Error creating the Microsoft Teams meeting: {e!s}")

    #send booking confirmation emails
    email_sent = send_booking_confirmation(meeting, student, tutor, app, teams_link)

    if email_sent:
        flash(f"Meeting booked successfully! ({booking.get_booking_type().upper()}) Confirmation emails sent.")
    else:
        flash(f"Meeting booked successfully! ({booking.get_booking_type().upper()}) Email notification failed.")

    return redirect(url_for("dashboard"))


@app.route("/meeting/<int:meeting_id>/public-notes", methods=["GET", "POST"])
@login_required
def edit_public_notes(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    if current_user.role != "tutor" or meeting.tutor_id != current_user.user_id:
        flash("Access denied.")
        return redirect(url_for("dashboard"))

    if meeting.start_time < datetime.now():
        flash("Public notes can no longer be edited after the meeting.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        meeting.public_notes = request.form.get("public_notes")
        db.session.commit()
        flash("Public notes updated.")
        return redirect(url_for("dashboard"))

    return render_template("edit_public_notes.html", meeting=meeting)


@app.route("/meeting/<int:meeting_id>/private-notes", methods=["GET", "POST"])
@login_required
def edit_private_notes(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    if current_user.role != "tutor" or meeting.tutor_id != current_user.user_id:
        flash("Access denied.")
        return redirect(url_for("dashboard"))

    if meeting.start_time > datetime.now():
        flash("Private tutor notes can only be written after the meeting.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        meeting.private_notes = request.form.get("private_notes")
        db.session.commit()
        flash("Private tutor notes saved.")
        return redirect(url_for("dashboard"))

    return render_template("edit_private_notes.html", meeting=meeting)


@app.route("/delete-availability/<int:slot_id>", methods=["POST"])
@login_required
def delete_availability(slot_id):
    #delete availability slot

    #create manager for current user
    manager = create_availability_manager(current_user.user_id)

    #delete slot
    success, error = manager.delete_slot(slot_id)

    if success:
        flash("Availability slot deleted successfully!")
    else:
        flash(f"Error: {error}")

    return redirect(url_for("dashboard"))


@app.route("/cancel-meeting/<int:meeting_id>", methods=["POST"])
@login_required
def cancel_meeting(meeting_id):
    from datetime import datetime

    meeting = Meeting.query.get_or_404(meeting_id)

    # check if meeting has passed
    if meeting.start_time < datetime.now():
        flash("Cannot cancel a meeting that has already passed!")
        return redirect(url_for("dashboard"))

    # check if user can still cancel
    if current_user.role == "student" and meeting.student_id != current_user.user_id:
        flash("You can only cancel your own meetings!")
        return redirect(url_for("dashboard"))

    if current_user.role == "tutor" and meeting.tutor_id != current_user.user_id:
        flash("You can only cancel your own meetings!")
        return redirect(url_for("dashboard"))

    # get student and tutor details for email notification
    student = User.query.get(meeting.student_id)
    tutor = User.query.get(meeting.tutor_id)

    # send cancellation emails before deleting the meeting
    send_cancellation_email(meeting, student, tutor, app)

    # mark availability slot as available
    availability = Availability.query.get(meeting.availability_id)
    if availability:
        availability.booked = False

    # delete the meeting
    db.session.delete(meeting)
    db.session.commit()

    flash("Meeting cancelled successfully! Notification emails sent.")
    return redirect(url_for("dashboard"))


@app.route("/reschedule/<int:meeting_id>", methods=["GET", "POST"])
@login_required
def reschedule_meeting(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    #check permissions
    user_role = get_user_role(current_user)
    if not user_role.can_manage_meetings():
        flash("You don't have permission to reschedule meetings!")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        new_slot_id = request.form.get("new_slot_id")

        if not new_slot_id:
            flash("Please select a new slot!")
            return redirect(url_for("reschedule_meeting", meeting_id=meeting_id))

        new_slot = Availability.query.get(int(new_slot_id))

        if not new_slot:
            flash("Invalid slot selected!")
            return redirect(url_for("reschedule_meeting", meeting_id=meeting_id))

        #use rescheduler
        rescheduler = MeetingRescheduler(meeting)
        success, error = rescheduler.reschedule(new_slot)

        if not success:
            flash(f"Cannot reschedule: {error}")
            return redirect(url_for("reschedule_meeting", meeting_id=meeting_id))

        flash(f"Meeting rescheduled successfully to {new_slot.start_time.strftime('%b %d, %Y at %H:%M')}!")
        return redirect(url_for("dashboard"))

    #GET - show available slots
    if current_user.role == "student":
        available_slots = Availability.query.filter_by(booked=False).order_by(Availability.start_time).all()
    else:
        #create manager to get slots
        manager = create_availability_manager(current_user.user_id)
        available_slots = [slot.availability for slot in manager.get_available_slots()]

    return render_template("reschedule.html", meeting=meeting, available_slots=available_slots)


@app.route("/urgent-booking", methods=["GET", "POST"])
@login_required
def urgent_booking():
    if current_user.role != "student":
        flash("Only students can make urgent bookings!")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        slot_id = request.form.get("slot_id")

        if not slot_id:
            flash("Please select a time slot!")
            return redirect(url_for("urgent_booking"))

        slot = Availability.query.get_or_404(int(slot_id))

        if slot.booked:
            flash("This slot is already booked!")
            return redirect(url_for("urgent_booking"))

        # get student and tutor info
        student = User.query.get(current_user.user_id)
        tutor = User.query.get(slot.tutor_id)

        # calculate base duration
        base_duration = int((slot.end_time - slot.start_time).total_seconds() / 60)

        # check for reasonable adjustments
        student_profile = Student.query.filter_by(user_id=student.user_id).first()
        has_adjustment = False
        adjustment_notes = ""
        actual_duration = base_duration
        adjusted_end_time = slot.end_time

        if student_profile and student_profile.has_adjustment:
            has_adjustment = True
            extra_time = int(base_duration * 0.25)
            actual_duration = base_duration + extra_time
            adjusted_end_time = slot.start_time + timedelta(minutes=actual_duration)
            adjustment_notes = f"URGENT BOOKING - REASONABLE ADJUSTMENT: Student requires additional time (+{extra_time} mins, +25%)"
        else:
            adjustment_notes = "URGENT BOOKING: Priority scheduled"

        # validate booking with adjusted time
        is_valid, error_message = validate_booking(
            tutor_id=slot.tutor_id,
            start_time=slot.start_time,
            end_time=adjusted_end_time,
        )

        if not is_valid:
            flash(f"Cannot book: {error_message}")
            return redirect(url_for("urgent_booking"))

        # generate Teams meeting link
        teams_link = None
        try:
            if power_automate_service:
                subject = f"URGENT: {student.name} with {tutor.name}"
                if has_adjustment:
                    subject += f" [ADJUSTMENT +{int(base_duration * 0.25)}min]"

                meeting_info = power_automate_service.create_teams_meeting(
                    subject=subject,
                    start_time=slot.start_time,
                    end_time=adjusted_end_time,
                    student_email=student.email,
                    tutor_email=tutor.email,
                    student_name=student.name,
                    tutor_name=tutor.name,
                )

                if meeting_info and meeting_info.get("success"):
                    teams_link = meeting_info["join_url"]
        except Exception as e:
            print(f"Error creating Teams meeting: {e!s}")

        # create urgent meeting with high priority
        new_meeting = Meeting(
            student_id=current_user.user_id,
            tutor_id=slot.tutor_id,
            availability_id=slot.availability_id,
            start_time=slot.start_time,
            duration=actual_duration,
            meeting_link=teams_link,
            adjustment_flag=has_adjustment,
            notes=adjustment_notes,
            status=MeetingStatus.CONFIRMED,
        )

        # mark slot as booked
        slot.booked = True
        db.session.add(new_meeting)
        db.session.commit()

        # send confirmation emails
        email_sent = send_booking_confirmation(
            new_meeting, student, tutor, app, teams_link
        )

        flash(
            f"URGENT booking confirmed with {tutor.name} on {slot.start_time.strftime('%b %d, %Y at %H:%M')}! "
            + (
                "Confirmation emails sent."
                if email_sent
                else "Email notification failed."
            )
        )

        return redirect(url_for("dashboard"))

    # GET request - show available slots within next 48 hours for urgent booking
    now = datetime.now()
    urgent_deadline = now + timedelta(hours=48)

    available_slots = (
        Availability.query.filter(
            Availability.booked.is_(False),
            Availability.start_time >= now,
            Availability.start_time <= urgent_deadline,
        )
        .order_by(Availability.start_time)
        .all()
    )

    return render_template("urgent_booking.html", slots=available_slots, now=now)


@app.route("/profile/<name>")
def profile(name):
    return render_template("profile.html", name=name)


@app.route("/urgent-bookings")
@login_required
def urgent_bookings():
    # display urgent bookings sorted by priority
    if current_user.role not in ["admin", "staff_tutor"]:
        flash("Access denied!")
        return redirect(url_for("dashboard"))

    # get all booked meetings
    all_meetings = Meeting.query.filter_by(status=MeetingStatus.CONFIRMED).all()

    # create priority queue
    pq = PriorityQueue()
    for meeting in all_meetings:
        student = User.query.get(meeting.student_id)
        priority = get_priority(meeting, student)
        pq.push(meeting, priority)

    # take out sorted urgent meetings
    urgent_meetings = []
    while not pq.is_empty():
        urgent_meetings.append(pq.pop())

    return render_template("urgent_bookings.html", meetings=urgent_meetings)


@app.route("/auto_schedule/<int:meeting_id>/setup", methods=["GET", "POST"])
@login_required
def auto_schedule_setup(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    if request.method == "POST":
        days = int(request.form.get("number_of_days"))
        return redirect(url_for("auto_schedule", meeting_id=meeting_id, days=days))
    return render_template("auto_schedule_setup.html", meeting=meeting)


@app.route("/auto_schedule/<int:meeting_id>")
@login_required
def auto_schedule(meeting_id):

    #get meeting
    meeting = Meeting.query.get_or_404(meeting_id)

    #get number of days
    days = request.args.get("days", type=int)

    if days is None:
        return redirect(url_for("auto_schedule_setup", meeting_id=meeting_id))

    #start from the original meetings date
    start_date = meeting.start_time.date()

    #ifin past, start from today
    start_date = max(start_date, datetime.now().date())

    #main function call
    best_slot = find_optimal_slot_recursive(
        tutor_id=meeting.tutor_id,
        duration=meeting.duration,
        date=start_date,
        days=days,
        ignored_meeting_id=meeting.meeting_id,
        student_id=meeting.student_id
    )

    if not best_slot:
        #no available slots found
        flash(
            f"Sorry! No available slot found from {start_date} for the next {days} days.",
            "warning"
        )
        return redirect(url_for("dashboard"))

    student_prefs = get_student_preferences(meeting.student_id)
    slot_score = calculate_slot_score(
        best_slot,
        student_prefs,
        meeting.tutor_id,
        start_date
    )

    return render_template(
        "auto_schedule_results.html",
        meeting=meeting,
        best_slot=best_slot,
        slot_score=slot_score,
        max_score=200  #maximum possible score
    )

@app.route("/confirm_auto_reschedule/<int:meeting_id>/<int:slot_id>", methods=["POST"])
@login_required
def confirm_auto_reschedule(meeting_id, slot_id):

    meeting = Meeting.query.get_or_404(meeting_id)
    new_slot = Availability.query.get_or_404(slot_id)

    #update slot
    old_slot = Availability.query.get(meeting.availability_id)
    if old_slot:
        old_slot.booked = False  #make meeting available again

    #update meeting details
    meeting.availability_id = new_slot.availability_id
    meeting.start_time = new_slot.start_time
    meeting.tutor_id = new_slot.tutor_id

    #mark new slot as booked
    new_slot.booked = True

    db.session.commit()

    flash(
        f"Meeting successfully rescheduled to "
        f"{new_slot.start_time.strftime('%A, %B %d at %I:%M %p')}!",
        "success"
    )

    #send them back to dashboard
    return redirect(url_for("dashboard"))


@app.route("/staff-tutor/select-tutor")
@login_required
def select_tutor():
    # staff tutor selects which tutor to manage
    if current_user.role != "staff_tutor":
        flash("Access denied! Staff tutors only!")
        return redirect(url_for("dashboard"))

    # get all tutors
    tutors = User.query.filter(User.role.in_(["tutor", "staff_tutor"])).all()

    return render_template("select_tutor.html", tutors=tutors)


@app.route("/staff-tutor/manage-tutor/<int:tutor_id>")
@login_required
def manage_tutor(tutor_id):
    # view and manage a specific tutor"s schedule
    if current_user.role != "staff_tutor":
        flash("Access denied! Staff tutors only!")
        return redirect(url_for("dashboard"))

    tutor = User.query.get_or_404(tutor_id)

    if tutor.role not in ["tutor", "staff_tutor"]:
        flash("Invalid tutor selected!")
        return redirect(url_for("select_tutor"))

    # get tutor availability and meetings
    availability_slots = (
        Availability.query.filter_by(tutor_id=tutor_id)
        .order_by(Availability.start_time)
        .all()
    )

    tutor_meetings = Meeting.query.filter_by(tutor_id=tutor_id).all()

    return render_template(
        "manage_tutor.html",
        tutor=tutor,
        availability_slots=availability_slots,
        tutor_meetings=tutor_meetings,
    )


@app.route("/staff-tutor/book-on-behalf/<int:tutor_id>", methods=["GET", "POST"])
@login_required
def book_on_behalf(tutor_id):
    # staff tutor books a meeting on behalf of a tutor
    if current_user.role != "staff_tutor":
        flash("Access denied! Staff tutors only!")
        return redirect(url_for("dashboard"))

    tutor = User.query.get_or_404(tutor_id)

    if request.method == "POST":
        student_id = request.form.get("student_id")
        slot_id = request.form.get("slot_id")

        if not student_id or not slot_id:
            flash("Please select both a student and a time slot!")
            return redirect(url_for("book_on_behalf", tutor_id=tutor_id))

        slot = Availability.query.get_or_404(slot_id)

        if slot.booked:
            flash("This slot is already booked!")
            return redirect(url_for("book_on_behalf", tutor_id=tutor_id))

        # validate booking (staff tutors can override limits if needed)
        from algorithms import validate_booking

        is_valid, error_message = validate_booking(
            tutor_id=tutor_id, start_time=slot.start_time, end_time=slot.end_time
        )

        if not is_valid:
            # staff tutors can see the warning but still proceed
            flash(
                f"Warning: {error_message}. Booking anyway as staff tutor!", "warning"
            )

        # calculate duration
        duration = int((slot.end_time - slot.start_time).total_seconds() / 60)

        # create meeting
        new_meeting = Meeting(
            student_id=student_id,
            tutor_id=tutor_id,
            availability_id=slot.availability_id,
            start_time=slot.start_time,
            duration=duration,
            status=MeetingStatus.CONFIRMED,
            notes=f"Booked by staff tutor: {current_user.name}",
        )

        slot.booked = True

        db.session.add(new_meeting)
        db.session.commit()

        # send confirmation emails to both student and tutor
        student = User.query.get(student_id)
        email_sent = send_booking_confirmation(new_meeting, student, tutor, app)

        if email_sent:
            flash(
                f"Meeting booked successfully for {tutor.name}! Confirmation emails sent."
            )
        else:
            flash(
                f"Meeting booked successfully for {tutor.name}! (Email notification failed)"
            )

        return redirect(url_for("manage_tutor", tutor_id=tutor_id))

    # GET request -> show booking form
    students = User.query.filter_by(role="student").all()
    available_slots = (
        Availability.query.filter_by(tutor_id=tutor_id, booked=False)
        .order_by(Availability.start_time)
        .all()
    )

    return render_template(
        "book_on_behalf.html",
        tutor=tutor,
        students=students,
        available_slots=available_slots,
    )

@app.route("/student/reasonable-adjustment", methods=["GET", "POST"])
@login_required
def manage_reasonable_adjustment():
    if current_user.role != "student":
        flash("Only students can access this page!")
        return redirect(url_for("dashboard"))

    # get or create profile
    student_profile = Student.query.filter_by(user_id=current_user.user_id).first()
    if not student_profile:
        student_profile = Student(user_id=current_user.user_id, has_adjustment=False)
        db.session.add(student_profile)
        db.session.commit()

    if request.method == "POST":
        # checkbox sends value ONLY when checked
        new_state = request.form.get("adjustment_flag") == "on"
        student_profile.has_adjustment = new_state
        db.session.commit()

        if new_state:
            flash("Reasonable adjustment enabled (+25% extra time).")
        else:
            flash("Reasonable adjustment disabled.")

        return redirect(url_for("manage_reasonable_adjustment"))

    return render_template(
        "reasonable_adjustment.html", student_profile=student_profile
    )

@app.route("/meeting/<int:meeting_id>/notes", methods=["GET", "POST"])
@login_required
def manage_meeting_notes(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    #check permission
    user_role = get_user_role(current_user)

    if not user_role.has_permission('manage_notes'):
        flash("Only tutors can manage meeting notes!")
        return redirect(url_for("dashboard"))

    #additional check for correct tutor
    if hasattr(user_role, 'can_manage_notes'):
        if not user_role.can_manage_notes(meeting):
            flash("You can only manage notes for your own meetings!")
            return redirect(url_for("dashboard"))

    #create notes manager
    notes_manager = MeetingNotesManager(meeting)

    if request.method == "POST":
        public_notes = request.form.get("public_notes", "").strip()
        private_notes = request.form.get("private_notes", "").strip()

        #update notes
        success = notes_manager.update_notes(public_notes, private_notes)

        if success:
            flash("Meeting notes updated successfully!")
        else:
            flash("Error updating notes!")

        return redirect(url_for("dashboard"))

    return render_template("manage_meeting_notes.html", meeting=meeting)

@app.route("/meeting/<int:meeting_id>/view-notes")
@login_required
def view_meeting_notes(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)

    #check if user is part of this meeting
    if current_user.user_id != meeting.student_id and current_user.user_id != meeting.tutor_id:
        flash("You don't have permission to view these notes!")
        return redirect(url_for("dashboard"))

    #get user role
    user_role = get_user_role(current_user)

    is_tutor = user_role.has_permission('view_private_notes')
    is_student = isinstance(user_role, StudentRole)

    return render_template("view_meeting_notes.html",
                         meeting=meeting,
                         is_tutor=is_tutor,
                         is_student=is_student)

@app.route("/admin")
@login_required
def admin():
    #redirect to admin dashboard
    if current_user.role != "admin":
        flash("Admin access required")
        return redirect(url_for("dashboard"))
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    #admin dashboard with full system overview
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    #get system statistics
    total_users = User.query.count()
    total_meetings = Meeting.query.count()
    total_availability = Availability.query.filter_by(booked=False).count()
    students_with_adjustments = Student.query.filter_by(has_adjustment=True).count()

    #user counts by role
    user_counts = {
        'students': User.query.filter_by(role='student').count(),
        'tutors': User.query.filter_by(role='tutor').count(),
        'staff_tutors': User.query.filter_by(role='staff_tutor').count(),
        'admins': User.query.filter_by(role='admin').count()
    }

    #recent users (last 5)
    recent_users = User.query.order_by(User.date_created.desc()).limit(5).all()

    #recent meetings (last 5)
    recent_meetings = Meeting.query.order_by(Meeting.start_time.desc()).limit(5).all()

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_meetings=total_meetings,
        total_availability=total_availability,
        students_with_adjustments=students_with_adjustments,
        user_counts=user_counts,
        recent_users=recent_users,
        recent_meetings=recent_meetings
    )


@app.route("/admin/users")
@login_required
def admin_manage_users():
    #manage all users with filtering
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    #get filter parameters
    role_filter = request.args.get('role', '')
    search_query = request.args.get('search', '')

    #build query
    query = User.query

    #apply role filter
    if role_filter:
        query = query.filter_by(role=role_filter)

    #apply search filter
    if search_query:
        query = query.filter(
            (User.name.contains(search_query)) |
            (User.email.contains(search_query))
        )

    #get all users
    users = query.order_by(User.date_created.desc()).all()

    return render_template("admin_manage_users.html", users=users)


@app.route("/admin/users/create", methods=["GET", "POST"])
@login_required
def admin_create_user():
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        role = request.form["role"]

        if role not in ALL_ROLES:
            flash("Invalid role selected.", "danger")
            return redirect(url_for("admin_create_user"))

        #validate email using regex
        is_valid, error = EmailValidator.is_valid_email(email)

        if not is_valid:
            flash(error, "danger")
            return redirect(url_for("admin_create_user"))

        #check passwords match
        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for("admin_create_user"))

        #check if email exists
        if User.query.filter_by(email=email.strip().lower()).first():
            flash("Email already exists!", "danger")
            return redirect(url_for("admin_create_user"))

        user = User(
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=generate_password_hash(password),
            role=role
        )

        db.session.add(user)
        db.session.commit()

        flash(f"User {name} created successfully!", "success")
        return redirect(url_for("admin_manage_users"))

    return render_template("admin_user_form.html", user=None)

@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_user(user_id):
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)
    student_profile = Student.query.filter_by(user_id=user_id).first()
    tutor_profile = Tutor.query.filter_by(user_id=user_id).first()

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]

        #valide email using regex if changed
        if email.strip().lower() != user.email.lower():
            is_valid, error = EmailValidator.is_valid_email(email)
            if not is_valid:
                flash(error, "danger")
                return redirect(url_for("admin_edit_user", user_id=user_id))

            #check if new email already exists
            existing = User.query.filter_by(email=email.strip().lower()).first()
            if existing and existing.user_id != user_id:
                flash("Email already exists!", "danger")
                return redirect(url_for("admin_edit_user", user_id=user_id))

        #update user
        old_email = user.email
        user.name = name.strip()
        user.email = email.strip().lower()

        #the old email must stop working for login
        if user.email != old_email:
            user_session_cache.delete(old_email)

        #update role-specific settings
        if user.role == "student" and student_profile:
            student_profile.has_adjustment = request.form.get("has_adjustment") == "on"

        if user.role == "tutor" and tutor_profile:
            tutor_profile.daily_limit = int(request.form.get("daily_limit", 4))
            tutor_profile.weekly_limit = int(request.form.get("weekly_limit", 10))

        db.session.commit()
        flash(f"User {name} updated successfully!", "success")
        return redirect(url_for("admin_manage_users"))

    return render_template(
        "admin_user_form.html",
        user=user,
        student_profile=student_profile,
        tutor_profile=tutor_profile
    )

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    #delete user account (admin override)
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    #prevent self deletion
    if user_id == current_user.user_id:
        flash("You cannot delete your own account!")
        return redirect(url_for("admin_manage_users"))

    user = User.query.get_or_404(user_id)
    user_name = user.name

    #delete role-specific profile
    if user.role == "student":
        Student.query.filter_by(user_id=user_id).delete()
        #delete student's meetings
        Meeting.query.filter_by(student_id=user_id).delete()
    elif user.role == "tutor":
        Tutor.query.filter_by(user_id=user_id).delete()
        #delete tutor's availability and meetings
        Availability.query.filter_by(tutor_id=user_id).delete()
        Meeting.query.filter_by(tutor_id=user_id).delete()
    elif user.role == "staff_tutor":
        StaffTutor.query.filter_by(user_id=user_id).delete()
        Availability.query.filter_by(tutor_id=user_id).delete()
        Meeting.query.filter_by(tutor_id=user_id).delete()
    elif user.role == "admin":
        Admin.query.filter_by(user_id=user_id).delete()

    #delete user
    user_session_cache.delete(user.email)
    db.session.delete(user)
    db.session.commit()

    flash(f"User {user_name} has been permanently deleted!")
    return redirect(url_for("admin_manage_users"))


@app.route("/admin/users/<int:user_id>/meetings")
@login_required
def admin_view_student_meetings(user_id):
    #view specific student meetings (admin override)
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)

    if user.role != "student":
        flash("This user is not a student!")
        return redirect(url_for("admin_manage_users"))

    meetings = Meeting.query.filter_by(student_id=user_id).order_by(Meeting.start_time.desc()).all()

    return render_template("admin_view_student_meetings.html", user=user, meetings=meetings)


@app.route("/admin/reports")
@login_required
def admin_reports():
    #generate comprehensive system reports
    if current_user.role not in ["admin", "staff_tutor"]:
        flash("Access denied!")
        return redirect(url_for("dashboard"))

    #get all statistics
    tutor_stats = ReportGenerator.get_tutor_statistics()
    busy_tutors = ReportGenerator.get_busy_tutors(limit=10)
    weekly_dist = ReportGenerator.get_weekly_meeting_distribution()
    popular_times = ReportGenerator.get_popular_time_slots()
    student_engagement = ReportGenerator.get_student_engagement_rate()
    availability_util = ReportGenerator.get_availability_utilisation()
    monthly_meetings = ReportGenerator.get_meetings_by_month()
    workload_comparison = ReportGenerator.get_tutor_workload_comparison()
    students_with_adjustments = ReportGenerator.get_students_with_adjustments()

    return render_template(
        "admin_reports.html",
        tutor_stats=tutor_stats,
        busy_tutors=busy_tutors,
        weekly_dist=weekly_dist,
        popular_times=popular_times,
        student_engagement=student_engagement,
        availability_util=availability_util,
        monthly_meetings=monthly_meetings,
        workload_comparison=workload_comparison,
        students_with_adjustments=students_with_adjustments,
    )

@app.route("/admin/manage-student/<int:user_id>")
@login_required
def admin_manage_student(user_id):
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    student = User.query.get_or_404(user_id)

    if student.role != "student":
        flash("This user is not a student!")
        return redirect(url_for("admin_manage_users"))

    #get student profile
    student_profile = Student.query.filter_by(user_id=user_id).first()

    #get all meetings
    from sorting import merge_sort_meetings
    all_meetings = Meeting.query.filter_by(student_id=user_id).all()
    all_meetings = merge_sort_meetings(all_meetings, key="start_time")

    #separate into past and upcoming
    now = datetime.now()
    upcoming_meetings = []
    past_meetings = []

    for meeting in all_meetings:
        meeting_end = meeting.start_time + timedelta(minutes=meeting.duration)
        if meeting_end < now:
            past_meetings.append(meeting)
        else:
            upcoming_meetings.append(meeting)

    return render_template(
        "admin_manage_student.html",
        student=student,
        student_profile=student_profile,
        all_meetings=all_meetings,
        upcoming_meetings=upcoming_meetings,
        past_meetings=past_meetings,
        now=now
    )

@app.route("/admin/manage-tutor/<int:user_id>")
@login_required
def admin_manage_tutor(user_id):
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    tutor = User.query.get_or_404(user_id)

    if tutor.role not in ["tutor", "staff_tutor"]:
        flash("This user is not a tutor!")
        return redirect(url_for("admin_manage_users"))

    #get availability slots
    from sorting import merge_sort_meetings
    availability_slots = Availability.query.filter_by(tutor_id=user_id).all()
    availability_slots = merge_sort_meetings(availability_slots, key="start_time")

    #get meetings
    tutor_meetings = Meeting.query.filter_by(tutor_id=user_id).all()
    tutor_meetings = merge_sort_meetings(tutor_meetings, key="start_time")

    return render_template(
        "admin_manage_tutor.html",
        tutor=tutor,
        availability_slots=availability_slots,
        tutor_meetings=tutor_meetings,
        now=datetime.now()
    )

@app.route("/admin/meetings")
@login_required
def admin_view_all_meetings():
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    #get filter parameters
    status_filter = request.args.get('status', '')
    student_filter = request.args.get('student', '')
    tutor_filter = request.args.get('tutor', '')

    #build query
    query = Meeting.query

    #apply filters
    if status_filter:
        query = query.filter_by(status=status_filter)

    if student_filter:
        query = query.filter(Meeting.student_id == int(student_filter))

    if tutor_filter:
        query = query.filter(Meeting.tutor_id == int(tutor_filter))

    #get all meetings
    meetings = query.order_by(Meeting.start_time.desc()).all()

    #get all students and tutors for filter dropdowns
    students = User.query.filter_by(role='student').order_by(User.name).all()
    tutors = User.query.filter(User.role.in_(['tutor', 'staff_tutor'])).order_by(User.name).all()

    #separate into upcoming and past
    now = datetime.now()
    upcoming_meetings = [m for m in meetings if m.start_time >= now]
    past_meetings = [m for m in meetings if m.start_time < now]

    return render_template(
        "admin_view_meetings.html",
        upcoming_meetings=upcoming_meetings,
        past_meetings=past_meetings,
        students=students,
        tutors=tutors,
        now=now
    )

@app.route("/admin/meeting/create", methods=["GET", "POST"])
@login_required
def admin_create_meeting():
    #admin creates a new meeting on behalf of student and tutor
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        student_id = int(request.form["student_id"])
        tutor_id = int(request.form["tutor_id"])
        date = request.form["date"]
        start_time = request.form["start_time"]
        duration = int(request.form["duration"])
        meeting_link = request.form.get("meeting_link", "")
        public_notes = request.form.get("public_notes", "")
        admin_reason = request.form["admin_reason"]
        skip_conflict = request.form.get("skip_conflict_check") == "on"
        skip_limits = request.form.get("skip_limit_check") == "on"

        #parse datetime
        start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")

        #get student and tutor
        student = User.query.get_or_404(student_id)
        tutor = User.query.get_or_404(tutor_id)

        #check for reasonable adjustments
        student_profile = Student.query.filter_by(user_id=student_id).first()
        adjustment_flag = False
        if student_profile and student_profile.has_adjustment:
            extra_time = int(duration * 0.25)
            duration += extra_time
            adjustment_flag = True

        #validate if not skipping
        if not skip_conflict:
            end_datetime = start_datetime + timedelta(minutes=duration)
            is_valid, error = validate_booking(tutor_id, start_datetime, end_datetime)
            if not is_valid and not skip_limits:
                flash(f"Conflict detected: {error}. Use override option to proceed anyway.")
                return redirect(url_for("admin_create_meeting"))

        #generate Teams link if not provided
        teams_link = meeting_link
        if not teams_link and power_automate_service:
            try:
                meeting_info = power_automate_service.create_teams_meeting(
                    subject=f"Meeting: {student.name} with {tutor.name} (Admin Scheduled)",
                    start_time=start_datetime,
                    end_time=start_datetime + timedelta(minutes=duration),
                    student_email=student.email,
                    tutor_email=tutor.email,
                    student_name=student.name,
                    tutor_name=tutor.name,
                )
                if meeting_info and meeting_info.get("success"):
                    teams_link = meeting_info["join_url"]
            except Exception as e:
                print(f"Error creating Teams meeting: {e!s}")

        #create meeting
        new_meeting = Meeting(
            student_id=student_id,
            tutor_id=tutor_id,
            availability_id=None,
            start_time=start_datetime,
            duration=duration,
            meeting_link=teams_link,
            adjustment_flag=adjustment_flag,
            status=MeetingStatus.CONFIRMED,
            public_notes=public_notes,
            notes=f"Created by admin: {current_user.name}. Reason: {admin_reason}"
        )

        db.session.add(new_meeting)
        db.session.commit()

        #send notification emails
        send_admin_created_meeting_email(
            new_meeting, student, tutor, current_user, admin_reason, app, teams_link
        )

        flash(f"Meeting created successfully! Both {student.name} and {tutor.name} have been notified.")
        return redirect(url_for("admin_dashboard"))

    students = User.query.filter_by(role="student").order_by(User.name).all()
    tutors = User.query.filter(User.role.in_(["tutor", "staff_tutor"])).order_by(User.name).all()

    return render_template("admin_create_meeting.html", students=students, tutors=tutors)

@app.route("/admin/meeting/<int:meeting_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_meeting(meeting_id):
    #admin edits an existing meeting
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    meeting = Meeting.query.get_or_404(meeting_id)

    if request.method == "POST":
        #store old details for comparison
        old_details = {
            'date': meeting.start_time.strftime("%B %d, %Y"),
            'start_time': meeting.start_time.strftime("%H:%M"),
            'end_time': meeting.end_time.strftime("%H:%M"),
            'duration': meeting.duration
        }

        #get new details
        date = request.form["date"]
        start_time = request.form["start_time"]
        duration = int(request.form["duration"])
        meeting_link = request.form.get("meeting_link", "")
        public_notes = request.form.get("public_notes", "")
        status = request.form["status"]
        admin_reason = request.form["admin_reason"]

        if status not in MeetingStatus.ALL:
            flash("Invalid meeting status.", "danger")
            return redirect(url_for("admin_edit_meeting", meeting_id=meeting_id))
        skip_conflict = request.form.get("skip_conflict_check") == "on"

        #parse new datetime
        new_start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")

        #validate if not skipping and time changed
        if not skip_conflict and new_start_datetime != meeting.start_time:
            end_datetime = new_start_datetime + timedelta(minutes=duration)
            is_valid, error = validate_booking(
                meeting.tutor_id,
                new_start_datetime,
                end_datetime,
                ignored_meeting_id=meeting_id
            )
            if not is_valid:
                flash(f"Conflict detected: {error}. Use override option to proceed anyway.")
                return redirect(url_for("admin_edit_meeting", meeting_id=meeting_id))

        #update meeting
        meeting.start_time = new_start_datetime
        meeting.duration = duration
        meeting.meeting_link = meeting_link or meeting.meeting_link
        meeting.public_notes = public_notes
        meeting.status = status
        meeting.notes = (meeting.notes or "") + f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Modified by admin: {current_user.name}. Reason: {admin_reason}"

        db.session.commit()

        #send notification emails
        student = User.query.get(meeting.student_id)
        tutor = User.query.get(meeting.tutor_id)
        send_admin_modified_meeting_email(
            meeting, student, tutor, current_user, admin_reason, old_details, app
        )

        flash("Meeting updated successfully! Both parties have been notified.")
        return redirect(url_for("admin_manage_student", user_id=student.user_id))

    return render_template("admin_edit_meeting.html", meeting=meeting)


@app.route("/admin/meeting/<int:meeting_id>/delete", methods=["POST"])
@login_required
def admin_delete_meeting(meeting_id):
    #admin deletes a meeting
    if current_user.role != "admin":
        flash("Admin access required!")
        return redirect(url_for("dashboard"))

    meeting = Meeting.query.get_or_404(meeting_id)
    admin_reason = request.form.get("admin_reason", "No reason provided")

    #get student and tutor before deleting
    student = User.query.get(meeting.student_id)
    tutor = User.query.get(meeting.tutor_id)

    #free up availability slot if exists
    if meeting.availability_id:
        availability = Availability.query.get(meeting.availability_id)
        if availability:
            availability.booked = False

    #dend notification before deleting
    send_admin_deleted_meeting_email(meeting, student, tutor, current_user, admin_reason, app)

    #delete meeting
    db.session.delete(meeting)
    db.session.commit()

    flash(f"Meeting deleted successfully! Both {student.name} and {tutor.name} have been notified.")
    return redirect(request.referrer or url_for("admin_dashboard"))


@app.cli.command("create-admin")
@click.argument("name")
@click.argument("email")
def create_admin(name, email):
    """Create an admin account from the command line.

    Usage: flask --app app create-admin "Your Name" you@example.com
    """
    email = email.strip().lower()

    is_valid, error = EmailValidator.is_valid_email(email)
    if not is_valid:
        raise click.ClickException(error)

    if User.query.filter_by(email=email).first():
        raise click.ClickException(f"{email} is already registered.")

    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    user = User(
        name=name.strip(),
        email=email,
        password_hash=generate_password_hash(password),
        role="admin"
    )
    db.session.add(user)
    db.session.commit()

    db.session.add(Admin(user_id=user.user_id, access_level="full", permissions="all"))
    db.session.commit()
    click.echo(f"Admin account created for {email}.")


if __name__ == "__main__":
    #debug mode only when FLASK_DEBUG=1 is set (e.g. in your local .env)
    #the Werkzeug debugger lets anyone who can reach it run code on the server
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
