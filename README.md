# Assessment Meeting Scheduler

A Flask web app for booking one-to-one assessment meetings between students and tutors. It is designed around the Open University's TM113 module: tutors publish their free time, students book slots, and staff tutors and admins oversee the whole process.

I built it as my AQA A-level Computer Science NEA. The project has since been submitted. I've kept working on this repository afterwards to fix bugs and security issues I found on review, adding a regression test for each fix (see [Post-submission fixes](#post-submission-fixes)).

## Features

**Students**
- Browse tutor availability and book meetings
- Request urgent bookings (within 24 hours), which get the highest priority
- Register a reasonable adjustment, which automatically adds 25% extra meeting time
- Cancel or reschedule meetings, and read the public notes a tutor leaves after a meeting

**Tutors**
- Create availability as one slot, or as a block split into fixed-length slots with optional breaks (with a preview first)
- Daily and weekly meeting limits (4/day and 10/week by default)
- Public notes (seen by the student) and private notes (seen only by the tutor) on each meeting
- **Auto-reschedule**: a recursive search over the coming days that scores free slots and suggests the best one

**Staff tutors**
- Everything a tutor can do, plus managing other tutors and booking meetings for them
- Can override a tutor's limits

**Admins**
- Create, edit and delete users and meetings, giving a reason that is included in the email to the people affected
- Dashboard and reports covering tutor workload, popular time slots, availability use, student engagement, monthly trends and students with adjustments

**Integrations**
- HTML email notifications for bookings, cancellations, reschedules and admin changes, sent through Gmail SMTP with Flask-Mail
- Microsoft Teams meeting links created through a Power Automate flow, with placeholder links used when no flow is configured

## Algorithms and data structures

The NEA rewarded technical complexity, so the app includes these hand-written implementations:

| Component | File | Purpose |
|---|---|---|
| Priority queue (binary heap) | `algorithms.py` | Orders bookings: urgent first, then adjusted, then normal |
| Recursive optimal-slot search | `algorithms.py` | Searches day by day for the highest-scoring free slot |
| Slot scoring heuristic | `algorithms.py` | Scores each slot on how soon it is, the student's preferred hours, the tutor's workload that day and whether it falls in working hours |
| Hash table (separate chaining, polynomial rolling hash) | `hash_table.py` | Login cache mapping email to user ID, with stale entries detected and removed |
| Merge sort | `sorting.py` | Sorts meetings by any attribute |
| Regex validation | `validation.py` | Validates email addresses |

The app also uses several object-oriented design patterns:
- **Inheritance and polymorphism**: an abstract `UserRole` with `StudentRole`, `TutorRole`, `StaffTutorRole` and `AdminRole`, created by a `UserRoleFactory` (`user_roles.py`)
- **Strategy pattern**: `SingleSlotStrategy` and `MultipleSlotStrategy` for creating availability (`availability_manager.py`)
- **Template method**: an abstract `MeetingBooking` with `RegularBooking`, `UrgentBooking` and `AdjustedBooking` (`meeting_manager.py`)

A note on the hash table: a cache hit still loads the user from the database by ID, so it doesn't make login meaningfully faster than looking the user up by email. It's included to demonstrate the data structure, not as a performance optimisation.

## Tech stack

Python · Flask 3 · Flask-SQLAlchemy (SQLite) · Flask-Login · Flask-Mail · Jinja2 · Bootstrap · unittest · Locust

## Getting started

### 1. Clone and install

Tested with Python 3.12 and 3.13.

```bash
git clone https://github.com/sedmoh/Assessment-meeting-scheduler-A-Level-NEA-.git
cd Assessment-meeting-scheduler-A-Level-NEA-
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure (optional)

Create a `.env` file in the project root. Every setting is optional: without email details the app logs emails instead of sending them, and without a Power Automate URL it uses placeholder Teams links.

```env
SECRET_KEY=change-me
FLASK_DEBUG=1          # local development only; leave unset anywhere else
DATABASE_URL=sqlite:///scheduler.db

# Gmail SMTP (use an App Password, not your normal password)
MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEBUG=0

# Power Automate HTTP-trigger flow that creates Teams meetings
POWER_AUTOMATE_FLOW_URL=
```

### 3. Run

```bash
python app.py
```

Then open http://127.0.0.1:5000. The database is created in `instance/` the first time the app runs.

### Create the first admin

The public registration form only allows the **student** and **tutor** roles. Create admin accounts from the command line:

```bash
flask --app app create-admin "Your Name" you@example.com
```

You'll be asked for a password. Admins can then create staff tutor and admin accounts from the admin dashboard. If you register users some other way, run `python init_db.py` to create any missing role profiles.

### Sample data (optional)

```bash
python setup_test_database.py
```

> ⚠️ This script **wipes the existing database**. It then creates 50 students, 25 tutors, 15 staff tutors and 10 admins, along with availability slots and meetings. Every sample account uses the password `test123`, for example `loadtest_admin0@test.com`.

## Testing

```bash
python run_all_tests.py     # runs every test_*.py file with unittest
```

There are 33 tests covering authentication, availability, booking and edge cases. They are isolated from anything real:

- Each test file points `DATABASE_URL` at an in-memory SQLite database before importing the app, so running the tests never touches `instance/scheduler.db`.
- They blank `POWER_AUTOMATE_FLOW_URL` and `MAIL_USERNAME`, so no real Teams meetings are created and no emails are sent, even if your `.env` is filled in.
- Each test starts with an empty login cache, so tests don't depend on each other.

Load testing uses Locust:

```bash
locust -f locustfile.py --host http://127.0.0.1:5000
```

## Project structure

```
├── app.py                    # Flask routes and app setup
├── models.py                 # SQLAlchemy models
├── config.py                 # Settings loaded from .env
├── algorithms.py             # Priority queue, slot scoring, recursive search, limits
├── availability_manager.py   # Strategy pattern for creating slots
├── meeting_manager.py        # Booking types, rescheduling, notes
├── user_roles.py             # Role class hierarchy and factory
├── hash_table.py             # Custom hash table (session cache)
├── sorting.py                # Merge sort
├── validation.py             # Email validation
├── auto_email.py             # Email notifications
├── generate_teams.py         # Power Automate / Teams integration
├── reports_wip.py            # Admin reports
├── init_db.py                # Creates role profiles for registered users
├── setup_test_database.py    # Fills the database with sample data
├── locustfile.py             # Load testing
├── run_all_tests.py          # Test runner
├── test_*.py                 # Unit tests
├── templates/                # Jinja2 pages and email templates
└── static/                   # CSS and images
```

## Post-submission fixes

Problems I found while reviewing the code after submission. Each one has a regression test that fails on the old code and passes on the fix.

| Problem | Fix |
|---|---|
| Anyone could register as an admin or staff tutor by choosing that role on the sign-up form | The server only accepts `student` and `tutor`; the first admin is created with `flask create-admin` |
| Two different but overlapping meetings could be booked with the same tutor: the clash check compared against `"confirmed"` while meetings were saved as `"Confirmed"` | Status values are defined once in `MeetingStatus`, and there is a single overlap check |
| After an admin changed a user's email, the old email still logged in. After a user was deleted, their email could log in to a new account that reused the same ID | Login checks that each cache hit still matches the account, and admin edits and deletes remove the stale entry |
| Login was case-sensitive although emails are stored in lowercase | Login normalises the email before looking it up |
| The registration form had lost its email-format check | Check restored |
| Running the tests deleted the real database, called the live Power Automate flow and could send real emails | Tests configure an in-memory database and disable the integrations before the app is imported |
| Power Automate errors printed the full flow URL, including its secret key | Errors now print only the status code or error type |
| The app always ran with the Werkzeug debugger enabled | Debug mode is only on when `FLASK_DEBUG=1` is set |

## Known limitations

This was a school project, not production software:

- **No CSRF protection.** Forms that change data (including admin delete actions) don't use CSRF tokens, so another website could trick a logged-in user's browser into submitting them. Adding [Flask-WTF](https://flask-wtf.readthedocs.io/)'s `CSRFProtect` would fix this.
- The auto-scheduler uses fixed student time preferences (10:00–16:00) rather than preferences each student sets.
- The Power Automate / Teams integration depends on a personal flow that isn't included in this repository, so other users will get placeholder meeting links.
- SQLite is fine for a demo but would not hold up under many simultaneous users.

## Author

Mohammed Seddik ([@sedmoh](https://github.com/sedmoh)). Originally built for the AQA A-level Computer Science (7517) NEA.
