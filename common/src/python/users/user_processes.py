import logging
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, Generic, List, Optional, TypeVar

from coreapi_client.models.identifier import Identifier
from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import FlywheelError

from users.authorization_visitor import (
    CenterAuthorizationVisitor,
    GeneralAuthorizationVisitor,
)
from users.authorizations import Authorizations, PageResource, StudyAuthorizations
from users.event_models import (
    EventCategory,
    EventType,
    UserContext,
    UserEventCollector,
    UserProcessEvent,
)
from users.failure_analyzer import FailureAnalyzer
from users.user_entry import ActiveUserEntry, CenterUserEntry, UserEntry
from users.user_process_environment import NotificationClient, UserProcessEnvironment
from users.user_registry import DomainCandidate, RegistryError, RegistryPerson

log = logging.getLogger(__name__)

T = TypeVar("T")


class BaseUserProcess(ABC, Generic[T]):
    """Abstract type for a user process.

    Call pattern for a user process is

    ```
    process.execute(queue)
    ```

    Subclasses should apply the process as a visitor to the queue.
    """

    def __init__(self, collector: UserEventCollector) -> None:
        """Initialize the base user process.

        Args:
            collector: Error collector for capturing error events
        """
        self.__collector = collector

    @property
    def collector(self) -> UserEventCollector:
        """Get the error collector (read-only access)."""
        return self.__collector

    @abstractmethod
    def visit(self, entry: T) -> None:
        pass

    @abstractmethod
    def execute(self, queue: "UserQueue[T]") -> None:
        pass


class UserQueue(Generic[T]):
    """Generic queue for user entries.

    Includes apply method to run user process over the queue entries.
    """

    def __init__(self) -> None:
        self.__queue: deque[T] = deque()

    def enqueue(self, user_entry: T) -> None:
        """Adds the user entry to the queue.

        Args:
          user_entry: the user entry to add
        """
        self.__queue.append(user_entry)

    def __dequeue(self) -> T:
        """Removes a user entry from the front of the queue.

        Assumes queue is nonempty.
        """
        assert self.__queue, "only dequeue with nonempty queue"
        return self.__queue.popleft()

    def apply(self, process: BaseUserProcess[T]) -> None:
        """Applies the user process to the entries of the queue.

        Destroys the queue. Individual entry processing errors are logged
        but do not stop the batch processing.

        Args:
          process: the user process
        """
        while self.__queue:
            entry = self.__dequeue()
            try:
                process.visit(entry)
            except (
                FlywheelError,
                RegistryError,
                ValueError,
                KeyError,
                AttributeError,
            ) as error:
                # Individual user processing errors should not stop the batch
                # Log the error and continue with the next user
                log.error(
                    "Error processing user entry: %s. Continuing with remaining users.",
                    error,
                    exc_info=True,
                )


class InactiveUserProcess(BaseUserProcess[UserEntry]):
    """User process for user entries marked inactive."""

    def __init__(
        self,
        environment: UserProcessEnvironment,
        collector: UserEventCollector,
    ) -> None:
        """Initialize the inactive user process.

        Args:
            environment: The user process environment
            collector: Error collector for capturing error events
        """
        super().__init__(collector)
        self.__env = environment

    def visit(self, entry: UserEntry) -> None:
        """Visit method for an inactive user entry.

        1. Looks up matching Flywheel users by email and disables each one.
        2. Looks up matching COmanage registry persons by email and suspends
           each one.

        The two operations are independent — failure of either does not
        prevent the other.

        Args:
          entry: the inactive user entry
        """
        log.info("processing inactive entry %s", entry.email)

        center_id = entry.adcid if isinstance(entry, CenterUserEntry) else None
        user_context = UserContext(
            email=entry.email,
            name=entry.name.as_str(),
            center_id=center_id,
        )

        # Step 1: Disable in Flywheel
        users = self.__env.proxy.find_user_by_email(entry.email)
        if not users:
            log.info("no matching Flywheel users found for %s", entry.email)
        else:
            for user in users:
                try:
                    self.__env.proxy.disable_user(user)
                    log.info(
                        "disabled user %s (%s)",
                        user.id,
                        entry.email,
                    )
                    success_event = UserProcessEvent(
                        event_type=EventType.SUCCESS,
                        category=EventCategory.USER_DISABLED,
                        user_context=user_context,
                        message=f"User {user.id} disabled in Flywheel",
                    )
                    self.collector.collect(success_event)
                except FlywheelError as error:
                    log.error(
                        "failed to disable user %s (%s): %s",
                        user.id,
                        entry.email,
                        error,
                    )
                    error_event = UserProcessEvent(
                        event_type=EventType.ERROR,
                        category=EventCategory.FLYWHEEL_ERROR,
                        user_context=user_context,
                        message=f"Failed to disable user {user.id}: {error}",
                    )
                    self.collector.collect(error_event)

        # Step 2: Suspend in COmanage
        person_list = self.__env.user_registry.get(email=entry.email)
        if not person_list:
            log.info("no matching COmanage registry persons for %s", entry.email)
        else:
            for person in person_list:
                registry_id = person.registry_id()
                if not registry_id:
                    continue
                if person.is_suspended():
                    log.info(
                        "user %s (%s) already suspended in COmanage, skipping",
                        registry_id,
                        entry.email,
                    )
                    continue
                try:
                    self.__env.user_registry.suspend(registry_id)
                    log.info(
                        "suspended user %s (%s) in COmanage",
                        registry_id,
                        entry.email,
                    )
                    success_event = UserProcessEvent(
                        event_type=EventType.SUCCESS,
                        category=EventCategory.USER_DISABLED,
                        user_context=user_context,
                        message=f"User {registry_id} suspended in COmanage",
                    )
                    self.collector.collect(success_event)
                except RegistryError as error:
                    log.error(
                        "failed to suspend user %s (%s) in COmanage: %s",
                        registry_id,
                        entry.email,
                        error,
                    )
                    error_event = UserProcessEvent(
                        event_type=EventType.ERROR,
                        category=EventCategory.USER_DISABLED,
                        user_context=user_context,
                        message=(
                            f"Failed to suspend user {registry_id} in COmanage: {error}"
                        ),
                    )
                    self.collector.collect(error_event)

    def execute(self, queue: UserQueue[UserEntry]) -> None:
        """Applies this process to the queue.

        Args:
          queue: the user entry queue
        """
        log.info("**Processing inactive entries")
        queue.apply(self)


class CreatedUserProcess(BaseUserProcess[ActiveUserEntry]):
    """Defines the user process for user entries recently created in
    Flywheel."""

    def __init__(
        self,
        notification_client: NotificationClient,
        collector: UserEventCollector,
    ) -> None:
        """Initialize the created user process.

        Args:
            notification_client: Client for sending notifications
            collector: Event collector for capturing events
        """
        super().__init__(collector)
        self.__notification_client = notification_client

    def visit(self, entry: ActiveUserEntry) -> None:
        """Processes the user entry by sending a notification email and
        collecting success event.

        Args:
          entry: the user entry (must be registered)
        """
        if not entry.is_registered:
            log.error(
                "Cannot process created user without registry_person: %s", entry.email
            )
            return

        # Send user creation email to the user
        self.__notification_client.send_creation_email(entry)

        # Collect success event for end-of-run notification
        success_event = UserProcessEvent(
            event_type=EventType.SUCCESS,
            category=EventCategory.USER_CREATED,
            user_context=UserContext.from_user_entry(entry),
            message="User successfully created in Flywheel",
        )
        self.collector.collect(success_event)

    def execute(self, queue: UserQueue[ActiveUserEntry]) -> None:
        """Applies this process to the queue.

        Args:
          queue: the user entry queue
        """
        log.info("**Processing recently created Flywheel users")
        queue.apply(self)


class UpdateCenterUserProcess(BaseUserProcess[CenterUserEntry]):
    """Defines the user process for center user entries with existing Flywheel
    users."""

    def __init__(
        self, environment: UserProcessEnvironment, collector: UserEventCollector
    ) -> None:
        super().__init__(collector)
        self.__env = environment
        self.__failure_analyzer = FailureAnalyzer(environment)

    def visit(self, entry: CenterUserEntry) -> None:
        if not entry.registry_person:
            log.error(
                "Cannot update center user without registry_person: %s",
                entry.email,
            )
            return

        if not entry.fw_user:
            log.error(
                "Cannot update center user without fw_user: %s",
                entry.email,
            )
            return

        registry_address = entry.registry_person.email_address
        if not registry_address:
            log.error(
                "Registry record does not have email address: %s", entry.registry_id
            )
            return

        authorizations = {
            authorization.study_id: authorization
            for authorization in entry.study_authorizations
        }
        self.__authorize_user(
            user=entry.fw_user,
            auth_email=registry_address.mail,
            center_id=entry.adcid,
            authorizations=authorizations,
        )

    def __authorize_user(
        self,
        *,
        user: User,
        auth_email: str,
        center_id: int,
        authorizations: dict[str, StudyAuthorizations],
    ) -> None:
        """Adds authorizations to the user.

        Users are granted access to nacc/metadata and projects per authorizations.

        Args:
        user: the user
        auth_email: the email used in the registry
        center_id: the center of the user
        authorizations: list of authorizations
        """
        center_group = self.__env.admin_group.get_center(center_id)
        if not center_group:
            log.warning("No center found with ID %s", center_id)
            return

        # give users access to nacc metadata project
        self.__env.admin_group.add_center_user(user=user)

        # give users access to center projects

        assert user.id, "requires user has ID"
        log.info("Adding roles for user %s", user.id)
        visitor = CenterAuthorizationVisitor(
            user=user,
            auth_email=auth_email,
            user_authorizations=authorizations,
            auth_map=self.__env.authorization_map,
            center_group=center_group,
        )
        portal_info = center_group.get_project_info()
        portal_info.apply(visitor)

    def execute(self, queue: UserQueue[CenterUserEntry]) -> None:
        log.info("**Processing center users")
        queue.apply(self)


class UpdateUserProcess(BaseUserProcess[ActiveUserEntry]):
    """Defines the user process for user entries with existing Flywheel
    users."""

    def __init__(
        self,
        environment: UserProcessEnvironment,
        collector: UserEventCollector,
    ) -> None:
        """Initialize the update user process.

        Args:
            environment: The user process environment
            collector: Error collector for capturing error events
        """
        super().__init__(collector)
        self.__env = environment
        self.__failure_analyzer = FailureAnalyzer(environment)
        self.__center_queue: UserQueue[CenterUserEntry] = UserQueue()

    def visit(self, entry: ActiveUserEntry) -> None:
        """Makes updates to the user for the user entry: setting the user
        email, and authorizing user.

        Args:
          entry: the user entry (must be registered)
        """
        if not entry.registry_person:
            log.error(
                "Cannot update user without registry_person: %s",
                entry.email,
            )
            return

        if not entry.registry_id:
            log.error(
                "Cannot update user without registry_id: %s",
                entry.email,
            )
            return

        fw_user = self.__env.find_user(entry.registry_id)
        if not fw_user:
            log.error(
                "Expected user %s with ID %s in Flywheel not found",
                entry.email,
                entry.registry_id,
            )
            return

        # Store the Flywheel user in the entry for downstream processes
        entry.set_fw_user(fw_user)

        self.__authorize_user(
            user=fw_user, email=entry.email, authorizations=entry.authorizations
        )
        self.__update_email(user=fw_user, email=entry.email)

        if isinstance(entry, CenterUserEntry):
            self.__center_queue.enqueue(entry)

    def __authorize_user(
        self, *, user: User, email: str, authorizations: Authorizations
    ) -> None:
        """Applies authorizations to give access to general resources.

        Processes general authorizations (not tied to specific centers) by creating
        a GeneralAuthorizationVisitor and dispatching page resource activities to it.

        Args:
            user: The Flywheel user to authorize
            email: The user's email address
            authorizations: The general authorizations containing activities
        """
        # Check if authorizations have any activities
        if not authorizations.activities:
            log.info("No general authorizations for user %s", user.id)
            return

        try:
            # Retrieve admin_group from environment
            admin_group = self.__env.admin_group

            # Create GeneralAuthorizationVisitor
            visitor = GeneralAuthorizationVisitor(
                user=user,
                authorizations=authorizations,
                auth_map=self.__env.authorization_map,
                nacc_group=admin_group,
                collector=self.collector,
            )

            # Iterate through activities and process page resources
            for activity in authorizations.activities.values():
                if isinstance(activity.resource, PageResource):
                    visitor.visit_page_resource(activity.resource)
        except Exception as error:
            # Catch unexpected exceptions, log error, don't propagate
            log.error(
                "Unexpected error during general authorization for user %s: %s",
                user.id,
                str(error),
                exc_info=True,
            )

    def __update_email(self, *, user: User, email: str) -> None:
        """Updates user email on FW instance if email is different.

        Checks whether user email is the same as new email.

        Note: this needs to be applied after a user is created if the ID and email
        are different, because the API wont allow a creating new user with ID and
        email different.

        Args:
        user: local user object
        email: email address to set
        """
        if user.email == email:
            return

        log.info("Setting user %s email to %s", user.id, email)
        self.__env.proxy.set_user_email(user=user, email=email)

    def execute(self, queue: UserQueue[ActiveUserEntry]) -> None:
        """Applies this process to the queue.

        Args:
          queue: the user entry queue
        """
        log.info("**Update Flywheel users")
        queue.apply(self)

        update_process = UpdateCenterUserProcess(self.__env, self.collector)
        update_process.execute(self.__center_queue)


class ClaimedUserProcess(BaseUserProcess[ActiveUserEntry]):
    """Processes user records that have been claimed in the user registry."""

    def __init__(
        self,
        environment: UserProcessEnvironment,
        claimed_queue: UserQueue[ActiveUserEntry],
        collector: UserEventCollector,
    ) -> None:
        """Initialize the claimed user process.

        Args:
            environment: The user process environment
            claimed_queue: Queue for claimed user entries
            collector: Event collector for capturing events
        """
        super().__init__(collector)
        self.__failed_count: Dict[str, int] = defaultdict(int)
        self.__claimed_queue: UserQueue[ActiveUserEntry] = claimed_queue
        self.__created_queue: UserQueue[ActiveUserEntry] = UserQueue()
        self.__update_queue: UserQueue[ActiveUserEntry] = UserQueue()
        self.__env = environment
        self.__failure_analyzer = FailureAnalyzer(environment)

    def __add_user(self, entry: ActiveUserEntry) -> Optional[str]:
        """Adds a user for the entry to Flywheel.

        Makes three attempts, and logs the error on the third attempt.

        Args:
          entry: the user entry (must be registered)
        Returns:
          the user id for the added user if succeeded. None, otherwise.
        """
        if not entry.registry_id:
            log.error("Cannot add user without registry_id: %s", entry.email)
            return None

        try:
            return self.__env.add_user(entry.as_user())
        except FlywheelError as error:
            self.__failed_count[entry.registry_id] += 1
            if self.__failed_count[entry.registry_id] >= 3:
                log.error(
                    "Unable to add user %s with ID %s: %s",
                    entry.email,
                    entry.registry_id,
                    str(error),
                )

                # Use failure analyzer to analyze the error
                error_event = (
                    self.__failure_analyzer.analyze_flywheel_user_creation_failure(
                        entry, error
                    )
                )
                if error_event:
                    self.collector.collect(error_event)

                return None

            self.__claimed_queue.enqueue(entry)
        return None

    def visit(self, entry: ActiveUserEntry) -> None:
        """Processes a claimed user entry.

        Creates a Flywheel user if the entry does not have one.

        Adds user created (or with no login) to the created queue.
        Adds all users to the "update" queue.

        Args:
          entry: the user entry (must be registered)
        """
        if not entry.registry_id:
            log.error(
                "Cannot process claimed user without registry_id: %s", entry.email
            )
            return

        fw_user = self.__env.find_user(entry.registry_id)
        if not fw_user:
            log.info(
                "User %s has no flywheel user with ID: %s",
                entry.email,
                entry.registry_id,
            )

            if not self.__add_user(entry):
                return

            self.__created_queue.enqueue(entry)

            log.info("Added user %s", entry.registry_id)

        fw_user = self.__env.find_user(entry.registry_id)
        if not fw_user:
            log.error(
                "Failed to add user %s with ID %s", entry.email, entry.registry_id
            )
            return

        self.__update_queue.enqueue(entry)

    def execute(self, queue: UserQueue[ActiveUserEntry]) -> None:
        """Applies this process to the queue to create flywheel users and apply
        processes for created users, and user updates.

        Args:
          queue: the user entry queue
        """
        log.info("**Processing claimed users")
        queue.apply(self)

        created_process = CreatedUserProcess(
            self.__env.notification_client, self.collector
        )
        created_process.execute(self.__created_queue)

        update_process = UpdateUserProcess(self.__env, self.collector)
        update_process.execute(self.__update_queue)


class UnclaimedUserProcess(BaseUserProcess[ActiveUserEntry]):
    """Applies the process for user entries with unclaimed user registry
    entries."""

    def __init__(
        self,
        notification_client: NotificationClient,
        collector: UserEventCollector,
    ) -> None:
        """Initialize the unclaimed user process.

        Args:
            notification_client: Client for sending notifications
            collector: Error collector for capturing error events
        """
        super().__init__(collector)
        self.__notification_client = notification_client

    def visit(self, entry: ActiveUserEntry) -> None:
        """Sends a notification email to claim the user and creates error event
        for tracking."""
        self.__notification_client.send_followup_claim_email(entry)

        # Create error event for unclaimed user tracking
        message = "User has not claimed their user registry record"
        if entry.registration_date:
            days_unclaimed = (datetime.now() - entry.registration_date).days
            message = (
                "User has not claimed their user registry record "
                f"({days_unclaimed} days unclaimed)"
            )

        error_event = UserProcessEvent(
            event_type=EventType.ERROR,
            category=EventCategory.UNCLAIMED_RECORDS,
            user_context=UserContext.from_user_entry(entry),
            message=message,
            action_needed="follow_up_with_user_to_claim_account",
        )
        self.collector.collect(error_event)

    def execute(self, queue: UserQueue[ActiveUserEntry]) -> None:
        """Applies this process to the queue.

        Args:
          queue: the user entry queue
        """
        log.info("**Processing unclaimed users")
        queue.apply(self)


class ActiveUserProcess(BaseUserProcess[ActiveUserEntry]):
    """Defines the process for active user entries relative to the COManage
    registry.

    Adds new user entries to the registry, and otherwise, splits the
    active users into claimed and unclaimed queues.
    """

    def __init__(
        self,
        environment: UserProcessEnvironment,
        collector: UserEventCollector,
    ) -> None:
        """Initialize the active user process.

        Args:
            environment: The user process environment
            collector: Event collector for capturing events
        """
        super().__init__(collector)
        self.__env = environment
        self.__claimed_queue: UserQueue[ActiveUserEntry] = UserQueue()
        self.__unclaimed_queue: UserQueue[ActiveUserEntry] = UserQueue()
        self.failure_analyzer = FailureAnalyzer(environment)

    def visit(self, entry: ActiveUserEntry) -> None:
        """Adds a new user to user registry, otherwise, adds the user to
        claimed or unclaimed queues.

        When a matching registry person is found with status 'S' (Suspended),
        re-enables them instead of treating them as a new user. This prevents
        duplicate record creation for returning users.

        The re-enable check happens after the email lookup but before the
        existing claimed/unclaimed routing.

        Args:
          entry: the user entry
        """
        if not entry.auth_email:
            log.error("User %s must have authentication email", entry.email)

            # Create error event for missing auth email
            error_event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.MISSING_DIRECTORY_DATA,
                user_context=UserContext.from_user_entry(entry),
                message="User has no authentication email in directory",
                action_needed="update_directory_auth_email",
            )
            self.collector.collect(error_event)
            return

        person_list = self.__env.user_registry.get(email=entry.auth_email)
        if not person_list:
            bad_claim = self.__env.user_registry.get_bad_claim(entry.full_name)
            if bad_claim:
                log.error(
                    "Active user has incomplete claim: %s, %s",
                    entry.full_name,
                    entry.email,
                )

                incomplete_claim_event = self.failure_analyzer.detect_incomplete_claim(
                    entry, bad_claim
                )
                if incomplete_claim_event:
                    self.collector.collect(incomplete_claim_event)
                return

            # Domain-aware and name-based fallback checks.
            # Only block skeleton creation when there is a name match
            # (combined signal or name-only). Domain-only hits are too
            # noisy at large institutions and are not reported.
            domain_candidates = self.__env.user_registry.get_by_parent_domain(
                entry.auth_email
            )
            name_candidates = self.__env.user_registry.get_by_name(entry.full_name)

            # Filter out self-matches: candidates whose email matches the
            # query email (case-insensitive). This handles registry records
            # stored with different casing than the directory entry.
            query_email_lower = entry.auth_email.lower()
            domain_candidates = [
                dc
                for dc in domain_candidates
                if dc.matched_email.lower() != query_email_lower
            ]
            name_candidates = [
                p
                for p in name_candidates
                if not any(
                    addr.mail.lower() == query_email_lower for addr in p.email_addresses
                )
            ]

            if name_candidates:
                self.__emit_near_miss_events(entry, domain_candidates, name_candidates)
                return

            log.info("Active user not in registry: %s", entry.email)
            self.__add_to_registry(user_entry=entry)
            self.__env.notification_client.send_claim_email(entry)
            log.info(
                "Added user %s to registry using email %s",
                entry.email,
                entry.auth_email,
            )
            return

        # Check for suspended persons and re-enable them
        suspended = [person for person in person_list if person.is_suspended()]
        if suspended:
            self.__re_enable_suspended(entry, suspended)
            return

        creation_date = self.__get_creation_date(person_list)
        if not creation_date:
            log.warning("person record for %s has no creation date", entry.email)
            return

        entry.registration_date = creation_date

        claimed = self.__get_claimed(person_list)
        if claimed:
            # Store the whole RegistryPerson object instead of just the ID
            entry.register(claimed[0])
            self.__claimed_queue.enqueue(entry)
            return

        self.__unclaimed_queue.enqueue(entry)

    def __get_claimed(self, person_list: List[RegistryPerson]) -> List[RegistryPerson]:
        """Builds the sublist of claimed members of the person list.

        Args:
          person_list: the list of person objects
        Returns:
          the claimed registry person objects
        """
        return [person for person in person_list if person.is_claimed()]

    def __re_enable_suspended(
        self,
        entry: ActiveUserEntry,
        suspended: List[RegistryPerson],
    ) -> None:
        """Re-enable suspended registry persons matched by email.

        For each suspended person with a registry ID, calls re_enable on
        the user registry. Collects success or error events for each.

        Args:
          entry: the active user entry
          suspended: list of suspended RegistryPerson objects
        """
        for person in suspended:
            registry_id = person.registry_id()
            if not registry_id:
                continue
            try:
                self.__env.user_registry.re_enable(registry_id)
                log.info(
                    "re-enabled user %s (%s) in COmanage",
                    registry_id,
                    entry.auth_email,
                )
                success_event = UserProcessEvent(
                    event_type=EventType.SUCCESS,
                    category=EventCategory.USER_RE_ENABLED,
                    user_context=UserContext.from_user_entry(entry),
                    message=(f"User {registry_id} re-enabled in COmanage"),
                )
                self.collector.collect(success_event)
            except RegistryError as error:
                log.error(
                    "failed to re-enable user %s (%s) in COmanage: %s",
                    registry_id,
                    entry.auth_email,
                    error,
                )
                error_event = UserProcessEvent(
                    event_type=EventType.ERROR,
                    category=EventCategory.USER_RE_ENABLED,
                    user_context=UserContext.from_user_entry(entry),
                    message=(
                        f"Failed to re-enable user {registry_id} in COmanage: {error}"
                    ),
                )
                self.collector.collect(error_event)

    def __emit_near_miss_events(
        self,
        entry: ActiveUserEntry,
        domain_candidates: List[DomainCandidate],
        name_candidates: List[RegistryPerson],
    ) -> None:
        """Emit near-miss diagnostic events for combined-signal and name-only
        candidates.

        Only emits events when a name match is present. Domain candidates
        are only reported when they also appear in the name results
        (combined signal). Pure domain-only matches are suppressed to
        avoid noise from large institutions.

        Args:
          entry: the active user entry being processed
          domain_candidates: candidates found via domain-aware lookup
          name_candidates: candidates found via name-based lookup
        """
        # Build sets of registry IDs (or object ids) for overlap detection
        domain_person_ids: set[str] = set()
        for dc in domain_candidates:
            pid = dc.person.registry_id() or str(id(dc.person))
            domain_person_ids.add(pid)

        name_person_ids: set[str] = set()
        for person in name_candidates:
            pid = person.registry_id() or str(id(person))
            name_person_ids.add(pid)

        combined_ids = domain_person_ids & name_person_ids

        # Determine summary category for logging
        if combined_ids:
            category = EventCategory.COMBINED_NEAR_MISS
        else:
            category = EventCategory.NAME_NEAR_MISS

        user_context = UserContext.from_user_entry(entry)

        # Emit events only for domain candidates that also matched by name
        for dc in domain_candidates:
            pid = dc.person.registry_id() or str(id(dc.person))
            if pid not in combined_ids:
                continue  # Skip domain-only matches
            event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.COMBINED_NEAR_MISS,
                user_context=user_context,
                message=(
                    f"Combined near-miss: candidate email={dc.matched_email}, "
                    f"name={dc.person.primary_name}, "
                    f"registry_id={dc.person.registry_id()}, "
                    f"query_domain={dc.query_domain}, "
                    f"candidate_domain={dc.candidate_domain}, "
                    f"parent_domain={dc.parent_domain}"
                ),
                action_needed="review_potential_duplicate",
            )
            self.collector.collect(event)

        # Emit events for name-only candidates (not already covered by combined)
        for person in name_candidates:
            pid = person.registry_id() or str(id(person))
            if pid in domain_person_ids:
                continue  # Already emitted as combined candidate
            candidate_email = (
                person.email_address.mail if person.email_address else "N/A"
            )
            event = UserProcessEvent(
                event_type=EventType.ERROR,
                category=EventCategory.NAME_NEAR_MISS,
                user_context=user_context,
                message=(
                    f"Name near-miss: candidate email={candidate_email}, "
                    f"name={person.primary_name}, "
                    f"registry_id={person.registry_id()}"
                ),
                action_needed="review_potential_duplicate",
            )
            self.collector.collect(event)

        log.info(
            "Near-miss candidates found for %s: %d combined, %d name-only, category=%s",
            entry.email,
            len(combined_ids),
            len(name_candidates) - len(combined_ids),
            category.value,
        )

    def __add_to_registry(self, *, user_entry: UserEntry) -> List[Identifier]:
        """Adds a user to the registry using the user entry data.

        When both auth_email and contact email are available and distinct,
        passes both to RegistryPerson.create() so the skeleton has a
        higher chance of matching the IdP-returned email during claim.

        Note: the comanage API was not returning any identifiers last checked

        Args:
        user_entry: the user directory entry
        Returns:
        the list of identifiers for the new registry record
        """
        assert user_entry.auth_email, "user entry must have auth email"

        # Determine email(s) to pass to skeleton creation
        email: str | list[str] = user_entry.auth_email
        if user_entry.email and user_entry.email != user_entry.auth_email:
            email = [user_entry.auth_email, user_entry.email]

        identifier_list = self.__env.user_registry.add(
            RegistryPerson.create(
                firstname=user_entry.first_name,
                lastname=user_entry.last_name,
                email=email,
                coid=self.__env.user_registry.coid,
            )
        )

        return identifier_list

    def __get_creation_date(
        self, person_list: List[RegistryPerson]
    ) -> Optional[datetime]:
        """Gets the most recent creation date from the person objects in the
        list.

        A person object will not have a creation date if was created locally.

        Args:
        person_list: the list of person objects
        Return:
        the max creation date if there is one. None, otherwise.
        """
        dates = [person.creation_date for person in person_list if person.creation_date]
        if not dates:
            return None

        return max(dates)

    def execute(self, queue: UserQueue[ActiveUserEntry]) -> None:
        """Applies this process to the active user queue.

        Registers any new users, and splits remainder into separate queues
        based on whether they are claimed in the registry or not.
        Then applies processes for claimed and unclaimed entries.

        Args:
          queue: the active user queue
        """
        log.info("**Processing active entries")
        queue.apply(self)

        claimed_process = ClaimedUserProcess(
            environment=self.__env,
            claimed_queue=self.__claimed_queue,
            collector=self.collector,
        )
        claimed_process.execute(self.__claimed_queue)

        unclaimed_process = UnclaimedUserProcess(
            self.__env.notification_client, self.collector
        )
        unclaimed_process.execute(self.__unclaimed_queue)


class UserProcess(BaseUserProcess[UserEntry]):
    """Defines the main process for handling directory user entries, which
    splits the queue into active and inactive sub-queues."""

    def __init__(
        self,
        environment: UserProcessEnvironment,
        collector: UserEventCollector,
    ) -> None:
        """Initialize the user process.

        Args:
            environment: The user process environment
            collector: Event collector for capturing events
        """
        super().__init__(collector)
        self.__active_queue: UserQueue[ActiveUserEntry] = UserQueue()
        self.__inactive_queue: UserQueue[UserEntry] = UserQueue()
        self.__env = environment

    def visit(self, entry: UserEntry) -> None:
        """Adds the entry to the active queue if it is active, or to the
        inactive queue otherwise.

        Args:
          entry: the user entry
        """
        if not entry.active:
            self.__inactive_queue.enqueue(entry)
            return

        if not entry.auth_email:
            log.info("Ignoring active user with no auth email: %s", entry.email)
            return

        if isinstance(entry, ActiveUserEntry):
            self.__active_queue.enqueue(entry)

    def execute(self, queue: UserQueue[UserEntry]) -> None:
        """Splits the queue into active and inactive queues of entries, and
        then applies appropriate processes to each.

        Args:
          queue: the user queue
        """
        log.info("**Processing directory entries")
        queue.apply(self)

        ActiveUserProcess(self.__env, self.collector).execute(self.__active_queue)
        InactiveUserProcess(self.__env, self.collector).execute(self.__inactive_queue)
