"""Failure analyzer for complex user management scenarios."""

from typing import List, Optional

from flywheel_adaptor.flywheel_proxy import FlywheelError

from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserProcessEvent,
)
from users.user_entry import RegisteredUserEntry, UserEntry
from users.user_process_environment import UserProcessEnvironment
from users.user_registry import RegistryPerson, org_name_is


class FailureAnalyzer:
    """Failure analyzer for complex scenarios that require investigation."""

    def __init__(self, environment: UserProcessEnvironment):
        """Initialize the failure analyzer with the user process environment.

        Args:
            environment: The user process environment containing services
        """
        self.env = environment

    def analyze_flywheel_user_creation_failure(
        self, entry: RegisteredUserEntry, error: FlywheelError
    ) -> Optional[UserProcessEvent]:
        """Analyze why Flywheel user creation failed after 3 attempts.

        Args:
            entry: The registered user entry that failed to be created
            error: The FlywheelError that occurred

        Returns:
            A UserProcessEvent describing the failure, or None if analysis fails
        """
        try:
            # Check if user already exists (duplicate)
            existing_user = self.env.find_user(entry.registry_id)
            if existing_user:
                return UserProcessEvent(
                    event_type=EventType.ERROR,
                    category=EventCategory.DUPLICATE_USER_RECORDS,
                    user_context=UserContext.from_user_entry(entry),
                    message="User already exists in Flywheel",
                    action_needed="deactivate_duplicate_and_clear_cache",
                )

            # Check if it's a permission issue
            error_str = str(error).lower()
            if "permission" in error_str or "unauthorized" in error_str:
                return UserProcessEvent(
                    event_type=EventType.ERROR,
                    category=EventCategory.INSUFFICIENT_PERMISSIONS,
                    user_context=UserContext.from_user_entry(entry),
                    message="Insufficient permissions to create user in Flywheel",
                    action_needed="check_flywheel_service_account_permissions",
                )

            # Generic Flywheel error
            return UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.FLYWHEEL_ERROR,
                user_context=UserContext.from_user_entry(entry),
                message="Flywheel user creation failed after 3 attempts",
                action_needed="check_flywheel_logs_and_service_status",
            )

        except Exception:
            # If analysis fails, return a generic error event
            return UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.FLYWHEEL_ERROR,
                user_context=UserContext.from_user_entry(entry),
                message="Flywheel user creation failed after 3 attempts",
                action_needed="check_flywheel_logs_and_service_status",
            )

    def analyze_missing_claimed_user(
        self, entry: RegisteredUserEntry
    ) -> Optional[UserProcessEvent]:
        """Analyze why we can't find a claimed user by registry_id.

        This method is specifically for the scenario where:
        - We have a RegisteredUserEntry with a registry_id
        - find_by_registry_id() returns None (user not found in registry)
        - This indicates a data inconsistency between our records and the registry

        The method checks two possible explanations:
        1. Bad claim: User is claimed but has no email (found in bad_claims)
        2. Missing from registry: User not found by email or in bad claims

        If the user IS found by email, this indicates a serious data inconsistency
        (registry_id index is out of sync with email index) and an exception is raised.

        IMPORTANT: This method should ONLY be used when find_by_registry_id()
        fails to find a user. Do not use this method for other scenarios such as:
        - User not found by email
        - User found but not claimed
        - User found but missing other data

        Args:
            entry: The registered user entry that should exist but wasn't found
                  by registry_id lookup

        Returns:
            A UserProcessEvent describing the issue, or None if the user is found
            by email but not by registry_id (indicating a bad claim scenario)

        Raises:
            RuntimeError: If user is found by email but not by registry_id,
                         indicating registry data structure inconsistency
            RegistryError: If registry API calls fail during analysis
        """
        # Check if user exists by email
        email_to_check = entry.auth_email or entry.email
        person_list = self.env.get_from_registry(email=email_to_check)

        if person_list:
            # This should never happen - registry data structures are inconsistent
            found_ids = [p.registry_id() for p in person_list]
            raise RuntimeError(
                f"Registry data inconsistency: User {email_to_check} found by "
                f"email (registry_ids: {found_ids}) but not by registry_id "
                f"{entry.registry_id}. This indicates a bug in registry indexing."
            )

        # Not found by email - check if it's a bad claim
        full_name = entry.name.as_str() if entry.name else None
        if full_name:
            bad_claim_persons = self.env.user_registry.get_bad_claim(full_name)
            if bad_claim_persons:
                # It's a bad claim - delegate to existing method
                return self.detect_incomplete_claim(entry, bad_claim_persons)

        # Not found anywhere - user is missing from registry
        return UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.MISSING_REGISTRY_DATA,
            user_context=UserContext.from_user_entry(entry),
            message=(
                "Expected claimed user not found in registry by ID, "
                "email, or bad claims"
            ),
            action_needed="verify_registry_record_exists_or_was_deleted",
        )

    def detect_incomplete_claim(
        self, entry: UserEntry, bad_claim_persons: List[RegistryPerson]
    ) -> Optional[UserProcessEvent]:
        """Detect incomplete claims and identify if ORCID is the identity
        provider.

        An incomplete claim occurs when a user has claimed their account (logged in
        via an identity provider) but the identity provider did not return complete
        information such as email address. ORCID is a common identity provider that
        requires special configuration and often causes this issue.

        Args:
            entry: The user entry from the directory
            bad_claim_persons: List of RegistryPerson objects with incomplete claims

        Returns:
            A UserProcessEvent with category BAD_ORCID_CLAIMS or INCOMPLETE_CLAIM
        """
        # Check if any of the bad claim persons have ORCID org identity
        has_orcid = any(
            person.org_identities(predicate=org_name_is("ORCID"))
            for person in bad_claim_persons
        )

        if has_orcid:
            return UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.BAD_ORCID_CLAIMS,
                user_context=UserContext.from_user_entry(entry),
                message="User has incomplete claim with ORCID identity provider",
                action_needed="delete_bad_record_and_reclaim_with_institutional_idp",
            )

        return UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.INCOMPLETE_CLAIM,
            user_context=UserContext.from_user_entry(entry),
            message=(
                "User has incomplete claim (identity provider did not return email)"
            ),
            action_needed="verify_identity_provider_configuration_and_reclaim",
        )
