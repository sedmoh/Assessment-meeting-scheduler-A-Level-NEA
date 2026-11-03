import random
from datetime import datetime, timedelta

from locust import HttpUser, between, task


class TutorSchedulingUser(HttpUser):
    #simulates typical user behavior of students and tutors interacting with the scheduling system

    wait_time = between(1, 3)

    def on_start(self):
        self.user_num = random.randint(1000, 9999)
        self.email = f"loadtest_{self.user_num}@open.ac.uk"
        self.password = "LoadTest123!"

        #register user
        self.client.post("/register", data={
            "name": f"Load Test {self.user_num}",
            "email": self.email,
            "password": self.password,
            "role": random.choice(["student", "tutor"])
        })

        #login
        self.client.post("/login", data={
            "email": self.email,
            "password": self.password
        })

    @task(3)
    def view_dashboard(self):
        #view dashboard after login
        self.client.get("/dashboard", name="/dashboard")

    @task(2)
    def view_available_slots(self):
        #view available slots
        self.client.get("/view-availability", name="/view-availability")

    @task(1)
    def create_availability(self):
        #if user is a tutor, create availability slots
        future_date = (datetime.now() + timedelta(days=random.randint(1, 14))).strftime('%Y-%m-%d')

        self.client.post("/create_availability", data={
            "date": future_date,
            "start_time": f"{random.randint(9, 16)}:00",
            "end_time": f"{random.randint(10, 17)}:00",
            "action": "create"
        }, name="/create_availability")


class AdminUser(HttpUser):
    #simulates admin user behavior for managing the system

    wait_time = between(2, 5)

    def on_start(self):
        #login as admin user
        self.client.post("/login", data={
            "email": "admin@open.ac.uk",
            "password": "AdminPass123!"
        })

    @task(2)
    def view_admin_dashboard(self):
        self.client.get("/admin/dashboard", name="/admin/dashboard")

    @task(1)
    def generate_report(self):
        self.client.get("/admin/reports", name="/admin/reports")


class HighVolumeUser(HttpUser):
    #simulates a user performing rapid actions to test system performance under high load

    wait_time = between(0.5, 1.5)

    def on_start(self):
        #create and login user
        self.user_num = random.randint(5000, 9999)
        self.email = f"heavy_{self.user_num}@open.ac.uk"

        self.client.post("/register", data={
            "name": f"Heavy User {self.user_num}",
            "email": self.email,
            "password": "Test123!",
            "role": "student"
        })
        self.client.post("/login", data={
            "email": self.email,
            "password": "Test123!"
        })

    @task(5)
    def rapid_dashboard_refresh(self):
        self.client.get("/dashboard")

    @task(2)
    def view_availability(self):
        self.client.get("/view-availability")


#locust command to run: "locust -f locustfile.py --host=http://127.0.0.1:5000 --users=30 --spawn-rate=5"
