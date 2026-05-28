"""Factory function for creating a configured AuthorizationClient."""

import os

from authorization.client import AuthorizationClient
from authorization.exceptions import ConfigurationError
from authorization.sigv4_transport import SigV4Transport

_ENV_VAR = "AUTHORIZATION_API_URL"


def create_authorization_client(
    base_url: str | None = None,
    max_retries: int = 3,
    base_backoff: float = 1.0,
    timeout: float = 30.0,
) -> AuthorizationClient:
    """Create an AuthorizationClient with SigV4 transport.

    Resolves the API base URL from the explicit parameter or the
    ``AUTHORIZATION_API_URL`` environment variable. Instantiates a
    SigV4Transport and returns a fully configured client.

    If ``base_url`` is None or empty, the function falls back to the
    environment variable. If both are absent or empty, a
    ConfigurationError is raised.

    Args:
        base_url: API base URL. Falls back to AUTHORIZATION_API_URL
            environment variable if not provided or empty.
        max_retries: Maximum retry attempts on 503 responses.
        base_backoff: Base delay in seconds for exponential backoff.
        timeout: HTTP request timeout in seconds. Defaults to 30.

    Returns:
        A configured AuthorizationClient instance.

    Raises:
        ConfigurationError: If no base URL is resolvable from the
            parameter or environment variable.
    """
    resolved_url = base_url or os.environ.get(_ENV_VAR)
    if not resolved_url:
        raise ConfigurationError(
            f"No base URL provided and {_ENV_VAR} environment variable is not set"
        )

    transport = SigV4Transport(base_url=resolved_url, timeout=timeout)
    return AuthorizationClient(
        transport=transport,
        max_retries=max_retries,
        base_backoff=base_backoff,
    )
