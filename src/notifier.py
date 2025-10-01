"""Notification handler for generator status changes."""
import logging
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from config import Config, GENERATOR_STATUS_MAP, DEVICE_NAME_MAP

logger = logging.getLogger(__name__)


class Notifier:
    """Handles sending notifications via SNS and SES."""

    def __init__(self, config: Config):
        """Initialize the notifier.

        Args:
            config: Application configuration
        """
        self.config = config
        self.sns = boto3.client("sns") if config.sns_topic_arn else None
        self.ses = boto3.client("ses") if config.ses_from_email and config.ses_to_emails else None

    def should_notify(
        self, change_type: str, changes: dict[str, Any], current_state: dict[str, Any]
    ) -> bool:
        """Determine if a notification should be sent based on change type.

        Args:
            change_type: Type of change detected
            changes: Dictionary of changes
            current_state: Current device state

        Returns:
            True if notification should be sent
        """
        if change_type == "status_change" and self.config.notify_on_status_change:
            return "apparatus_status" in changes

        if change_type == "connectivity" and self.config.notify_on_connectivity_change:
            return "is_connected" in changes or "is_connecting" in changes

        if change_type == "maintenance" and self.config.notify_on_maintenance_alert:
            return changes.get("has_maintenance_alert", {}).get("current") is True

        if change_type == "warning" and self.config.notify_on_warning:
            return changes.get("show_warning", {}).get("current") is True

        if change_type == "low_battery" and self.config.notify_on_low_battery:
            battery_voltage = current_state.get("battery_voltage")
            if battery_voltage:
                try:
                    voltage = float(battery_voltage)
                    return voltage < self.config.low_battery_threshold
                except (ValueError, TypeError):
                    pass

        return False

    def build_message(
        self,
        device_id: str,
        current_state: dict[str, Any],
        changes: dict[str, Any],
        is_new_device: bool,
    ) -> dict[str, str]:
        """Build notification message.

        Args:
            device_id: Device ID
            current_state: Current device state
            changes: Dictionary of changes
            is_new_device: Whether this is a newly discovered device

        Returns:
            Dictionary with 'subject' and 'body' keys
        """
        device_name = current_state.get("name", "Unknown Device")
        device_type = DEVICE_NAME_MAP.get(current_state.get("device_type"), "Unknown")
        serial = current_state.get("serial_number", device_id)

        if is_new_device:
            subject = f"New {device_type} Detected: {device_name}"
            body = f"""A new {device_type} has been detected in your Generac account.

Device: {device_name}
Serial Number: {serial}
Current Status: {self._format_status(current_state)}

This is the first time this device has been seen by the monitoring system.
"""
        else:
            subject = f"Generator Alert: {device_name}"
            body = f"""Your {device_type} has reported status changes.

Device: {device_name}
Serial Number: {serial}

Changes:
{self._format_changes(changes, current_state)}

Current Status: {self._format_status(current_state)}
"""

        body += f"\nTimestamp: {datetime.utcnow().isoformat()}Z"
        return {"subject": subject, "body": body}

    def _format_status(self, state: dict[str, Any]) -> str:
        """Format current status into human-readable text."""
        status_parts = []

        # Main status
        apparatus_status = state.get("apparatus_status")
        if apparatus_status:
            status_text = GENERATOR_STATUS_MAP.get(apparatus_status, "Unknown")
            status_parts.append(f"Status: {status_text}")
        elif state.get("status_label"):
            status_parts.append(f"Status: {state['status_label']}")

        # Connection status
        if state.get("is_connected"):
            status_parts.append("Connected: Yes")
        elif state.get("is_connecting"):
            status_parts.append("Connected: Connecting...")
        else:
            status_parts.append("Connected: No")

        # Alerts
        if state.get("has_maintenance_alert"):
            status_parts.append("⚠️  Maintenance Alert Active")
        if state.get("show_warning"):
            status_parts.append("⚠️  Warning Active")

        # Battery voltage (for generators)
        battery_voltage = state.get("battery_voltage")
        if battery_voltage:
            try:
                voltage = float(battery_voltage)
                status_parts.append(f"Battery: {voltage:.1f}V")
                if voltage < self.config.low_battery_threshold:
                    status_parts.append("🔋 Low Battery Warning")
            except (ValueError, TypeError):
                pass

        return "\n".join(status_parts)

    def _format_changes(self, changes: dict[str, Any], current_state: dict[str, Any]) -> str:
        """Format changes into human-readable text."""
        change_lines = []

        for key, change in changes.items():
            prev = change.get("previous")
            curr = change.get("current")

            if key == "apparatus_status":
                prev_text = GENERATOR_STATUS_MAP.get(prev, str(prev))
                curr_text = GENERATOR_STATUS_MAP.get(curr, str(curr))
                change_lines.append(f"  • Status changed: {prev_text} → {curr_text}")
            elif key == "is_connected":
                change_lines.append(f"  • Connection: {'Disconnected' if not prev else 'Connected'} → {'Connected' if curr else 'Disconnected'}")
            elif key == "has_maintenance_alert":
                if curr:
                    change_lines.append("  • ⚠️  Maintenance alert triggered")
                else:
                    change_lines.append("  • ✓ Maintenance alert cleared")
            elif key == "show_warning":
                if curr:
                    change_lines.append("  • ⚠️  Warning triggered")
                else:
                    change_lines.append("  • ✓ Warning cleared")
            elif key == "battery_voltage":
                try:
                    prev_v = float(prev) if prev else 0
                    curr_v = float(curr) if curr else 0
                    change_lines.append(f"  • Battery voltage: {prev_v:.1f}V → {curr_v:.1f}V")
                except (ValueError, TypeError):
                    change_lines.append(f"  • Battery voltage changed")
            else:
                change_lines.append(f"  • {key.replace('_', ' ').title()}: {prev} → {curr}")

        return "\n".join(change_lines) if change_lines else "No significant changes"

    async def send_notification(self, subject: str, body: str) -> bool:
        """Send notification via configured channels.

        Args:
            subject: Notification subject
            body: Notification body

        Returns:
            True if at least one notification was sent successfully
        """
        success = False

        # Send via SNS
        if self.sns and self.config.sns_topic_arn:
            try:
                self.sns.publish(
                    TopicArn=self.config.sns_topic_arn,
                    Subject=subject,
                    Message=body,
                )
                logger.info("Sent SNS notification: %s", subject)
                success = True
            except ClientError as e:
                logger.error("Failed to send SNS notification: %s", e)

        # Send via SES
        if self.ses and self.config.ses_from_email and self.config.ses_to_emails:
            try:
                self.ses.send_email(
                    Source=self.config.ses_from_email,
                    Destination={"ToAddresses": self.config.ses_to_emails},
                    Message={
                        "Subject": {"Data": subject},
                        "Body": {"Text": {"Data": body}},
                    },
                )
                logger.info("Sent SES notification to %s: %s", self.config.ses_to_emails, subject)
                success = True
            except ClientError as e:
                logger.error("Failed to send SES notification: %s", e)

        return success

    async def process_changes(
        self,
        device_id: str,
        current_state: dict[str, Any],
        changes: dict[str, Any],
        is_new_device: bool,
    ) -> None:
        """Process changes and send notifications if needed.

        Args:
            device_id: Device ID
            current_state: Current device state
            changes: Dictionary of changes
            is_new_device: Whether this is a newly discovered device
        """
        # Always notify for new devices
        if is_new_device:
            message = self.build_message(device_id, current_state, changes, is_new_device)
            await self.send_notification(message["subject"], message["body"])
            return

        # Check if we should notify based on changes
        should_send = False

        if self.should_notify("status_change", changes, current_state):
            should_send = True
        elif self.should_notify("connectivity", changes, current_state):
            should_send = True
        elif self.should_notify("maintenance", changes, current_state):
            should_send = True
        elif self.should_notify("warning", changes, current_state):
            should_send = True
        elif self.should_notify("low_battery", changes, current_state):
            should_send = True

        if should_send:
            message = self.build_message(device_id, current_state, changes, is_new_device)
            await self.send_notification(message["subject"], message["body"])
            logger.info("Sent notification for device %s", device_id)
        else:
            logger.debug("No notification needed for device %s", device_id)
