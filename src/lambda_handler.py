"""AWS Lambda handler for Generac generator monitoring."""
import asyncio
import logging
import sys
from typing import Any

from .config import Config
from .generac_api import GeneracApiClient
from .notifier import Notifier
from .state_manager import StateManager

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add stdout handler for Lambda
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


async def check_generators(config: Config) -> dict[str, Any]:
    """Check generator status and send notifications.

    Args:
        config: Application configuration

    Returns:
        Dictionary with execution results
    """
    state_manager = StateManager(config.dynamodb_table)
    notifier = Notifier(config)

    results = {
        "devices_checked": 0,
        "notifications_sent": 0,
        "errors": [],
    }

    try:
        # Fetch current device data from Generac API
        async with GeneracApiClient(config.session_cookie) as api_client:
            logger.info("Fetching device data from Generac API")
            devices = await api_client.get_device_data()
            logger.info("Found %d devices", len(devices))
            results["devices_checked"] = len(devices)

            # Process each device
            for device_id, item in devices.items():
                try:
                    logger.info("Processing device %s: %s", device_id, item.apparatus.name)

                    # Extract current state
                    current_state = state_manager.extract_state(item)

                    # Get previous state from DynamoDB
                    previous_state = state_manager.get_previous_state(device_id)

                    # Compare states
                    comparison = state_manager.compare_states(previous_state, current_state)

                    # Log changes
                    if comparison["is_new_device"]:
                        logger.info("New device detected: %s", device_id)
                    elif comparison["changes"]:
                        logger.info(
                            "Device %s has %d changes: %s",
                            device_id,
                            len(comparison["changes"]),
                            list(comparison["changes"].keys()),
                        )
                    else:
                        logger.debug("No changes for device %s", device_id)

                    # Send notifications if needed
                    if comparison["is_new_device"] or comparison["changes"]:
                        await notifier.process_changes(
                            device_id,
                            current_state,
                            comparison["changes"],
                            comparison["is_new_device"],
                        )
                        results["notifications_sent"] += 1

                    # Save current state
                    state_manager.save_state(device_id, current_state)

                except Exception as e:
                    error_msg = f"Error processing device {device_id}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    results["errors"].append(error_msg)

    except Exception as e:
        error_msg = f"Error fetching device data: {str(e)}"
        logger.error(error_msg, exc_info=True)
        results["errors"].append(error_msg)

    return results


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler function.

    Args:
        event: Lambda event data
        context: Lambda context

    Returns:
        Response dictionary with statusCode and body
    """
    logger.info("Starting Generac generator check")
    logger.info("Event: %s", event)

    try:
        # Load configuration from environment
        config = Config.from_env()
        logger.info("Configuration loaded successfully")

        # Run async check
        results = asyncio.run(check_generators(config))

        logger.info(
            "Check complete. Devices: %d, Notifications: %d, Errors: %d",
            results["devices_checked"],
            results["notifications_sent"],
            len(results["errors"]),
        )

        return {
            "statusCode": 200,
            "body": {
                "message": "Generator check completed successfully",
                "results": results,
            },
        }

    except ValueError as e:
        # Configuration error
        logger.error("Configuration error: %s", e)
        return {
            "statusCode": 500,
            "body": {
                "message": "Configuration error",
                "error": str(e),
            },
        }

    except Exception as e:
        # Unexpected error
        logger.error("Unexpected error: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "body": {
                "message": "Internal error",
                "error": str(e),
            },
        }
