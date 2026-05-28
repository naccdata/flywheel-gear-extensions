"""Unit tests for AuthorizationClient.batch() method."""

import json

import pytest
from authorization.client import AuthorizationClient
from authorization.exceptions import (
    ParseError,
    ServiceUnavailableError,
    UnexpectedError,
    ValidationError,
)
from authorization.models import BatchOperation

from .conftest import MockResponse, MockTransport, no_sleep


def _make_operations(count: int) -> list[BatchOperation]:
    """Create a list of batch operations for testing."""
    return [
        BatchOperation(
            action="grant" if i % 2 == 0 else "revoke",
            user_id=f"user-{i}",
            resource_type="study",
            resource_id=f"resource-{i}",
            relation="member",
        )
        for i in range(count)
    ]


def _batch_success_response(
    total: int,
    succeeded: int,
    failed: int,
    errors: list[dict] | None = None,
) -> MockResponse:
    """Create a successful batch response."""
    body = {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors or [],
    }
    return MockResponse(status_code=200, body=json.dumps(body).encode())


class TestBatchChunking:
    """Tests for batch chunking behavior."""

    def test_single_chunk_under_100(self) -> None:
        """Operations <= 100 are sent in a single request."""
        ops = _make_operations(50)
        transport = MockTransport(
            [_batch_success_response(total=50, succeeded=50, failed=0)]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert len(transport.requests) == 1
        assert transport.requests[0][0] == "POST"
        assert transport.requests[0][1] == "/grants/batch"
        assert result.total == 50
        assert result.succeeded == 50
        assert result.failed == 0

    def test_exactly_100_operations_single_chunk(self) -> None:
        """Exactly 100 operations are sent in a single request."""
        ops = _make_operations(100)
        transport = MockTransport(
            [_batch_success_response(total=100, succeeded=100, failed=0)]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert len(transport.requests) == 1
        assert result.total == 100

    def test_101_operations_two_chunks(self) -> None:
        """101 operations are split into two chunks (100 + 1)."""
        ops = _make_operations(101)
        transport = MockTransport(
            [
                _batch_success_response(total=100, succeeded=100, failed=0),
                _batch_success_response(total=1, succeeded=1, failed=0),
            ]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert len(transport.requests) == 2
        assert result.total == 101
        assert result.succeeded == 101
        assert result.failed == 0

    def test_250_operations_three_chunks(self) -> None:
        """250 operations are split into three chunks (100 + 100 + 50)."""
        ops = _make_operations(250)
        transport = MockTransport(
            [
                _batch_success_response(total=100, succeeded=100, failed=0),
                _batch_success_response(total=100, succeeded=100, failed=0),
                _batch_success_response(total=50, succeeded=50, failed=0),
            ]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert len(transport.requests) == 3
        assert result.total == 250
        assert result.succeeded == 250

    def test_empty_operations_list(self) -> None:
        """Empty operations list returns zero result without network call."""
        ops: list[BatchOperation] = []
        transport = MockTransport(
            [_batch_success_response(total=0, succeeded=0, failed=0)]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert len(transport.requests) == 0
        assert result.total == 0


class TestBatchOrderPreservation:
    """Tests that batch chunking preserves operation order."""

    def test_order_preserved_across_chunks(self) -> None:
        """Operations are sent in original order across chunks."""
        ops = _make_operations(150)
        transport = MockTransport(
            [
                _batch_success_response(total=100, succeeded=100, failed=0),
                _batch_success_response(total=50, succeeded=50, failed=0),
            ]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        client.batch(ops)

        # Verify first chunk has first 100 operations
        first_request_body = transport.requests[0][2]
        assert first_request_body is not None
        first_body = json.loads(first_request_body)
        assert len(first_body["operations"]) == 100
        assert first_body["operations"][0]["userId"] == "user-0"
        assert first_body["operations"][99]["userId"] == "user-99"

        # Verify second chunk has remaining 50 operations
        second_request_body = transport.requests[1][2]
        assert second_request_body is not None
        second_body = json.loads(second_request_body)
        assert len(second_body["operations"]) == 50
        assert second_body["operations"][0]["userId"] == "user-100"
        assert second_body["operations"][49]["userId"] == "user-149"


class TestBatchRequestConstruction:
    """Tests for correct request body construction."""

    def test_request_body_uses_camel_case_aliases(self) -> None:
        """Request body uses camelCase field names."""
        ops = [
            BatchOperation(
                action="grant",
                user_id="user-1",
                resource_type="study",
                resource_id="res-1",
                relation="member",
            )
        ]
        transport = MockTransport(
            [_batch_success_response(total=1, succeeded=1, failed=0)]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        client.batch(ops)

        request_body = transport.requests[0][2]
        assert request_body is not None
        body = json.loads(request_body)
        op = body["operations"][0]
        assert "userId" in op
        assert "resourceId" in op
        assert op["userId"] == "user-1"
        assert op["resourceId"] == "res-1"
        assert op["type"] == "study"
        assert op["relation"] == "member"
        assert op["action"] == "grant"


class TestBatchErrorClassification:
    """Tests for per-operation error classification."""

    def test_conflict_counted_as_success(self) -> None:
        """Per-operation 'conflict' errors are idempotent successes."""
        ops = _make_operations(3)
        response = _batch_success_response(
            total=3,
            succeeded=2,
            failed=1,
            errors=[{"index": 1, "error": "conflict", "message": "Already exists"}],
        )
        transport = MockTransport([response])
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert result.total == 3
        assert result.succeeded == 3  # 2 + 1 idempotent
        assert result.failed == 0
        assert result.errors == []

    def test_not_found_counted_as_success(self) -> None:
        """Per-operation 'not_found' errors are idempotent successes."""
        ops = _make_operations(3)
        response = _batch_success_response(
            total=3,
            succeeded=2,
            failed=1,
            errors=[{"index": 2, "error": "not_found", "message": "Grant not found"}],
        )
        transport = MockTransport([response])
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0
        assert result.errors == []

    def test_service_unavailable_reported_as_failure(self) -> None:
        """Per-operation 'service_unavailable' errors are retriable
        failures."""
        ops = _make_operations(3)
        response = _batch_success_response(
            total=3,
            succeeded=2,
            failed=1,
            errors=[
                {
                    "index": 0,
                    "error": "service_unavailable",
                    "message": "Engine unavailable",
                }
            ],
        )
        transport = MockTransport([response])
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.errors) == 1
        assert result.errors[0].error == "service_unavailable"

    def test_other_errors_reported_as_failure(self) -> None:
        """Non-idempotent, non-retriable errors are reported as failures."""
        ops = _make_operations(3)
        response = _batch_success_response(
            total=3,
            succeeded=2,
            failed=1,
            errors=[
                {
                    "index": 1,
                    "error": "internal_error",
                    "message": "Something went wrong",
                }
            ],
        )
        transport = MockTransport([response])
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.errors) == 1
        assert result.errors[0].error == "internal_error"

    def test_mixed_errors_classified_correctly(self) -> None:
        """Mixed error types are classified independently."""
        ops = _make_operations(5)
        response = _batch_success_response(
            total=5,
            succeeded=2,
            failed=3,
            errors=[
                {"index": 0, "error": "conflict", "message": "Already exists"},
                {
                    "index": 2,
                    "error": "service_unavailable",
                    "message": "Unavailable",
                },
                {"index": 4, "error": "internal_error", "message": "Failed"},
            ],
        )
        transport = MockTransport([response])
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        # 2 succeeded + 1 idempotent (conflict) = 3
        assert result.succeeded == 3
        # 3 failed - 1 idempotent = 2
        assert result.failed == 2
        # Only non-idempotent errors remain
        assert len(result.errors) == 2
        error_codes = {e.error for e in result.errors}
        assert error_codes == {"service_unavailable", "internal_error"}


class TestBatchHTTPErrors:
    """Tests for HTTP-level error handling in batch."""

    def test_400_raises_validation_error(self) -> None:
        """HTTP 400 raises ValidationError with API message."""
        ops = _make_operations(5)
        error_body = json.dumps(
            {"error": "validation_error", "message": "Invalid operation format"}
        ).encode()
        transport = MockTransport([MockResponse(status_code=400, body=error_body)])
        client = AuthorizationClient(transport, sleep=no_sleep)

        with pytest.raises(ValidationError) as exc_info:
            client.batch(ops)

        assert "Invalid operation format" in str(exc_info.value)

    def test_500_raises_unexpected_error(self) -> None:
        """HTTP 500 raises UnexpectedError."""
        ops = _make_operations(5)
        error_body = json.dumps(
            {"error": "internal", "message": "Server error"}
        ).encode()
        transport = MockTransport([MockResponse(status_code=500, body=error_body)])
        client = AuthorizationClient(transport, sleep=no_sleep)

        with pytest.raises(UnexpectedError) as exc_info:
            client.batch(ops)

        assert exc_info.value.status_code == 500

    def test_503_retries_then_raises(self) -> None:
        """HTTP 503 triggers retry logic."""
        ops = _make_operations(5)
        # All responses are 503 - should exhaust retries
        responses = [
            MockResponse(status_code=503, body=b"Service Unavailable")
            for _ in range(4)  # initial + 3 retries
        ]
        transport = MockTransport(responses)
        client = AuthorizationClient(transport, max_retries=3, sleep=no_sleep)

        with pytest.raises(ServiceUnavailableError):
            client.batch(ops)

    def test_503_then_success(self) -> None:
        """HTTP 503 followed by success returns result."""
        ops = _make_operations(5)
        transport = MockTransport(
            [
                MockResponse(status_code=503, body=b"Service Unavailable"),
                _batch_success_response(total=5, succeeded=5, failed=0),
            ]
        )
        client = AuthorizationClient(transport, max_retries=3, sleep=no_sleep)

        result = client.batch(ops)

        assert result.total == 5
        assert result.succeeded == 5

    def test_malformed_response_raises_parse_error(self) -> None:
        """Non-JSON response body raises ParseError."""
        ops = _make_operations(5)
        transport = MockTransport(
            [MockResponse(status_code=200, body=b"not json at all")]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        with pytest.raises(ParseError) as exc_info:
            client.batch(ops)

        assert exc_info.value.raw_content == b"not json at all"


class TestBatchAggregation:
    """Tests for result aggregation across multiple chunks."""

    def test_aggregates_totals_across_chunks(self) -> None:
        """Results from multiple chunks are summed correctly."""
        ops = _make_operations(150)
        transport = MockTransport(
            [
                _batch_success_response(
                    total=100,
                    succeeded=98,
                    failed=2,
                    errors=[
                        {"index": 5, "error": "conflict", "message": "Exists"},
                        {
                            "index": 10,
                            "error": "internal_error",
                            "message": "Fail",
                        },
                    ],
                ),
                _batch_success_response(
                    total=50,
                    succeeded=49,
                    failed=1,
                    errors=[
                        {
                            "index": 3,
                            "error": "not_found",
                            "message": "Not found",
                        }
                    ],
                ),
            ]
        )
        client = AuthorizationClient(transport, sleep=no_sleep)

        result = client.batch(ops)

        # Total: 100 + 50 = 150
        assert result.total == 150
        # Succeeded: (98 + 1 idempotent) + (49 + 1 idempotent) = 149
        assert result.succeeded == 149
        # Failed: (2 - 1 idempotent) + (1 - 1 idempotent) = 1
        assert result.failed == 1
        # Only non-idempotent errors
        assert len(result.errors) == 1
        assert result.errors[0].error == "internal_error"
