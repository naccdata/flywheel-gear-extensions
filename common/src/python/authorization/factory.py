"""Factory function for creating a configured AuthorizationClient."""

from authorization.client import AuthorizationClient
from authorization.exceptions import ConfigurationError
from authorization.sigv4_transport import SigV4Transport


def create_authorization_client(
    base_url: str,
    max_retries: int = 3,
    base_backoff: float = 1.0,
    timeout: float = 30.0,
) -> AuthorizationClient:
    """Create an AuthorizationClient with SigV4 transport.

    Args:
        base_url: API base URL (e.g., from SSM parameter store).
        max_retries: Maximum retry attempts on 503 responses.
        base_backoff: Base delay in seconds for exponential backoff.
        timeout: HTTP request timeout in seconds. Defaults to 30.

    Returns:
        A configured AuthorizationClient instance.

    Raises:
        ConfigurationError: If base_url is empty.
    """
    if not base_url:
        raise ConfigurationError("Authorization API base URL is required")

    transport = SigV4Transport(base_url=base_url, timeout=timeout)
    return AuthorizationClient(
        transport=transport,
        max_retries=max_retries,
        base_backoff=base_backoff,
    )
