import os
import secrets

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Signs login sessions and form data
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///scheduler.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Gmail SMTP settings
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False

    # Gmail credentials, read from the environment only
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

    # Sender name shown in recipients' inboxes
    MAIL_DEFAULT_SENDER = ("OU Scheduling System", MAIL_USERNAME)

    # With no email credentials set, emails are logged instead of sent
    MAIL_SUPPRESS_SEND = not (MAIL_USERNAME and MAIL_PASSWORD)

    # Set MAIL_DEBUG=1 in .env to print email details to the console
    MAIL_DEBUG = os.environ.get("MAIL_DEBUG") == "1"

    # Power Automate flow that creates Teams meetings
    POWER_AUTOMATE_FLOW_URL = os.environ.get("POWER_AUTOMATE_FLOW_URL")

    # Use placeholder meeting links when no flow is configured
    USE_PLACEHOLDER_LINKS = not POWER_AUTOMATE_FLOW_URL
