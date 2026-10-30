import requests
import json


class PowerAutomateTeamsService:
    # service to create Teams meetings via Power Automate

    def __init__(self, flow_url):
        # initialise Power Automate service
        self.flow_url = flow_url

    def create_teams_meeting(
        self,
        subject,
        start_time,
        end_time,
        student_email,
        tutor_email,
        student_name,
        tutor_name,
    ):
        # create a Teams meeting via Power Automate
        # prepare data for Power Automate
        meeting_data = {
            "subject": subject,
            "startDateTime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "endDateTime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "studentEmail": student_email,
            "tutorEmail": tutor_email,
            "studentName": student_name,
            "tutorName": tutor_name,
            "timeZone": "GMT Standard Time",
        }

        try:
            response = requests.post(
                self.flow_url,
                json=meeting_data,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )

            response.raise_for_status()
            result = response.json()

            join_url = (
                result.get("joinUrl")
                or result.get("joinWebUrl")
                or result.get("onlineMeetingUrl")
            )

            if join_url:
                return {
                    "join_url": join_url,
                    "meeting_id": result.get("id"),
                    "success": True,
                }
            else:
                print("Response received but no join URL found")
                return None

        except requests.exceptions.Timeout:
            print("Request timed out after 30 seconds")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e}")
            print(f"Status Code: {e.response.status_code}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {str(e)}")
            return None
        except json.JSONDecodeError:
            print("Invalid JSON response from Power Automate")
            return None
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return None

    def test_connection(self):
        # test if the Power Automate flow is reachable
        try:
            test_data = {"test": True}
            response = requests.post(
                self.flow_url,
                json=test_data,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

            if response.status_code == 200:
                print("Power Automate flow is reachable")
                return True
            else:
                print(f"Flow responded with status: {response.status_code}")
                return False
        except Exception as e:
            print(f"Cannot reach Power Automate flow: {str(e)}")
            return False


def init_power_automate_service(app):
    # initialise Power Automate service from Flask config
    flow_url = app.config.get("POWER_AUTOMATE_FLOW_URL")

    if flow_url and len(flow_url) > 50:
        print("Initialising Power Automate Teams service...")
        service = PowerAutomateTeamsService(flow_url)

        if service.test_connection():
            print("Power Automate service ready")
            return service
        else:
            print("Power Automate service initialised but connection test failed")
            return service
    else:
        print("Power Automate Flow URL not configured")
        return None
