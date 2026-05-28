"""Authorization client for the NACC Authorization API."""

import json
import logging
import math
from collections.abc import Callable
from typing import Any

from authorization.exceptions import (
    ParseError,
    UnexpectedError,
    ValidationError,
)
from authorization.models import (
    BatchError,
    BatchOperation,
    BatchOperationModel,
    BatchRequestModel,
    BatchResult,
    ErrorResponse,
    GrantRequest,
    GrantResult,
    HealthResult,
    ParentRelationshipModel,
    ResourceParents,
    RevokeRequest,
    RevokeResult,
    SetParentsRequestModel,
    UserPermissions,
)
from authorization.retry import retry_on_503
from authorization.transport import HttpResponse, HttpTransport

log = logging.getLogger(__name__)

# Maximum number of operations per batch chunk
_BATCH_CHUNK_SIZE = 100

# Per-operation error codes treated as idempotent success
_IDEMPOTENT_ERROR_CODES = frozenset({"conflict", "not_found"})

# Per-operation error codes treated as retriable failures
_RETRIABLE_ERROR_CODES = frozenset({"service_unavailable"})


class AuthorizationClient:
    """Client for the NACC Authorization API.

    Provides typed, idempotent access to authorization operations with
    automatic retry on transient failures and transparent batch
    chunking.
    """

    def __init__(
        self,
        transport: HttpTransport,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialize the authorization client.

        Args:
            transport: HTTP transport implementation for sending requests.
            max_retries: Maximum retry attempts on 503 responses.
            base_backoff: Base delay in seconds for exponential backoff.
            sleep: Optional sleep callable for testing. If None, uses
                time.sleep via the retry module default.
        """
        self._transport = transport
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._sleep = sleep

    def _retry_kwargs(self) -> dict[str, Any]:
        """Build keyword arguments for retry_on_503."""
        kwargs: dict[str, Any] = {
            "max_retries": self._max_retries,
            "base_backoff": self._base_backoff,
        }
        if self._sleep is not None:
            kwargs["sleep"] = self._sleep
        return kwargs

    def grant(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
    ) -> GrantResult:
        """Grant a user a relation on a resource.

        Sends a POST request to /grants. Treats HTTP 409 (grant already
        exists) as a successful idempotent outcome.

        Args:
            user_id: The user identifier (e.g., ePPN).
            resource_type: The type of resource.
            resource_id: The resource identifier.
            relation: The relation to grant.

        Returns:
            GrantResult containing the granted relationship details.

        Raises:
            ValidationError: If the API returns 400.
            ServiceUnavailableError: If retries are exhausted on 503.
            UnexpectedError: On other unexpected HTTP errors.
        """
        request = GrantRequest(
            user_id=user_id,
            relation=relation,
            type=resource_type,
            resource_id=resource_id,
        )
        body = request.model_dump_json(by_alias=True).encode()

        def do_request() -> HttpResponse:
            return self._transport.request(
                method="POST",
                path="/grants",
                body=body,
            )

        response = retry_on_503(do_request, **self._retry_kwargs())

        if response.status_code in (200, 201):
            log.debug(
                "Grant succeeded: user=%s, type=%s, resource=%s, relation=%s",
                user_id,
                resource_type,
                resource_id,
                relation,
            )
            try:
                return GrantResult.model_validate_json(response.body)
            except Exception as exc:
                raise ParseError(
                    message=f"Failed to parse grant response: {exc}",
                    raw_content=response.body,
                ) from exc

        if response.status_code == 409:
            log.debug(
                "Grant already exists (idempotent): user=%s, type=%s, "
                "resource=%s, relation=%s",
                user_id,
                resource_type,
                resource_id,
                relation,
            )
            return GrantResult(
                user_id=user_id,
                relation=relation,
                type=resource_type,
                resource_id=resource_id,
            )

        if response.status_code == 400:
            error_resp = self._parse_error_response(response)
            log.error(
                "Grant validation error: %s",
                error_resp.message,
            )
            raise ValidationError(
                message=error_resp.message,
                details=error_resp.details,
            )

        # Any other error status
        error_msg = self._extract_error_message(response)
        log.error(
            "Grant unexpected error %d: %s",
            response.status_code,
            error_msg,
        )
        raise UnexpectedError(
            status_code=response.status_code,
            message=error_msg,
        )

    def revoke(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
    ) -> RevokeResult:
        """Revoke a user's relation on a resource.

        Sends a DELETE request to /grants. Treats HTTP 404 (grant does
        not exist) as a successful idempotent outcome.

        Args:
            user_id: The user identifier (e.g., ePPN).
            resource_type: The type of resource.
            resource_id: The resource identifier.
            relation: The relation to revoke.

        Returns:
            RevokeResult containing the revoked relationship details.

        Raises:
            ValidationError: If the API returns 400.
            ServiceUnavailableError: If retries are exhausted on 503.
            UnexpectedError: On other unexpected HTTP errors.
        """
        request = RevokeRequest(
            user_id=user_id,
            relation=relation,
            type=resource_type,
            resource_id=resource_id,
        )
        body = request.model_dump_json(by_alias=True).encode()

        def do_request() -> HttpResponse:
            return self._transport.request(
                method="DELETE",
                path="/grants",
                body=body,
            )

        response = retry_on_503(do_request, **self._retry_kwargs())

        if response.status_code == 200:
            log.debug(
                "Revoke succeeded: user=%s, type=%s, resource=%s, relation=%s",
                user_id,
                resource_type,
                resource_id,
                relation,
            )
            try:
                return RevokeResult.model_validate_json(response.body)
            except Exception as exc:
                raise ParseError(
                    message=f"Failed to parse revoke response: {exc}",
                    raw_content=response.body,
                ) from exc

        if response.status_code == 404:
            log.debug(
                "Revoke target not found (idempotent): user=%s, type=%s, "
                "resource=%s, relation=%s",
                user_id,
                resource_type,
                resource_id,
                relation,
            )
            return RevokeResult(
                user_id=user_id,
                relation=relation,
                type=resource_type,
                resource_id=resource_id,
            )

        if response.status_code == 400:
            error_resp = self._parse_error_response(response)
            log.error(
                "Revoke validation error: %s",
                error_resp.message,
            )
            raise ValidationError(
                message=error_resp.message,
                details=error_resp.details,
            )

        # Any other error status
        error_msg = self._extract_error_message(response)
        log.error(
            "Revoke unexpected error %d: %s",
            response.status_code,
            error_msg,
        )
        raise UnexpectedError(
            status_code=response.status_code,
            message=error_msg,
        )

    def batch(
        self,
        operations: list[BatchOperation],
    ) -> BatchResult:
        """Submit a batch of grant and revoke operations.

        Splits operations into chunks of at most 100, preserving order,
        and sends each chunk as a separate POST to /grants/batch. Results
        are aggregated across all chunks.

        Per-operation errors are classified:
        - conflict/not_found: counted as idempotent success
        - service_unavailable: reported as retriable failure
        - Other: reported as non-retriable failure

        Args:
            operations: List of batch operations to execute.

        Returns:
            Aggregate BatchResult with totals across all chunks.

        Raises:
            ValidationError: If the API returns 400 for the batch.
            ServiceUnavailableError: If retries are exhausted on 503.
            UnexpectedError: On other unexpected HTTP errors.
        """
        if not operations:
            return BatchResult(total=0, succeeded=0, failed=0, errors=[])

        num_chunks = max(1, math.ceil(len(operations) / _BATCH_CHUNK_SIZE))
        chunks = [
            operations[i * _BATCH_CHUNK_SIZE : (i + 1) * _BATCH_CHUNK_SIZE]
            for i in range(num_chunks)
        ]

        total = 0
        succeeded = 0
        failed = 0
        errors: list[BatchError] = []

        for chunk_index, chunk in enumerate(chunks):
            chunk_result = self._execute_batch_chunk(chunk, chunk_index)
            total += chunk_result.total
            succeeded += chunk_result.succeeded
            failed += chunk_result.failed
            errors.extend(chunk_result.errors)

        return BatchResult(
            total=total,
            succeeded=succeeded,
            failed=failed,
            errors=errors,
        )

    def _execute_batch_chunk(
        self,
        chunk: list[BatchOperation],
        chunk_index: int,
    ) -> BatchResult:
        """Execute a single batch chunk and classify results.

        Args:
            chunk: List of operations (at most 100).
            chunk_index: Zero-based index of this chunk for logging.

        Returns:
            BatchResult for this chunk with classified outcomes.
        """
        request_model = BatchRequestModel(
            operations=[
                BatchOperationModel(
                    action=op.action,
                    user_id=op.user_id,
                    relation=op.relation,
                    type=op.resource_type,
                    resource_id=op.resource_id,
                )
                for op in chunk
            ]
        )

        body = request_model.model_dump_json(by_alias=True).encode()

        def do_request() -> HttpResponse:
            return self._transport.request(
                method="POST",
                path="/grants/batch",
                body=body,
            )

        response = retry_on_503(do_request, **self._retry_kwargs())

        if response.status_code == 400:
            error_resp = self._parse_error_response(response)
            log.error(
                "Batch chunk %d validation error: %s",
                chunk_index,
                error_resp.message,
            )
            raise ValidationError(
                message=error_resp.message,
                details=error_resp.details,
            )

        if response.status_code not in (200, 201):
            error_msg = self._extract_error_message(response)
            log.error(
                "Batch chunk %d unexpected error %d: %s",
                chunk_index,
                response.status_code,
                error_msg,
            )
            raise UnexpectedError(
                status_code=response.status_code,
                message=error_msg,
            )

        # Parse the batch response
        chunk_result = self._parse_batch_response(response)

        # Classify per-operation errors
        return self._classify_batch_errors(chunk_result, chunk_index)

    def _classify_batch_errors(
        self,
        raw_result: BatchResult,
        chunk_index: int,
    ) -> BatchResult:
        """Classify per-operation errors in a batch response.

        - conflict/not_found errors are idempotent successes
        - service_unavailable errors are retriable failures
        - Other errors are non-retriable failures

        Args:
            raw_result: The raw BatchResult from the API response.
            chunk_index: Zero-based chunk index for logging.

        Returns:
            A new BatchResult with adjusted counts.
        """
        idempotent_count = 0
        real_errors: list[BatchError] = []

        for error in raw_result.errors:
            if error.error in _IDEMPOTENT_ERROR_CODES:
                idempotent_count += 1
                log.debug(
                    "Batch chunk %d operation %d: idempotent outcome (%s)",
                    chunk_index,
                    error.index,
                    error.error,
                )
            else:
                real_errors.append(error)
                if error.error in _RETRIABLE_ERROR_CODES:
                    log.warning(
                        "Batch chunk %d operation %d: retriable error (%s)",
                        chunk_index,
                        error.index,
                        error.error,
                    )
                else:
                    log.error(
                        "Batch chunk %d operation %d: failed (%s: %s)",
                        chunk_index,
                        error.index,
                        error.error,
                        error.message,
                    )

        return BatchResult(
            total=raw_result.total,
            succeeded=raw_result.succeeded + idempotent_count,
            failed=raw_result.failed - idempotent_count,
            errors=real_errors,
        )

    def get_user_permissions(
        self,
        user_id: str,
        type_filter: str | None = None,
        relation_filter: str | None = None,
    ) -> UserPermissions:
        """Retrieve all resources a user can access.

        Sends a GET request to /users/{userId}/permissions with optional
        type and relation query parameters for filtering.

        Args:
            user_id: The user identifier (e.g., ePPN).
            type_filter: Optional resource type to filter by.
            relation_filter: Optional relation to filter by.

        Returns:
            UserPermissions containing the user's permissions grouped
            by resource type.

        Raises:
            ServiceUnavailableError: If retries are exhausted on 503.
            UnexpectedError: On unexpected HTTP errors.
            ParseError: If the response body cannot be parsed.
        """
        path = f"/users/{user_id}/permissions"
        query_params: dict[str, str] = {}
        if type_filter is not None:
            query_params["type"] = type_filter
        if relation_filter is not None:
            query_params["relation"] = relation_filter

        def do_request() -> HttpResponse:
            return self._transport.request(
                method="GET",
                path=path,
                body=None,
                query_params=query_params or None,
            )

        response = retry_on_503(do_request, **self._retry_kwargs())

        if response.status_code == 200:
            log.debug(
                "Get user permissions succeeded: user=%s",
                user_id,
            )
            try:
                return UserPermissions.model_validate_json(response.body)
            except Exception as exc:
                raise ParseError(
                    message=(f"Failed to parse user permissions response: {exc}"),
                    raw_content=response.body,
                ) from exc

        # Any other error status
        error_msg = self._extract_error_message(response)
        log.error(
            "Get user permissions unexpected error %d: %s",
            response.status_code,
            error_msg,
        )
        raise UnexpectedError(
            status_code=response.status_code,
            message=error_msg,
        )

    def set_resource_parents(
        self,
        resource_type: str,
        resource_id: str,
        parents: list[ParentRelationshipModel],
    ) -> ResourceParents:
        """Set the parent organizations of a resource.

        Sends a PUT request to /resources/{type}/{resourceId}/parents
        with the list of parent relationships.

        Args:
            resource_type: The type of resource.
            resource_id: The resource identifier.
            parents: List of parent relationships to set.

        Returns:
            ResourceParents containing the updated parent relationships.

        Raises:
            ValidationError: If the API returns 400.
            ServiceUnavailableError: If retries are exhausted on 503.
            UnexpectedError: On other unexpected HTTP errors.
            ParseError: If the response body cannot be parsed.
        """
        request = SetParentsRequestModel(parents=parents)
        body = request.model_dump_json(by_alias=True).encode()
        path = f"/resources/{resource_type}/{resource_id}/parents"

        def do_request() -> HttpResponse:
            return self._transport.request(
                method="PUT",
                path=path,
                body=body,
            )

        response = retry_on_503(do_request, **self._retry_kwargs())

        if response.status_code == 200:
            log.debug(
                "Set resource parents succeeded: type=%s, resource=%s",
                resource_type,
                resource_id,
            )
            try:
                return ResourceParents.model_validate_json(response.body)
            except Exception as exc:
                raise ParseError(
                    message=(f"Failed to parse set parents response: {exc}"),
                    raw_content=response.body,
                ) from exc

        if response.status_code == 400:
            error_resp = self._parse_error_response(response)
            log.error(
                "Set resource parents validation error: %s",
                error_resp.message,
            )
            raise ValidationError(
                message=error_resp.message,
                details=error_resp.details,
            )

        # Any other error status
        error_msg = self._extract_error_message(response)
        log.error(
            "Set resource parents unexpected error %d: %s",
            response.status_code,
            error_msg,
        )
        raise UnexpectedError(
            status_code=response.status_code,
            message=error_msg,
        )

    def health_check(self) -> HealthResult:
        """Check the health of the Authorization API.

        Sends a GET request to /health. Unlike other methods, this does
        NOT retry on 503 — it returns an unhealthy result instead.

        Returns:
            HealthResult with the service health status.

        Raises:
            ParseError: If a 200 response body cannot be parsed.
            UnexpectedError: On unexpected HTTP errors (not 200 or 503).
        """
        response = self._transport.request(
            method="GET",
            path="/health",
            body=None,
            query_params=None,
        )

        if response.status_code == 200:
            log.debug("Health check succeeded")
            try:
                return HealthResult.model_validate_json(response.body)
            except Exception as exc:
                raise ParseError(
                    message=f"Failed to parse health check response: {exc}",
                    raw_content=response.body,
                ) from exc

        if response.status_code == 503:
            log.debug("Health check returned 503: service unhealthy")
            return HealthResult(status="unhealthy")

        # Any other error status
        error_msg = self._extract_error_message(response)
        log.error(
            "Health check unexpected error %d: %s",
            response.status_code,
            error_msg,
        )
        raise UnexpectedError(
            status_code=response.status_code,
            message=error_msg,
        )

    def _parse_batch_response(self, response: HttpResponse) -> BatchResult:
        """Parse a batch response body into a BatchResult.

        Args:
            response: The HTTP response with a JSON body.

        Returns:
            Parsed BatchResult model.

        Raises:
            ParseError: If the response body cannot be parsed.
        """
        try:
            return BatchResult.model_validate_json(response.body)
        except Exception as exc:
            raise ParseError(
                message=f"Failed to parse batch response: {exc}",
                raw_content=response.body,
            ) from exc

    def _parse_error_response(self, response: HttpResponse) -> ErrorResponse:
        """Parse an error response body.

        Args:
            response: The HTTP response with an error JSON body.

        Returns:
            Parsed ErrorResponse model.
        """
        try:
            return ErrorResponse.model_validate_json(response.body)
        except Exception:
            # If we can't parse the error response, create a generic one
            return ErrorResponse(
                error="unknown",
                message=response.body.decode(errors="replace"),
            )

    def _extract_error_message(self, response: HttpResponse) -> str:
        """Extract an error message from a response body.

        Args:
            response: The HTTP response.

        Returns:
            The error message string.
        """
        try:
            data = json.loads(response.body)
            return str(data.get("message", response.body.decode(errors="replace")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return response.body.decode(errors="replace")
