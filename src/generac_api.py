"""Generac API Client for AWS Lambda."""
import json
import logging
from typing import Optional

import aiohttp
from dacite import from_dict

from .models import Apparatus, ApparatusDetail, Item

API_BASE = "https://app.mobilelinkgen.com/api"
TIMEOUT = 10

# Device types
DEVICE_TYPE_GENERATOR = 0
DEVICE_TYPE_PROPANE_MONITOR = 2
ALLOWED_DEVICES = [DEVICE_TYPE_GENERATOR, DEVICE_TYPE_PROPANE_MONITOR]

logger = logging.getLogger(__name__)


class InvalidCredentialsException(Exception):
    """Raised when authentication fails."""
    pass


class SessionExpiredException(Exception):
    """Raised when the session has expired."""
    pass


class GeneracApiClient:
    """Client for interacting with the Generac MobileLink API."""

    def __init__(self, session_cookie: str) -> None:
        """Initialize the API client.

        Args:
            session_cookie: The session cookie obtained from logging into
                          https://app.mobilelinkgen.com/
        """
        self._session_cookie = session_cookie
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()

    async def get_device_data(self) -> dict[str, Item]:
        """Fetch all device data from the Generac API.

        Returns:
            Dictionary mapping device IDs to Item objects containing
            apparatus and detail information.

        Raises:
            InvalidCredentialsException: If session cookie is invalid
            SessionExpiredException: If session has expired
        """
        if not self._session_cookie:
            logger.error("No session cookie provided, cannot login")
            raise InvalidCredentialsException("No session cookie provided")

        # Get list of all apparatuses
        apparatuses = await self._get_endpoint("/v2/Apparatus/list")
        if apparatuses is None:
            logger.debug("Could not decode apparatuses response")
            return {}
        if not isinstance(apparatuses, list):
            logger.error("Expected list from /v2/Apparatus/list got %s", type(apparatuses))
            return {}

        data: dict[str, Item] = {}
        for apparatus_data in apparatuses:
            apparatus = from_dict(Apparatus, apparatus_data)
            if apparatus.type not in ALLOWED_DEVICES:
                logger.debug(
                    "Unknown apparatus type %s %s", apparatus.type, apparatus.name
                )
                continue

            # Get detailed information for this apparatus
            detail_json = await self._get_endpoint(
                f"/v1/Apparatus/details/{apparatus.apparatusId}"
            )
            if detail_json is None:
                logger.debug(
                    "Could not decode response from /v1/Apparatus/details/%s",
                    apparatus.apparatusId
                )
                continue

            detail = from_dict(ApparatusDetail, detail_json)
            data[str(apparatus.apparatusId)] = Item(apparatus, detail)

        return data

    async def _get_endpoint(self, endpoint: str):
        """Make a GET request to the Generac API.

        Args:
            endpoint: API endpoint path (e.g., "/v2/Apparatus/list")

        Returns:
            JSON response data or None if no content

        Raises:
            SessionExpiredException: If API returns non-200 status
        """
        if not self._session:
            raise RuntimeError("Session not initialized. Use 'async with' context manager.")

        try:
            headers = {**self._headers, "Cookie": self._session_cookie}

            url = API_BASE + endpoint
            async with self._session.get(url, headers=headers, timeout=TIMEOUT) as response:
                if response.status == 204:
                    # No data
                    return None

                if response.status != 200:
                    raise SessionExpiredException(
                        f"API returned status code: {response.status}"
                    )

                data = await response.json()
                logger.debug("GET %s: %s", endpoint, json.dumps(data))
                return data

        except SessionExpiredException:
            raise
        except Exception as ex:
            logger.exception("Error calling API endpoint %s", endpoint)
            raise IOError(f"Failed to call {endpoint}") from ex
