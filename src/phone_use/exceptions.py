from __future__ import annotations

from typing import Any


class PhoneUseError(Exception):
    """Base exception for phone-use."""


class PhoneUseNetworkError(PhoneUseError):
    """Raised when the automation API cannot be reached."""


class PhoneUseAPIError(PhoneUseError):
    """Raised when the automation API returns an error response."""

    def __init__(
        self,
        status_code: int,
        message: str,
        response: Any = None,
    ) -> None:
        super().__init__(f"API request failed ({status_code}): {message}")
        self.status_code = status_code
        self.message = message
        self.response = response
