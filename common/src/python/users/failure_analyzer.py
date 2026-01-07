"""Failure analyzer for complex user management scenarios."""

from typing import Optional

from flywheel_adaptor.flywheel_proxy import FlywheelError

from users.error_models import (
    ErrorCategory,
    ErrorEvent,
    UserContext,
)
from users.user_entry import RegisteredUserEntry
from users.user_processes import UserProcessEnvironment


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
            # Check if user already exists (duplicate) using environment's proxy
            existing_user = self.env.proxy.find_user(entry.registry_id)
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
        """Analyze why we can't find a claimed user that should exist.

        Args:
            entry: The registered user entry that should exist but wasn't found

        Returns:
            An ErrorEvent describing the issue, or None if analysis fails
        """
        try:
            # Use environment's user registry to check what's actually there
            email_to_check = entry.auth_email or entry.email
            person_list = self.env.user_registry.get(email=email_to_check)

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
