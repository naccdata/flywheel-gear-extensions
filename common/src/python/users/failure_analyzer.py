"""Failure analyzer for complex user management scenarios."""

from typing import List, Optional

from flywheel_adaptor.flywheel_proxy import FlywheelError

from users.error_models import (
    ErrorCategory,
    ErrorEvent,
    UserContext,
)
from users.user_entry import ActiveUserEntry, RegisteredUserEntry, UserEntry
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
    ) -> Optional[ErrorEvent]:
        """Analyze why Flywheel user creation failed after 3 attempts.

        Args:
            entry: The registered user entry that failed to be created
            error: The FlywheelError that occurred

        Returns:
            An ErrorEvent describing the failure, or None if analysis fails
        """
        try:
            # Check if user already exists (duplicate)
            existing_user = self.env.find_user(entry.registry_id)
            if existing_user:
                return ErrorEvent(
                    category=ErrorCategory.DUPLICATE_USER_RECORDS,
                    user_context=UserContext.from_user_entry(entry),
                    error_details={
                        "message": "User already exists in Flywheel",
                        "existing_user_id": existing_user.id,
                        "registry_id": entry.registry_id,
                        "action_needed": "deactivate_duplicate_and_clear_cache",
                    },
                )

            # Check if it's a permission issue
            error_str = str(error).lower()
            if "permission" in error_str or "unauthorized" in error_str:
                return ErrorEvent(
                    category=ErrorCategory.INSUFFICIENT_PERMISSIONS,
                    user_context=UserContext.from_user_entry(entry),
                    error_details={
                        "message": (
                            "Insufficient permissions to create user in Flywheel"
                        ),
                        "flywheel_error": str(error),
                        "action_needed": "check_flywheel_service_account_permissions",
                    },
                )

            # Generic Flywheel error
            return ErrorEvent(
                category=ErrorCategory.FLYWHEEL_ERROR,
                user_context=UserContext.from_user_entry(entry),
                error_details={
                    "message": "Flywheel user creation failed after 3 attempts",
                    "error": str(error),
                    "registry_id": entry.registry_id,
                    "action_needed": "check_flywheel_logs_and_service_status",
                },
            )

        except Exception:
            # If analysis fails, return a generic error event
            return ErrorEvent(
                category=ErrorCategory.FLYWHEEL_ERROR,
                user_context=UserContext.from_user_entry(entry),
                error_details={
                    "message": "Flywheel user creation failed after 3 attempts",
                    "error": str(error),
                    "registry_id": entry.registry_id,
                    "action_needed": "check_flywheel_logs_and_service_status",
                },
            )

    def analyze_missing_claimed_user(
        self, entry: RegisteredUserEntry
    ) -> Optional[ErrorEvent]:
        """Analyze why we can't find a claimed user by registry_id.

        This method is specifically for the scenario where:
        - We have a RegisteredUserEntry with a registry_id
        - find_by_registry_id() returns None (user not found in registry)
        - This indicates a data inconsistency between our records and the registry

        IMPORTANT: This method should ONLY be used when find_by_registry_id()
        fails to find a user. Do not use this method for other scenarios such as:
        - User not found by email
        - User found but not claimed
        - User found but missing other data

        Args:
            entry: The registered user entry that should exist but wasn't found
                  by registry_id lookup

        Returns:
            An ErrorEvent describing the issue, or None if analysis fails
        """
        try:
            # Use environment's wrapper method to check what's actually there
            email_to_check = entry.auth_email or entry.email
            person_list = self.env.get_from_registry(email=email_to_check)

            if not person_list:
                return ErrorEvent(
                    category=ErrorCategory.UNCLAIMED_RECORDS,
                    user_context=UserContext.from_user_entry(entry),
                    error_details={
                        "message": "Expected claimed user not found in registry",
                        "registry_id": entry.registry_id,
                        "action_needed": "verify_registry_record_exists",
                    },
                )
            else:
                # User exists but not claimed properly
                return ErrorEvent(
                    category=ErrorCategory.UNCLAIMED_RECORDS,
                    user_context=UserContext.from_user_entry(entry),
                    error_details={
                        "message": "User found in registry but not properly claimed",
                        "registry_records": len(person_list),
                        "registry_id": entry.registry_id,
                        "action_needed": "check_claim_status_and_email_verification",
                    },
                )

        except Exception:
            # If analysis fails, return None
            return None

    def detect_email_mismatch(
        self, entry: UserEntry, registry_person: RegistryPerson
    ) -> Optional[ErrorEvent]:
        """Detect authentication email mismatch between directory and COManage.

        Compares the authentication email from the directory entry with all
        email addresses in the COManage registry record to identify mismatches.

        Args:
            entry: The user entry from the directory
            registry_person: The registry person from COManage

        Returns:
            An ErrorEvent if mismatch detected, None otherwise
        """
        if not entry.auth_email:
            return None

        # Check if the auth email exists in the registry person's emails
        if not registry_person.has_email(entry.auth_email):
            return ErrorEvent(
                category=ErrorCategory.EMAIL_MISMATCH,
                user_context=UserContext.from_user_entry(entry),
                error_details={
                    "message": (
                        "Authentication email in directory does not match "
                        "any email in COManage registry"
                    ),
                    "directory_auth_email": entry.auth_email,
                    "directory_email": entry.email,
                    "registry_emails": [
                        addr.mail for addr in registry_person.email_addresses
                    ],
                    "action_needed": "update_directory_with_correct_auth_email",
                },
            )

        return None

    def detect_unverified_email(
        self, registry_person: RegistryPerson
    ) -> Optional[ErrorEvent]:
        """Detect unverified email status in COManage registry.

        Checks if the registry person has any verified email addresses.

        Args:
            registry_person: The registry person from COManage

        Returns:
            An ErrorEvent if no verified emails found, None otherwise
        """
        if not registry_person.verified_email_addresses:
            # Create a basic user context from registry person
            user_context = UserContext(
                email=(
                    registry_person.email_address.mail
                    if registry_person.email_address
                    else "unknown"
                ),
                registry_id=registry_person.registry_id(),
            )

            return ErrorEvent(
                category=ErrorCategory.UNVERIFIED_EMAIL,
                user_context=user_context,
                error_details={
                    "message": "User has no verified email addresses in COManage",
                    "registry_id": registry_person.registry_id(),
                    "unverified_emails": [
                        addr.mail for addr in registry_person.email_addresses
                    ],
                    "action_needed": "contact_institutional_it_for_email_verification",
                },
            )

        return None

    def detect_insufficient_permissions(
        self, entry: ActiveUserEntry
    ) -> Optional[ErrorEvent]:
        """Detect insufficient permissions based on user entry authorizations.

        Checks if the user entry has no authorizations listed, indicating
        they lack necessary permissions.

        Args:
            entry: The active user entry from the directory

        Returns:
            An ErrorEvent if no authorizations found, None otherwise
        """
        if not entry.authorizations:
            return ErrorEvent(
                category=ErrorCategory.INSUFFICIENT_PERMISSIONS,
                user_context=UserContext.from_user_entry(entry),
                error_details={
                    "message": "User entry has no authorizations listed",
                    "directory_email": entry.email,
                    "action_needed": "contact_center_administrator_for_permissions",
                },
            )

        return None

    def detect_incomplete_claim(
        self, entry: UserEntry, bad_claim_persons: List[RegistryPerson]
    ) -> Optional[ErrorEvent]:
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
            An ErrorEvent with category BAD_ORCID_CLAIMS or INCOMPLETE_CLAIM
        """
        # Check if any of the bad claim persons have ORCID org identity
        has_orcid = any(
            person.org_identities(predicate=org_name_is("ORCID"))
            for person in bad_claim_persons
        )

        if has_orcid:
            return ErrorEvent(
                category=ErrorCategory.BAD_ORCID_CLAIMS,
                user_context=UserContext.from_user_entry(entry),
                error_details={
                    "message": "User has incomplete claim with ORCID identity provider",
                    "full_name": entry.name.full_name if entry.name else "unknown",
                    "has_orcid_org_identity": True,
                    "action_needed": (
                        "delete_bad_record_and_reclaim_with_institutional_idp"
                    ),
                },
            )

        return ErrorEvent(
            category=ErrorCategory.INCOMPLETE_CLAIM,
            user_context=UserContext.from_user_entry(entry),
            error_details={
                "message": (
                    "User has incomplete claim (identity provider did not return email)"
                ),
                "full_name": entry.name.full_name if entry.name else "unknown",
                "has_orcid_org_identity": False,
                "action_needed": "verify_identity_provider_configuration_and_reclaim",
            },
        )

    def detect_duplicate_user(
        self, entry: UserEntry, registry_id: Optional[str] = None
    ) -> Optional[ErrorEvent]:
        """Detect duplicate user records across systems.

        Checks if multiple registry records exist for the same email address,
        which could indicate duplicate or conflicting user records.

        Args:
            entry: The user entry from the directory
            registry_id: Optional registry ID to check for duplicates

        Returns:
            An ErrorEvent if duplicates detected, None otherwise
        """
        try:
            # Check for multiple registry records with the same email
            email_to_check = entry.auth_email or entry.email
            person_list = self.env.get_from_registry(email=email_to_check)

            if len(person_list) > 1:
                # Multiple records found for the same email
                registry_ids = [
                    person.registry_id()
                    for person in person_list
                    if person.registry_id()
                ]

                return ErrorEvent(
                    category=ErrorCategory.DUPLICATE_USER_RECORDS,
                    user_context=UserContext.from_user_entry(entry),
                    error_details={
                        "message": (
                            f"Multiple registry records ({len(person_list)}) "
                            f"found for email {email_to_check}"
                        ),
                        "email": email_to_check,
                        "registry_ids": registry_ids,
                        "action_needed": "deactivate_duplicate_records_and_clear_cache",
                    },
                )

            # If registry_id provided, check if it matches the found record
            if registry_id and person_list:
                found_person = person_list[0]
                found_registry_id = found_person.registry_id()

                if found_registry_id and found_registry_id != registry_id:
                    return ErrorEvent(
                        category=ErrorCategory.DUPLICATE_USER_RECORDS,
                        user_context=UserContext.from_user_entry(entry),
                        error_details={
                            "message": (
                                "Registry ID mismatch: expected "
                                f"{registry_id} but found {found_registry_id}"
                            ),
                            "expected_registry_id": registry_id,
                            "found_registry_id": found_registry_id,
                            "email": email_to_check,
                            "action_needed": (
                                "verify_correct_registry_id_and_deactivate_wrong_record"
                            ),
                        },
                    )

            return None

        except Exception:
            # If detection fails, return None
            return None
