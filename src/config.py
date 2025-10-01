"""Configuration module for Generac AWS Notifier."""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Application configuration."""

    # Generac API
    session_cookie: str

    # AWS Resources
    dynamodb_table: str
    sns_topic_arn: Optional[str] = None
    ses_from_email: Optional[str] = None
    ses_to_emails: Optional[list[str]] = None

    # Notification settings
    notify_on_status_change: bool = True
    notify_on_connectivity_change: bool = True
    notify_on_maintenance_alert: bool = True
    notify_on_warning: bool = True
    notify_on_low_battery: bool = True
    low_battery_threshold: float = 12.0  # volts

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables.

        Required environment variables:
            GENERAC_SESSION_COOKIE: Session cookie from Generac MobileLink
            DYNAMODB_TABLE: Name of DynamoDB table for state storage

        Optional environment variables:
            SNS_TOPIC_ARN: ARN of SNS topic for notifications
            SES_FROM_EMAIL: From email address for SES notifications
            SES_TO_EMAILS: Comma-separated list of recipient emails
            NOTIFY_ON_STATUS_CHANGE: Enable status change notifications (default: true)
            NOTIFY_ON_CONNECTIVITY_CHANGE: Enable connectivity notifications (default: true)
            NOTIFY_ON_MAINTENANCE_ALERT: Enable maintenance notifications (default: true)
            NOTIFY_ON_WARNING: Enable warning notifications (default: true)
            NOTIFY_ON_LOW_BATTERY: Enable low battery notifications (default: true)
            LOW_BATTERY_THRESHOLD: Battery voltage threshold (default: 12.0)
        """
        session_cookie = os.environ.get("GENERAC_SESSION_COOKIE")
        if not session_cookie:
            raise ValueError("GENERAC_SESSION_COOKIE environment variable is required")

        dynamodb_table = os.environ.get("DYNAMODB_TABLE")
        if not dynamodb_table:
            raise ValueError("DYNAMODB_TABLE environment variable is required")

        ses_to_emails_str = os.environ.get("SES_TO_EMAILS")
        ses_to_emails = None
        if ses_to_emails_str:
            ses_to_emails = [email.strip() for email in ses_to_emails_str.split(",")]

        return cls(
            session_cookie=session_cookie,
            dynamodb_table=dynamodb_table,
            sns_topic_arn=os.environ.get("SNS_TOPIC_ARN"),
            ses_from_email=os.environ.get("SES_FROM_EMAIL"),
            ses_to_emails=ses_to_emails,
            notify_on_status_change=os.environ.get("NOTIFY_ON_STATUS_CHANGE", "true").lower() == "true",
            notify_on_connectivity_change=os.environ.get("NOTIFY_ON_CONNECTIVITY_CHANGE", "true").lower() == "true",
            notify_on_maintenance_alert=os.environ.get("NOTIFY_ON_MAINTENANCE_ALERT", "true").lower() == "true",
            notify_on_warning=os.environ.get("NOTIFY_ON_WARNING", "true").lower() == "true",
            notify_on_low_battery=os.environ.get("NOTIFY_ON_LOW_BATTERY", "true").lower() == "true",
            low_battery_threshold=float(os.environ.get("LOW_BATTERY_THRESHOLD", "12.0")),
        )


# Device type constants
DEVICE_TYPE_GENERATOR = 0
DEVICE_TYPE_PROPANE_MONITOR = 2
DEVICE_NAME_MAP = {
    DEVICE_TYPE_GENERATOR: "Generator",
    DEVICE_TYPE_PROPANE_MONITOR: "Propane Tank Monitor",
}

# Generator status mapping
GENERATOR_STATUS_MAP = {
    1: "Ready",
    2: "Running",
    3: "Exercising",
    4: "Warning",
    5: "Stopped",
    6: "Communication Issue",
    7: "Unknown",
    8: "Online",
    9: "Offline",
}
