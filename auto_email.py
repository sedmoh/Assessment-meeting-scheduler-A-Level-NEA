from flask import render_template
from flask_mail import Mail, Message

mail = Mail()


def send_booking_confirmation(meeting, student, tutor, app, teams_link):
    # sends a booking confirmation email to both the student and tutor.

    with app.app_context():
        # prepare meeting details
        meeting_date = meeting.start_time.strftime("%B %d, %Y")
        meeting_start_time = meeting.start_time.strftime("%H:%M")
        meeting_end_time = meeting.end_time.strftime("%H:%M")

        student_html = render_template(
            "emails/booking_confirmation.html",
            recipient_name=student.name,
            student_name=student.name,
            tutor_name=tutor.name,
            meeting_date=meeting_date,
            meeting_start_time=meeting_start_time,
            meeting_end_time=meeting_end_time,
            meeting_duration=meeting.duration,
            meeting_status=meeting.status,
            meeting_notes=meeting.public_notes or "",
            teams_link=teams_link,
        )

        student_msg = Message(
            subject="Meeting Confirmation - OU Scheduling System",
            sender=app.config["MAIL_DEFAULT_SENDER"],
            recipients=[student.email],
            html=student_html,
        )

        tutor_html = render_template(
            "emails/booking_confirmation.html",
            recipient_name=tutor.name,
            student_name=student.name,
            tutor_name=tutor.name,
            meeting_date=meeting_date,
            meeting_start_time=meeting_start_time,
            meeting_end_time=meeting_end_time,
            meeting_duration=meeting.duration,
            meeting_status=meeting.status,
            meeting_notes=meeting.public_notes or "",
            teams_link=teams_link,
        )

        tutor_msg = Message(
            subject="Meeting Confirmation - OU Scheduling System",
            sender=app.config["MAIL_DEFAULT_SENDER"],
            recipients=[tutor.email],
            html=tutor_html,
        )

        try:
            mail.send(student_msg)
            mail.send(tutor_msg)
            return True
        except Exception as e:
            print(f"Error sending booking confirmation email: {str(e)}")
            return False


def send_cancellation_email(meeting, student, tutor, app):
    # sends a cancellation email to both the student and tutor.

    with app.app_context():
        meeting_date = meeting.start_time.strftime("%B %d, %Y")
        meeting_start_time = meeting.start_time.strftime("%H:%M")
        meeting_end_time = meeting.end_time.strftime("%H:%M")

        for recipient in [student, tutor]:
            html = render_template(
                "emails/meeting_cancellation.html",
                recipient_name=recipient.name,
                student_name=student.name,
                tutor_name=tutor.name,
                meeting_date=meeting_date,
                meeting_start_time=meeting_start_time,
                meeting_end_time=meeting_end_time,
            )

            msg = Message(
                subject="Meeting Cancelled - OU Scheduling System",
                sender=app.config["MAIL_DEFAULT_SENDER"],
                recipients=[recipient.email],
                html=html,
            )

            try:
                mail.send(msg)
            except Exception as e:
                print(
                    f"Error sending cancellation email to {recipient.email}: {str(e)}"
                )


def send_reschedule_email(meeting, student, tutor, old_time, app):
    # sends a reschedule notification email to both the student and tutor.

    with app.app_context():
        old_date = old_time.strftime("%B %d, %Y")
        old_time_str = old_time.strftime("%H:%M")
        new_date = meeting.start_time.strftime("%B %d, %Y")
        new_time = meeting.start_time.strftime("%H:%M")

        for recipient in [student, tutor]:
            html = render_template(
                "emails/meeting_reschedule.html",
                recipient_name=recipient.name,
                student_name=student.name,
                tutor_name=tutor.name,
                old_date=old_date,
                old_time=old_time_str,
                new_date=new_date,
                new_time=new_time,
                meeting_duration=meeting.duration,
            )

            msg = Message(
                subject="Meeting Rescheduled - OU Scheduling System",
                sender=app.config["MAIL_DEFAULT_SENDER"],
                recipients=[recipient.email],
                html=html,
            )

            try:
                mail.send(msg)
            except Exception as e:
                print(f"Error sending reschedule email to {recipient.email}: {str(e)}")

def send_admin_created_meeting_email(meeting, student, tutor, admin, admin_reason, app, teams_link=None):
    #send notification when admin creates a meeting

    with app.app_context():
        meeting_date = meeting.start_time.strftime("%B %d, %Y")
        meeting_start_time = meeting.start_time.strftime("%H:%M")
        meeting_end_time = meeting.end_time.strftime("%H:%M")

        #email to student
        student_html = render_template(
            "emails/admin_created_meeting.html",
            recipient_name=student.name,
            student_name=student.name,
            tutor_name=tutor.name,
            admin_name=admin.name,
            admin_reason=admin_reason,
            meeting_date=meeting_date,
            meeting_start_time=meeting_start_time,
            meeting_end_time=meeting_end_time,
            meeting_duration=meeting.duration,
            meeting_status=meeting.status,
            meeting_notes=meeting.public_notes or "",
            teams_link=teams_link,
        )

        student_msg = Message(
            subject="Meeting Scheduled by Administrator - OU Scheduling System",
            sender=app.config["MAIL_DEFAULT_SENDER"],
            recipients=[student.email],
            html=student_html,
        )

        #email to tutor
        tutor_html = render_template(
            "emails/admin_created_meeting.html",
            recipient_name=tutor.name,
            student_name=student.name,
            tutor_name=tutor.name,
            admin_name=admin.name,
            admin_reason=admin_reason,
            meeting_date=meeting_date,
            meeting_start_time=meeting_start_time,
            meeting_end_time=meeting_end_time,
            meeting_duration=meeting.duration,
            meeting_status=meeting.status,
            meeting_notes=meeting.public_notes or "",
            teams_link=teams_link,
        )

        tutor_msg = Message(
            subject="Meeting Scheduled by Administrator - OU Scheduling System",
            sender=app.config["MAIL_DEFAULT_SENDER"],
            recipients=[tutor.email],
            html=tutor_html,
        )

        try:
            mail.send(student_msg)
            mail.send(tutor_msg)
            return True
        except Exception as e:
            print(f"Error sending admin created meeting email: {str(e)}")
            return False


def send_admin_modified_meeting_email(meeting, student, tutor, admin, admin_reason, old_details, app):
    #send notification when admin modifies a meeting
    with app.app_context():
        new_date = meeting.start_time.strftime("%B %d, %Y")
        new_start_time = meeting.start_time.strftime("%H:%M")
        new_end_time = meeting.end_time.strftime("%H:%M")

        for recipient in [student, tutor]:
            html = render_template(
                "emails/admin_modified_meeting.html",
                recipient_name=recipient.name,
                student_name=student.name,
                tutor_name=tutor.name,
                admin_name=admin.name,
                admin_reason=admin_reason,
                old_date=old_details['date'],
                old_start_time=old_details['start_time'],
                old_end_time=old_details['end_time'],
                old_duration=old_details['duration'],
                new_date=new_date,
                new_start_time=new_start_time,
                new_end_time=new_end_time,
                new_duration=meeting.duration,
                meeting_link=meeting.meeting_link,
            )

            msg = Message(
                subject="Meeting Modified by Administrator - OU Scheduling System",
                sender=app.config["MAIL_DEFAULT_SENDER"],
                recipients=[recipient.email],
                html=html,
            )

            try:
                mail.send(msg)
            except Exception as e:
                print(f"Error sending admin modified email to {recipient.email}: {str(e)}")


def send_admin_deleted_meeting_email(meeting, student, tutor, admin, admin_reason, app):
    #send notification when admin deletes a meeting
    with app.app_context():
        meeting_date = meeting.start_time.strftime("%B %d, %Y")
        meeting_start_time = meeting.start_time.strftime("%H:%M")
        meeting_end_time = meeting.end_time.strftime("%H:%M")

        for recipient in [student, tutor]:
            html = render_template(
                "emails/admin_deleted_meeting.html",
                recipient_name=recipient.name,
                student_name=student.name,
                tutor_name=tutor.name,
                admin_name=admin.name,
                admin_reason=admin_reason,
                meeting_date=meeting_date,
                meeting_start_time=meeting_start_time,
                meeting_end_time=meeting_end_time,
                meeting_duration=meeting.duration,
            )

            msg = Message(
                subject="Meeting Cancelled by Administrator - OU Scheduling System",
                sender=app.config["MAIL_DEFAULT_SENDER"],
                recipients=[recipient.email],
                html=html,
            )

            try:
                mail.send(msg)
            except Exception as e:
                print(f"Error sending admin deleted email to {recipient.email}: {str(e)}")
