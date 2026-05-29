"""Exception hierarchy for the authorization client library."""


class AuthorizationClientError(Exception):
    """Base exception for authorization client errors."""


class ConfigurationError(AuthorizationClientError):
    """Raised when the client cannot be configured (e.g., missing base URL)."""


class ValidationError(AuthorizationClientError):
    """Raised when the API returns 400 (validation error)."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ServiceUnavailableError(AuthorizationClientError):
    """Raised when retries are exhausted on 503."""


class NotFoundError(AuthorizationClientError):
    """Raised when the API returns 404 (resource not found)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnexpectedError(AuthorizationClientError):
    """Raised on unexpected HTTP errors (non-retriable 4xx/5xx)."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class ParseError(AuthorizationClientError):
    """Raised when a response body cannot be parsed into the expected model."""

    def __init__(self, message: str, raw_content: bytes) -> None:
        super().__init__(message)
        self.message = message
        self.raw_content = raw_content
