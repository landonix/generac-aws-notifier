"""DynamoDB state manager for tracking generator state changes."""
import json
import logging
from datetime import datetime
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class StateManager:
    """Manages generator state persistence in DynamoDB."""

    def __init__(self, table_name: str):
        """Initialize the state manager.

        Args:
            table_name: Name of the DynamoDB table
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(table_name)

    def get_previous_state(self, device_id: str) -> Optional[dict[str, Any]]:
        """Get the previous state for a device.

        Args:
            device_id: The device ID

        Returns:
            Previous state dictionary or None if not found
        """
        try:
            response = self.table.get_item(Key={"device_id": device_id})
            if "Item" in response:
                item = response["Item"]
                # Parse the state JSON if it's stored as a string
                if "state" in item and isinstance(item["state"], str):
                    item["state"] = json.loads(item["state"])
                return item
            return None
        except ClientError as e:
            logger.error("Error getting previous state for %s: %s", device_id, e)
            return None

    def save_state(self, device_id: str, state: dict[str, Any]) -> bool:
        """Save the current state for a device.

        Args:
            device_id: The device ID
            state: Current state dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            item = {
                "device_id": device_id,
                "state": json.dumps(state, default=str),  # Serialize complex objects
                "last_updated": datetime.utcnow().isoformat(),
            }
            self.table.put_item(Item=item)
            return True
        except ClientError as e:
            logger.error("Error saving state for %s: %s", device_id, e)
            return False

    def extract_state(self, item: Any) -> dict[str, Any]:
        """Extract relevant state from an Item object.

        Args:
            item: Item object containing apparatus and apparatusDetail

        Returns:
            Dictionary with relevant state information
        """
        from models import Item
        from config import DEVICE_TYPE_GENERATOR

        if not isinstance(item, Item):
            return {}

        state = {
            "device_type": item.apparatus.type,
            "name": item.apparatus.name,
            "serial_number": item.apparatus.serialNumber,
            "is_connected": item.apparatusDetail.isConnected,
            "is_connecting": item.apparatusDetail.isConnecting,
            "has_maintenance_alert": item.apparatusDetail.hasMaintenanceAlert,
            "show_warning": item.apparatusDetail.showWarning,
            "status_label": item.apparatusDetail.statusLabel,
            "status_text": item.apparatusDetail.statusText,
            "apparatus_status": item.apparatusDetail.apparatusStatus,
            "last_seen": item.apparatusDetail.lastSeen,
        }

        # Add generator-specific fields
        if item.apparatus.type == DEVICE_TYPE_GENERATOR:
            # Extract battery voltage (property type 70)
            battery_voltage = None
            if item.apparatusDetail.properties:
                for prop in item.apparatusDetail.properties:
                    if prop.type == 70:
                        battery_voltage = prop.value
                        break
            state["battery_voltage"] = battery_voltage

        return state

    def compare_states(
        self, previous: Optional[dict[str, Any]], current: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare two states and identify changes.

        Args:
            previous: Previous state dictionary
            current: Current state dictionary

        Returns:
            Dictionary with change information
        """
        if previous is None:
            return {
                "is_new_device": True,
                "changes": {},
            }

        # Parse state if it's stored as JSON string
        if isinstance(previous.get("state"), str):
            previous_state = json.loads(previous["state"])
        else:
            previous_state = previous.get("state", {})

        changes = {}
        for key in current:
            prev_value = previous_state.get(key)
            curr_value = current[key]

            if prev_value != curr_value:
                changes[key] = {
                    "previous": prev_value,
                    "current": curr_value,
                }

        return {
            "is_new_device": False,
            "changes": changes,
        }
