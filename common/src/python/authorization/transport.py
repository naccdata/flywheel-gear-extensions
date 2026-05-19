"""HTTP transport protocol definitions for the Authorization Client."""

from typing import Protocol


class HttpResponse(Protocol):
    """Minimal response interface returned by transport."""

    @property
    def status_code(self) -> int:
        """HTTP status code of the response."""
        ...

    @property
    def body(self) -> bytes:
        """Raw response body as bytes."""
        ...


class HttpTransport(Protocol):
    """Abstract HTTP transport for the Authorization API.

    Implementations handle the details of sending HTTP requests (e.g.,
    SigV4 signing, connection pooling) while the client operates against
    this protocol for testability.
    """

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> HttpResponse:
        """Send an HTTP request and return the response.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: Request path relative to the API base URL.
            body: Optional request body as bytes.
            query_params: Optional query string parameters.

        Returns:
            An HttpResponse with status_code and body.
        """
        ...
