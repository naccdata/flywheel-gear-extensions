"""Property tests for batch operations.

**Feature: authorization-client-library,
  Properties 7, 8, 9: Batch chunking and aggregation**
**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.7**
"""

import json
import math

from authorization.client import AuthorizationClient
from authorization.models import BatchOperation
from hypothesis import given, settings
from hypothesis import strategies as st

from .conftest import MockResponse, no_sleep

# --- Strategies ---

_RESOURCE_TYPES = st.sampled_from(
    ["study", "research_center", "community", "data_pipeline", "dashboard", "page"]
)

_RELATIONS = st.sampled_from(
    ["member", "admin", "viewer", "submitter", "auditor", "editor"]
)

_USER_IDS = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="-_@."
    ),
    min_size=1,
    max_size=30,
)

_RESOURCE_IDS = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
)

_BATCH_OPERATIONS = st.builds(
    BatchOperation,
    action=st.sampled_from(["grant", "revoke"]),
    user_id=_USER_IDS,
    resource_type=_RESOURCE_TYPES,
    resource_id=_RESOURCE_IDS,
    relation=_RELATIONS,
)

# Lists of 1-500 operations as specified in the design
_OPERATION_LISTS = st.lists(_BATCH_OPERATIONS, min_size=1, max_size=500)

# --- Mock Transport ---

# Error codes for per-operation errors
_IDEMPOTENT_ERROR_CODES = st.sampled_from(["conflict", "not_found"])
_NON_IDEMPOTENT_ERROR_CODES = st.sampled_from(
    ["service_unavailable", "internal_error", "permission_denied"]
)


class ChunkRecordingTransport:
    """Mock transport that records each batch request and returns success."""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> MockResponse:
        parsed_body = json.loads(body) if body else {}
        self.requests.append(
            {
                "method": method,
                "path": path,
                "body": parsed_body,
                "raw_body": body,
                "query_params": query_params,
            }
        )
        # Return a success response matching the number of operations
        num_ops = len(parsed_body.get("operations", []))
        response_body = json.dumps(
            {
                "total": num_ops,
                "succeeded": num_ops,
                "failed": 0,
                "errors": [],
            }
        ).encode()
        return MockResponse(status_code=200, body=response_body)


class MixedResultTransport:
    """Mock transport that returns configurable per-operation errors."""

    def __init__(
        self,
        idempotent_indices: list[int],
        non_idempotent_indices: list[int],
        idempotent_code: str = "conflict",
        non_idempotent_code: str = "internal_error",
    ) -> None:
        self.idempotent_indices = idempotent_indices
        self.non_idempotent_indices = non_idempotent_indices
        self.idempotent_code = idempotent_code
        self.non_idempotent_code = non_idempotent_code
        self.requests: list[dict] = []
        self._global_offset = 0

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query_params: dict[str, str] | None = None,
    ) -> MockResponse:
        parsed_body = json.loads(body) if body else {}
        self.requests.append({"body": parsed_body})
        num_ops = len(parsed_body.get("operations", []))

        # Determine which errors fall in this chunk
        chunk_start = self._global_offset
        chunk_end = chunk_start + num_ops

        errors = []
        idempotent_in_chunk = 0
        non_idempotent_in_chunk = 0

        for idx in self.idempotent_indices:
            if chunk_start <= idx < chunk_end:
                local_idx = idx - chunk_start
                errors.append(
                    {
                        "index": local_idx,
                        "error": self.idempotent_code,
                        "message": f"Idempotent error at {local_idx}",
                    }
                )
                idempotent_in_chunk += 1

        for idx in self.non_idempotent_indices:
            if chunk_start <= idx < chunk_end:
                local_idx = idx - chunk_start
                errors.append(
                    {
                        "index": local_idx,
                        "error": self.non_idempotent_code,
                        "message": f"Non-idempotent error at {local_idx}",
                    }
                )
                non_idempotent_in_chunk += 1

        total_errors = idempotent_in_chunk + non_idempotent_in_chunk
        succeeded = num_ops - total_errors
        failed = total_errors

        response_body = json.dumps(
            {
                "total": num_ops,
                "succeeded": succeeded,
                "failed": failed,
                "errors": errors,
            }
        ).encode()

        self._global_offset = chunk_end
        return MockResponse(status_code=200, body=response_body)


# --- Property Tests ---


@given(operations=_OPERATION_LISTS)
@settings(max_examples=100)
def test_batch_chunking_respects_size_limit(
    operations: list[BatchOperation],
) -> None:
    """Property 7: Batch chunking respects size limit.

    **Feature: authorization-client-library,
      Property 7: Batch chunking respects size limit**
    **Validates: Requirements 4.1, 4.2**

    For any list of N batch operations, the client sends exactly
    ceil(N/100) HTTP requests, each containing at most 100 operations.
    """
    transport = ChunkRecordingTransport()
    client = AuthorizationClient(transport, sleep=no_sleep)

    client.batch(operations)

    n = len(operations)
    expected_chunks = math.ceil(n / 100)

    # Verify correct number of requests
    assert len(transport.requests) == expected_chunks, (
        f"Expected {expected_chunks} requests for {n} operations, "
        f"got {len(transport.requests)}"
    )

    # Verify each chunk has at most 100 operations
    for i, req in enumerate(transport.requests):
        chunk_ops = req["body"]["operations"]
        assert len(chunk_ops) <= 100, (
            f"Chunk {i} has {len(chunk_ops)} operations, exceeds limit of 100"
        )


@given(operations=_OPERATION_LISTS)
@settings(max_examples=100)
def test_batch_chunking_preserves_order(
    operations: list[BatchOperation],
) -> None:
    """Property 8: Batch chunking preserves order.

    **Feature: authorization-client-library,
      Property 8: Batch chunking preserves order**
    **Validates: Requirements 4.3**

    For any list of batch operations, the concatenation of operations
    across all chunks (in chunk order) equals the original list.
    """
    transport = ChunkRecordingTransport()
    client = AuthorizationClient(transport, sleep=no_sleep)

    client.batch(operations)

    # Reconstruct the full list from chunks
    reconstructed: list[dict] = []
    for req in transport.requests:
        reconstructed.extend(req["body"]["operations"])

    # Verify same length
    assert len(reconstructed) == len(operations), (
        f"Reconstructed {len(reconstructed)} operations, expected {len(operations)}"
    )

    # Verify each operation matches in order
    for i, (original, sent) in enumerate(zip(operations, reconstructed, strict=False)):
        assert sent["userId"] == original.user_id, (
            f"Operation {i}: userId mismatch. "
            f"Expected '{original.user_id}', got '{sent['userId']}'"
        )
        assert sent["resourceId"] == original.resource_id, (
            f"Operation {i}: resourceId mismatch. "
            f"Expected '{original.resource_id}', got '{sent['resourceId']}'"
        )
        assert sent["type"] == original.resource_type, (
            f"Operation {i}: type mismatch. "
            f"Expected '{original.resource_type}', got '{sent['type']}'"
        )
        assert sent["relation"] == original.relation, (
            f"Operation {i}: relation mismatch. "
            f"Expected '{original.relation}', got '{sent['relation']}'"
        )
        assert sent["action"] == original.action, (
            f"Operation {i}: action mismatch. "
            f"Expected '{original.action}', got '{sent['action']}'"
        )


@given(
    operations=st.lists(_BATCH_OPERATIONS, min_size=1, max_size=500),
    idempotent_code=_IDEMPOTENT_ERROR_CODES,
    non_idempotent_code=_NON_IDEMPOTENT_ERROR_CODES,
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
@settings(max_examples=100)
def test_batch_result_aggregation(
    operations: list[BatchOperation],
    idempotent_code: str,
    non_idempotent_code: str,
    seed: int,
) -> None:
    """Property 9: Batch result aggregation.

    **Feature: authorization-client-library,
      Property 9: Batch result aggregation**
    **Validates: Requirements 4.4, 4.7**

    For any multi-chunk batch execution with mixed per-operation outcomes,
    the aggregate BatchResult has:
    - total == sum of all chunk totals
    - succeeded == sum of chunk successes + idempotent errors
    - failed == only non-idempotent failures
    """
    import random

    rng = random.Random(seed)
    n = len(operations)

    # Randomly select some indices for idempotent errors and some for
    # non-idempotent errors (non-overlapping)
    all_indices = list(range(n))
    rng.shuffle(all_indices)

    # Use up to 20% of operations as errors
    max_errors = max(1, n // 5)
    num_idempotent = rng.randint(0, min(max_errors, n))
    remaining = n - num_idempotent
    num_non_idempotent = rng.randint(0, min(max_errors, remaining))

    idempotent_indices = sorted(all_indices[:num_idempotent])
    non_idempotent_indices = sorted(
        all_indices[num_idempotent : num_idempotent + num_non_idempotent]
    )

    transport = MixedResultTransport(
        idempotent_indices=idempotent_indices,
        non_idempotent_indices=non_idempotent_indices,
        idempotent_code=idempotent_code,
        non_idempotent_code=non_idempotent_code,
    )
    client = AuthorizationClient(transport, sleep=no_sleep)

    result = client.batch(operations)

    # Verify aggregate totals
    assert result.total == n, f"Total should be {n}, got {result.total}"

    # Succeeded = operations that didn't error + idempotent errors
    expected_succeeded = (n - num_idempotent - num_non_idempotent) + num_idempotent
    assert result.succeeded == expected_succeeded, (
        f"Succeeded should be {expected_succeeded}, got {result.succeeded}. "
        f"(n={n}, idempotent={num_idempotent}, non_idempotent={num_non_idempotent})"
    )

    # Failed = only non-idempotent errors
    assert result.failed == num_non_idempotent, (
        f"Failed should be {num_non_idempotent}, got {result.failed}"
    )

    # Errors list should contain only non-idempotent errors
    assert len(result.errors) == num_non_idempotent, (
        f"Errors list should have {num_non_idempotent} entries, "
        f"got {len(result.errors)}"
    )

    # All reported errors should have the non-idempotent error code
    for error in result.errors:
        assert error.error == non_idempotent_code, (
            f"Expected error code '{non_idempotent_code}', got '{error.error}'"
        )
