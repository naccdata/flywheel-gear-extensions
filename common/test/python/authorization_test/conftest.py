"""Shared fixtures and mock transport for authorization client tests."""

from dataclasses import dataclass, field


@dataclass
class MockResponse:
    """Mock HTTP response for testing."""

    status_code: int
    body: bytes


class MockTransport:
    """Mock transport that returns pre-configured responses in sequence.

    If a single MockResponse is provided, it is returned for every call.
    If a list is provided, responses are returned in order; once
    exhausted, the last response is repeated.
    """

    def __init__(self, responses: list[MockResponse] | MockResponse) -> None:
        if isinstance(responses, MockResponse):
            responses = [responses]
        self.responses = responses
        self._call_index = 0
        self.requests: list[tuple[str, str, bytes | None, dict[str, str] | None]] = []

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> MockResponse:
        self.requests.append((method, path, body, query_params))
        response = self.responses[min(self._call_index, len(self.responses) - 1)]
        self._call_index += 1
        return response


@dataclass
class DataclassMockTransport:
    """Dataclass-based mock transport for use in property tests.

    Equivalent to MockTransport but uses dataclass syntax for
    compatibility with hypothesis strategies that construct via fields.
    """

    responses: list[MockResponse] = field(default_factory=list)
    requests: list[tuple[str, str, bytes | None, dict[str, str] | None]] = field(
        default_factory=list
    )
    _call_index: int = field(default=0, init=False)

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> MockResponse:
        self.requests.append((method, path, body, query_params))
        response = self.responses[min(self._call_index, len(self.responses) - 1)]
        self._call_index += 1
        return response


class CapturingTransport:
    """Transport that captures requests and returns a single fixed response.

    Useful for property tests that verify request construction.
    """

    def __init__(self, response: MockResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, str, bytes | None, dict[str, str] | None]] = []

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> MockResponse:
        self.requests.append((method, path, body, query_params))
        return self.response


def no_sleep(_: float) -> None:
    """No-op sleep callable for fast tests.

    Inject this as the ``sleep`` parameter to AuthorizationClient to
    avoid real delays during testing.
    """
