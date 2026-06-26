"""Property-based tests for ResourceHierarchySeeder.

Tests correctness properties from the design document for the
authorization resource hierarchy feature.
"""

from unittest.mock import MagicMock

from authorization.client import AuthorizationClient
from authorization.exceptions import (
    AuthorizationClientError,
    ConfigurationError,
    ParseError,
    ServiceUnavailableError,
    UnexpectedError,
    ValidationError,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from projects.hierarchy_seeder import ResourceHierarchySeeder

# --- Strategies ---

# Valid resource IDs: non-empty alphanumeric strings with hyphens/underscores
resource_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_"),
    min_size=1,
    max_size=50,
)

# Valid study IDs
study_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-"),
    min_size=1,
    max_size=30,
)

# Valid center IDs
center_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-"),
    min_size=1,
    max_size=30,
)

# Error messages for exceptions
error_messages = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789 .:-_"),
    min_size=1,
    max_size=50,
)

# HTTP status codes for UnexpectedError
http_status_codes = st.sampled_from([400, 401, 403, 404, 405, 409, 422, 429, 500, 502])

# Strategy to generate random AuthorizationClientError subclass instances
# Uses st.one_of with map for fast generation without @st.composite overhead
authorization_client_errors = st.one_of(
    error_messages.map(AuthorizationClientError),
    error_messages.map(ConfigurationError),
    error_messages.map(lambda msg: ValidationError(message=msg, details=None)),
    error_messages.map(ServiceUnavailableError),
    st.tuples(http_status_codes, error_messages).map(
        lambda t: UnexpectedError(status_code=t[0], message=t[1])
    ),
    st.tuples(error_messages, st.binary(min_size=0, max_size=50)).map(
        lambda t: ParseError(message=t[0], raw_content=t[1])
    ),
)

# Seed method choices for the seeder
seed_methods = st.sampled_from(
    [
        "center_pipeline",
        "center_dashboard",
        "center_page",
        "study_dashboard",
        "study_page",
        "community_page",
    ]
)


# --- Property 4: Non-propagation of client exceptions ---


class TestProperty4NonPropagationOfClientExceptions:
    """Property 4: Non-propagation of client exceptions.

    For any exception raised by the AuthorizationClient during a
    set_resource_parents call, the seeder SHALL catch the exception
    and continue processing subsequent resources without raising.

    **Validates: Requirements 7.1, 7.2**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        error=authorization_client_errors,
        method_name=seed_methods,
        resource_id=resource_ids,
        study_id=study_ids,
        center_id=center_ids,
    )
    def test_no_exception_escapes_seeder(
        self,
        error: AuthorizationClientError,
        method_name: str,
        resource_id: str,
        study_id: str,
        center_id: str,
    ) -> None:
        """No AuthorizationClientError subclass escapes the seeder.

        **Validates: Requirements 7.1, 7.2**
        """
        mock_client = MagicMock(spec=AuthorizationClient)
        mock_client.set_resource_parents.side_effect = error

        seeder = ResourceHierarchySeeder(client=mock_client)

        # Call the appropriate seed method — no exception should escape
        if method_name == "center_pipeline":
            seeder.seed_center_pipeline(
                resource_id=resource_id,
                study_id=study_id,
                center_id=center_id,
            )
        elif method_name == "center_dashboard":
            seeder.seed_center_dashboard(
                resource_id=resource_id,
                study_id=study_id,
                center_id=center_id,
            )
        elif method_name == "center_page":
            seeder.seed_center_page(
                resource_id=resource_id,
                study_id=study_id,
                center_id=center_id,
            )
        elif method_name == "study_dashboard":
            seeder.seed_study_dashboard(
                resource_id=resource_id,
                study_id=study_id,
            )
        elif method_name == "study_page":
            seeder.seed_study_page(
                resource_id=resource_id,
                study_id=study_id,
            )
        elif method_name == "community_page":
            seeder.seed_community_page(
                resource_id=resource_id,
            )

        # Verify the failure was counted
        assert seeder.failure_count == 1

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(
        error=authorization_client_errors,
        resource_id=resource_ids,
        study_id=study_ids,
        center_id=center_ids,
    )
    def test_seeder_continues_after_exception(
        self,
        error: AuthorizationClientError,
        resource_id: str,
        study_id: str,
        center_id: str,
    ) -> None:
        """Seeder continues processing after an exception is caught.

        After one call raises, subsequent calls still execute normally.

        **Validates: Requirements 7.1, 7.2**
        """
        mock_client = MagicMock(spec=AuthorizationClient)
        # First call raises, second call succeeds
        mock_client.set_resource_parents.side_effect = [error, None]

        seeder = ResourceHierarchySeeder(client=mock_client)

        # First call — raises internally but does not propagate
        seeder.seed_center_pipeline(
            resource_id=resource_id,
            study_id=study_id,
            center_id=center_id,
        )

        # Second call — should succeed without issue
        seeder.seed_study_dashboard(
            resource_id=resource_id,
            study_id=study_id,
        )

        # Verify: one failure counted, two calls made
        assert seeder.failure_count == 1
        assert mock_client.set_resource_parents.call_count == 2
