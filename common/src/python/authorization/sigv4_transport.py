"""SigV4-signed HTTP transport for the Authorization API."""

import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Response:
    """Concrete HTTP response returned by SigV4Transport."""

    status_code: int
    body: bytes


class SigV4Transport:
    """HTTP transport that signs requests with AWS SigV4.

    Uses botocore's standard credential chain (environment variables,
    shared credentials file, IAM role, etc.) to sign requests against
    the ``execute-api`` service.

    This class satisfies the ``HttpTransport`` protocol via structural
    subtyping — no explicit inheritance is needed.
    """

    def __init__(
        self,
        base_url: str,
        region: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the SigV4 transport.

        Args:
            base_url: The base URL of the Authorization API
                (e.g., ``https://api.example.com/v1``).
            region: AWS region for signing. If not provided, the region
                is resolved from the botocore session (environment or
                config file).
            timeout: Request timeout in seconds. Defaults to 30 seconds.
        """
        self._base_url = base_url.rstrip("/")
        self._session = Session()
        self._region = region or self._session.get_config_variable("region")
        self._credentials = self._session.get_credentials()
        self._timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> _Response:
        """Send a SigV4-signed HTTP request and return the response.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: Request path relative to the base URL.
            body: Optional request body as bytes.
            query_params: Optional query string parameters.

        Returns:
            An object with ``status_code`` and ``body`` attributes.
        """
        url = self._build_url(path, query_params)

        headers: dict[str, str] = {}
        if body is not None:
            headers["Content-Type"] = "application/json"

        # Create and sign the AWS request
        aws_request = AWSRequest(
            method=method.upper(),
            url=url,
            data=body,
            headers=headers,
        )
        SigV4Auth(self._credentials, "execute-api", self._region).add_auth(aws_request)

        # Build urllib request with signed headers
        req = urllib.request.Request(
            url=url,
            data=body,
            headers=dict(aws_request.headers),
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                return _Response(
                    status_code=response.status,
                    body=response.read(),
                )
        except urllib.error.HTTPError as error:
            return _Response(
                status_code=error.code,
                body=error.read(),
            )

    def _build_url(
        self,
        path: str,
        query_params: dict[str, str] | None = None,
    ) -> str:
        """Construct the full URL from base, path, and query parameters."""
        # Ensure path starts with /
        if not path.startswith("/"):
            path = f"/{path}"

        url = f"{self._base_url}{path}"

        if query_params:
            url = f"{url}?{urlencode(query_params)}"

        return url
