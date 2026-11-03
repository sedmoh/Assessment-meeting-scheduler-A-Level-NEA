from models import db
from sqlalchemy import text


class ReportGenerator:
    # generates statistical and analytical reports using raw SQL queries

    @staticmethod
    def get_tutor_statistics(tutor_id=None, start_date=None, end_date=None):
        query = """
            SELECT
                u.user_id,
                u.name,
                COUNT(m.meeting_id) AS total_meetings,
                AVG(m.duration) AS avg_duration,
                SUM(m.duration) AS total_minutes,
                MAX(m.start_time) AS latest_meeting,
                MIN(m.start_time) AS earliest_meeting,
                SUM(CASE WHEN m.status = 'Confirmed' THEN 1 ELSE 0 END) AS confirmed_count,
                SUM(CASE WHEN m.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_count
            FROM users u
            LEFT JOIN meeting m
                ON u.user_id = m.tutor_id
            WHERE u.role IN ('tutor', 'staff_tutor')
        """

        params = {}

        if tutor_id:
            query += " AND u.user_id = :tutor_id"
            params["tutor_id"] = tutor_id

        if start_date:
            query += " AND (m.start_time >= :start_date OR m.start_time IS NULL)"
            params["start_date"] = start_date

        if end_date:
            query += " AND (m.start_time <= :end_date OR m.start_time IS NULL)"
            params["end_date"] = end_date

        query += " GROUP BY u.user_id, u.name ORDER BY u.name"

        result = db.session.execute(text(query), params)
        return result.fetchall()

    @staticmethod
    def get_busy_tutors(limit=10):
        query = """
            SELECT
                u.user_id,
                u.name,
                u.email,
                COUNT(m.meeting_id) AS meeting_count,
                SUM(m.duration) / 60.0 AS total_hours
            FROM users u
            INNER JOIN meeting m ON u.user_id = m.tutor_id
            WHERE u.role IN ('tutor', 'staff_tutor')
              AND m.status = 'Confirmed'
            GROUP BY u.user_id, u.name, u.email
            ORDER BY meeting_count DESC
            LIMIT :limit
        """

        result = db.session.execute(text(query), {"limit": limit})
        return result.fetchall()

    @staticmethod
    def get_weekly_meeting_distribution():
        query = """
            SELECT
                CAST(strftime('%w', start_time) AS INTEGER) AS day_of_week,
                COUNT(meeting_id) AS meeting_count,
                AVG(duration) AS avg_duration
            FROM meeting
            WHERE status = 'Confirmed'
            GROUP BY day_of_week
            ORDER BY day_of_week
        """

        rows = db.session.execute(text(query)).fetchall()

        day_names = [
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ]

        distribution = []
        for day, count, avg in rows:
            distribution.append(
                {
                    "day": day_names[day],
                    "day_num": day,
                    "meeting_count": count,
                    "avg_duration": round(avg, 2) if avg else 0,
                }
            )

        return distribution

    @staticmethod
    def get_popular_time_slots():
        query = """
            SELECT
                CAST(strftime('%H', start_time) AS INTEGER) AS hour,
                COUNT(meeting_id) AS bookings,
                COUNT(DISTINCT student_id) AS unique_students
            FROM meeting
            WHERE status = 'Confirmed'
            GROUP BY hour
            ORDER BY bookings DESC
        """

        rows = db.session.execute(text(query)).fetchall()

        return [
            {
                "time": f"{hour:02d}:00",
                "bookings": bookings,
                "unique_students": students,
            }
            for hour, bookings, students in rows
        ]

    @staticmethod
    def get_student_engagement_rate():
        query = """
            SELECT
                u.user_id,
                u.name,
                u.email,
                COUNT(m.meeting_id) AS total_bookings,
                SUM(CASE WHEN m.status = 'Confirmed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN m.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled
            FROM users u
            INNER JOIN meeting m ON u.user_id = m.student_id
            WHERE u.role = 'student'
            GROUP BY u.user_id, u.name, u.email
            ORDER BY u.name
        """

        rows = db.session.execute(text(query)).fetchall()

        engagement = []
        for user_id, name, email, total, completed, cancelled in rows:
            rate = (completed / total * 100) if total else 0
            engagement.append(
                {
                    "student_id": user_id,
                    "name": name,
                    "email": email,
                    "total_bookings": total,
                    "completed": completed,
                    "cancelled": cancelled,
                    "engagement_rate": round(rate, 2),
                }
            )

        return engagement

    @staticmethod
    def get_availability_utilisation():
        query = """
            SELECT
                COUNT(availability_id) AS total_slots,
                SUM(CASE WHEN booked = 1 THEN 1 ELSE 0 END) AS booked_slots,
                SUM(CASE WHEN booked = 0 THEN 1 ELSE 0 END) AS available_slots
            FROM availability
        """

        total, booked, available = db.session.execute(text(query)).fetchone()

        utilisation = (booked / total * 100) if total else 0

        return {
            "total_slots": total or 0,
            "booked_slots": booked or 0,
            "available_slots": available or 0,
            "utilisation_rate": round(utilisation, 2),
        }

    @staticmethod
    def get_students_with_adjustments():
        query = """
            SELECT
                u.user_id,
                u.name,
                u.email,
                COUNT(m.meeting_id) AS total_meetings,
                SUM(CASE WHEN m.adjustment_flag = 1 THEN 1 ELSE 0 END) AS adjusted_meetings,
                SUM(CASE WHEN m.adjustment_flag = 1 THEN m.duration ELSE 0 END) AS adjusted_minutes
            FROM users u
            INNER JOIN student s ON u.user_id = s.user_id
            LEFT JOIN meeting m
                ON u.user_id = m.student_id
               AND m.status = 'Confirmed'
            WHERE s.has_adjustment = 1
            GROUP BY u.user_id, u.name, u.email
            ORDER BY u.name
        """

        return db.session.execute(text(query)).fetchall()

    @staticmethod
    def get_meetings_by_month():
        query = """
            SELECT
                CAST(strftime('%Y', start_time) AS INTEGER) AS year,
                CAST(strftime('%m', start_time) AS INTEGER) AS month,
                COUNT(meeting_id) AS meeting_count
            FROM meeting
            WHERE status = 'Confirmed'
            GROUP BY year, month
            ORDER BY year, month
        """

        rows = db.session.execute(text(query)).fetchall()

        month_names = [
            "",
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        return [
            {
                "year": year,
                "month": month,
                "month_name": month_names[month],
                "count": count,
            }
            for year, month, count in rows
        ]

    @staticmethod
    def get_tutor_workload_comparison():
        query = """
            SELECT
                u.user_id,
                u.name,
                COUNT(m.meeting_id) AS total_meetings,
                SUM(m.duration) AS total_minutes
            FROM users u
            INNER JOIN meeting m ON u.user_id = m.tutor_id
            WHERE u.role IN ('tutor', 'staff_tutor')
              AND m.status = 'Confirmed'
            GROUP BY u.user_id, u.name
        """

        rows = db.session.execute(text(query)).fetchall()

        if not rows:
            return []

        avg_meetings = sum(r[2] for r in rows) / len(rows)

        workload = []
        for user_id, name, meetings, minutes in rows:
            deviation = (
                ((meetings - avg_meetings) / avg_meetings * 100) if avg_meetings else 0
            )
            workload.append(
                {
                    "tutor_id": user_id,
                    "name": name,
                    "total_meetings": meetings,
                    "total_hours": round((minutes or 0) / 60, 2),
                    "vs_average": round(deviation, 2),
                }
            )

        workload.sort(key=lambda x: x["total_meetings"], reverse=True)
        return workload
