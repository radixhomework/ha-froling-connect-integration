"""Exceptions for the Fröling Connect client."""


class FroelingConnectError(Exception):
    """Base exception for Fröling Connect client errors."""


class AuthenticationError(FroelingConnectError):
    """Raised when login fails or a session cannot be restored."""


class RateLimitError(FroelingConnectError):
    """Raised when the cloud service responds with HTTP 429."""

    def __init__(self, retry_after: float | None = None) -> None:
        """Initialize with the optional Retry-After hint in seconds."""
        super().__init__(f"Rate limited by Fröling Connect (retry_after={retry_after})")
        self.retry_after = retry_after


class NetworkError(FroelingConnectError):
    """Raised on unexpected HTTP status codes or connection problems."""


class ParsingError(FroelingConnectError):
    """Raised when a response cannot be parsed as expected JSON."""
