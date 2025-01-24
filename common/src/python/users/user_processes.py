import logging
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, Generic, List, Literal, Optional, TypeVar

from centers.nacc_group import NACCGroup
from coreapi_client.models.identifier import Identifier
from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import FlywheelError, FlywheelProxy
from notifications.email import DestinationModel, EmailClient, TemplateDataModel

from users.authorizations import AuthMap, Authorizations
from users.nacc_directory import ActiveUserEntry, RegisteredUserEntry, UserEntry
from users.user_registry import RegistryPerson, UserRegistry

log = logging.getLogger(__name__)

NotificationModeType = Literal['date', 'force', 'none']


class NotificationClient:
    """Wrapper for the email client to send email notifications for the user
    enrollment flow."""

    def __init__(self, email_client: EmailClient, configuration_set_name: str,
                 portal_url: str, mode: NotificationModeType) -> None:
        self.__client = email_client
        self.__configuration_set_name = configuration_set_name
        self.__portal_url = portal_url
        self.__mode: NotificationModeType = mode

    def __claim_template(self,
                         user_entry: ActiveUserEntry) -> TemplateDataModel:
        """Creates the email data template from the user entry for a registry
        claim email.

        The user entry must have the auth email address set.

        Args:
          user_entry: the user entry
        Returns:
          the template model with first name and auth email address
        """
        assert user_entry.auth_email, "user entry must have auth email"
        return TemplateDataModel(firstname=user_entry.first_name,
                                 email_address=user_entry.auth_email)

    def __claim_destination(self,
                            user_entry: ActiveUserEntry) -> DestinationModel:
        """Creates the email destination from the user entry for a registry
        claim email.

        The user entry must have the auth email address set.

        Args:
          user_entry: the user entry
        Returns:
          the destination model with auth email address.
        """
        assert user_entry.auth_email, "user entry must have auth email"
        return DestinationModel(to_addresses=[user_entry.auth_email])

    def send_claim_email(self, user_entry: ActiveUserEntry) -> None:
        """Sends the initial claim email to the auth email of the user.

        The user entry must have the auth email address set.

        Args:
          user_entry: the user entry for the user
        """
        self.__client.send(
            configuration_set_name=self.__configuration_set_name,
            destination=self.__claim_destination(user_entry),
            template="claim",
            template_data=self.__claim_template(user_entry))

    def send_followup_claim_email(self, user_entry: ActiveUserEntry) -> None:
        """Sends the followup claim email to the auth email of the user.

        The user entry must have the auth email address set.

        Args:
          user_entry: the user entry for the user
        """
        if self.__should_send(user_entry):
            self.__client.send(
                configuration_set_name=self.__configuration_set_name,
                destination=self.__claim_destination(user_entry),
                template="followup-claim",
                template_data=self.__claim_template(user_entry))

    def send_creation_email(self, user_entry: ActiveUserEntry) -> None:
        """Sends the user creation email to the email of the user.

        Args:
          user_entry: the user entry for the user
        """
        assert user_entry.auth_email, "user entry must have auth email"
        self.__client.send(
            configuration_set_name=self.__configuration_set_name,
            destination=DestinationModel(to_addresses=[user_entry.email],
                                         cc_addresses=[user_entry.auth_email]),
            template="user-creation",
            template_data=TemplateDataModel(firstname=user_entry.first_name,
                                            url=self.__portal_url))

    def __should_send(self, user_entry: ActiveUserEntry) -> bool:
        """Determines whether to send a notification.

        If notification mode is force, then returns true.
        If mode is none, returns False.
        If mode is date, returns true if the number of days since creation is
        a multiple of 7, and False otherwise.

        Args:
        user_entry: the directory entry for user
        Returns:
        True if criteria for notification mode is met. False, otherwise.
        """
        if self.__mode == 'force':
            return True
        if self.__mode == 'none':
            return False

        assert user_entry.registration_date, "user must be registered"

        time_since_creation = user_entry.registration_date - datetime.now()
        return (time_since_creation.days % 7 == 0
                and time_since_creation.days / 7 <= 3)


class UserProcessEnvironment:
    """Defines the environment consisting of services used in user
    management."""

    def __init__(self, *, admin_group: NACCGroup, authorization_map: AuthMap,
                 proxy: FlywheelProxy, registry: UserRegistry,
                 notification_client: NotificationClient) -> None:
        self.__admin_group = admin_group
        self.__authorization_map = authorization_map
        self.__proxy = proxy
        self.__registry = registry
        self.__notification_client = notification_client

    @property
    def admin_group(self) -> NACCGroup:
        return self.__admin_group

    @property
    def authorization_map(self) -> AuthMap:
        return self.__authorization_map

    @property
    def proxy(self) -> FlywheelProxy:
        return self.__proxy

    @property
    def user_registry(self) -> UserRegistry:
        return self.__registry

    @property
    def notification_client(self) -> NotificationClient:
        return self.__notification_client


T = TypeVar('T')


class BaseUserProcess(ABC, Generic[T]):
    """Abstract type for a user process.

    Call pattern for a user process is

    ```
    process.execute(queue)
    ```

    Subclasses should apply the process as a visitor to the queue.
    """

    @abstractmethod
    def visit(self, entry: T) -> None:
        pass

    @abstractmethod
    def execute(self, queue: 'UserQueue[T]') -> None:
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

        Destroys the queue.

        Args:
          process: the user process
        """
        while self.__queue:
            entry = self.__dequeue()
            process.visit(entry)


class InactiveUserProcess(BaseUserProcess[UserEntry]):
    """User process for user entries marked inactive."""

    def visit(self, entry: UserEntry) -> None:
        """Visit method for an inactive user entry.

        Args:
          entry: the inactive user entry
        """
        log.info("ignoring inactive entry %s", entry.email)

    def execute(self, queue: UserQueue[UserEntry]) -> None:
        """Applies this process to the queue.

        Args:
          queue: the user entry queue
        """
        log.info('**Processing inactive entries')
        queue.apply(self)


class CreatedUserProcess(BaseUserProcess[RegisteredUserEntry]):
    """Defines the user process for user entries recently created in
    Flywheel."""

    def __init__(self, notification_client: NotificationClient) -> None:
        self.__notification_client = notification_client

    def visit(self, entry: RegisteredUserEntry) -> None:
        """Processes the user entry by sendings a notification email.

        Args:
          entry: the user entry
        """
        self.__notification_client.send_creation_email(entry)

    def execute(self, queue: UserQueue[RegisteredUserEntry]) -> None:
        """Applies this process to the queue.

        Args:
          queue: the user entry queue
        """
        log.info('**Processing recently created Flywheel users')
        queue.apply(self)


class UpdateUserProcess(BaseUserProcess[RegisteredUserEntry]):
    """Defines the user process for user entries with existing Flywheel
    users."""

    def __init__(self, environment: UserProcessEnvironment) -> None:
        self.__env = environment

    def visit(self, entry: RegisteredUserEntry) -> None:
        """Makes updates to the user for the user entry: setting the user
        email, and authorizing user.

        Args:
          entry: the user entry
        """
        fw_user = self.__env.proxy.find_user(entry.registry_id)
        if not fw_user:
            log.error('Failed to add user %s with ID %s', entry.email,
                      entry.registry_id)
            return

        assert entry.auth_email, "user entry must have auth email"

        self.__update_email(user=fw_user, email=entry.email)
        self.__authorize_user(user=fw_user,
                              auth_email=entry.auth_email,
                              center_id=entry.adcid,
                              authorizations=entry.authorizations)

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

        log.info('Setting user %s email to %s', user.id, email)
        self.__env.proxy.set_user_email(user=user, email=email)

    def __authorize_user(self, *, user: User, auth_email: str, center_id: int,
                         authorizations: Authorizations) -> None:
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
            log.warning('No center found with ID %s', center_id)
            return

        # give users access to nacc metadata project
        self.__env.admin_group.add_center_user(user=user)

        # give users access to center projects
        center_group.add_user_roles(user=user,
                                    auth_email=auth_email,
                                    authorizations=authorizations,
                                    auth_map=self.__env.authorization_map)

    def execute(self, queue: UserQueue[RegisteredUserEntry]) -> None:
        """Applies this process to the queue.

        Args:
          queue: the user entry queue
        """
        log.info('**Update Flywheel users')
        queue.apply(self)


class ClaimedUserProcess(BaseUserProcess[RegisteredUserEntry]):
    """Processes user records that have been claimed in the user registry."""

    def __init__(self, environment: UserProcessEnvironment,
                 claimed_queue: UserQueue[RegisteredUserEntry]) -> None:
        self.__failed_count: Dict[str, int] = defaultdict(int)
        self.__claimed_queue: UserQueue[RegisteredUserEntry] = claimed_queue
        self.__created_queue: UserQueue[RegisteredUserEntry] = UserQueue()
        self.__update_queue: UserQueue[RegisteredUserEntry] = UserQueue()
        self.__env = environment

    def __add_user(self, entry: RegisteredUserEntry) -> Optional[str]:
        """Adds a user for the entry to Flywheel.

        Makes three attempts, and logs the error on the third attempt.

        Args:
          entry: the user entry
        Returns:
          the user id for the added user if succeeded. None, otherwise.
        """
        try:
            return self.__env.proxy.add_user(entry.as_user())
        except FlywheelError as error:
            self.__failed_count[entry.registry_id] += 1
            if self.__failed_count[entry.registry_id] >= 3:
                log.error("Unable to add user %s with ID %s: %s", entry.email,
                          entry.registry_id, str(error))
                return None

            self.__claimed_queue.enqueue(entry)
        return None

    def visit(self, entry: RegisteredUserEntry) -> None:
        """Processes a claimed user entry.

        Creates a Flywheel user if the entry does not have one.

        Adds user created (or with no login) to the created queue.
        Adds all users to the "update" queue.

        Args:
          entry: the user entry
        """
        assert entry.registry_id
        fw_user = self.__env.proxy.find_user(entry.registry_id)
        if not fw_user:
            log.info('User %s has no flywheel user with ID: %s', entry.email,
                     entry.registry_id)

            if not self.__add_user(entry):
                return

            self.__created_queue.enqueue(entry)

            log.info('Added user %s', entry.registry_id)

        fw_user = self.__env.proxy.find_user(entry.registry_id)
        if not fw_user:
            log.error('Failed to find user %s with ID %s', entry.email,
                      entry.registry_id)
            return

        self.__update_queue.enqueue(entry)

    def execute(self, queue: UserQueue[RegisteredUserEntry]) -> None:
        """Applies this process to the queue to create flywheel users and apply
        processes for created users, and user updates.

        Args:
          queue: the user entry queue
        """
        log.info('**Processing claimed users')
        queue.apply(self)

        created_process = CreatedUserProcess(self.__env.notification_client)
        created_process.execute(self.__created_queue)

        update_process = UpdateUserProcess(self.__env)
        update_process.execute(self.__update_queue)


class UnclaimedUserProcess(BaseUserProcess[ActiveUserEntry]):
    """Applies the process for user entries with unclaimed user registry
    entries."""

    def __init__(self, notification_client: NotificationClient) -> None:
        self.__notification_client = notification_client

    def visit(self, entry: ActiveUserEntry) -> None:
        """Sends a notification email to claim the user."""
        self.__notification_client.send_followup_claim_email(entry)

    def execute(self, queue: UserQueue[ActiveUserEntry]) -> None:
        """Applies this process to the queue.

        Args:
          queue: the user entry queue
        """
        log.info('**Processing unclaimed users')
        queue.apply(self)


class ActiveUserProcess(BaseUserProcess[ActiveUserEntry]):
    """Defines the process for active user entries relative to the COManage
    registry.

    Adds new user entries to the registry, and otherwise, splits the
    active users into claimed and unclaimed queues.
    """

    def __init__(self, environment: UserProcessEnvironment) -> None:
        self.__env = environment
        self.__claimed_queue: UserQueue[RegisteredUserEntry] = UserQueue()
        self.__unclaimed_queue: UserQueue[ActiveUserEntry] = UserQueue()

    def visit(self, entry: ActiveUserEntry) -> None:
        """Adds a new user to user registry, otherwise, adds the user to
        claimed or unclaimed queues.

        Args:
          entry: the user entry
        """
        if not entry.auth_email:
            log.error('User %s must have authentication email', entry.email)
            return

        person_list = self.__env.user_registry.get(email=entry.auth_email)
        if not person_list:
            if self.__env.user_registry.has_bad_claim(entry.full_name):
                log.error('Active user has incomplete claim: %s, %s',
                          entry.full_name, entry.email)
                return

            log.info('Active user not in registry: %s', entry.email)
            self.__add_to_registry(user_entry=entry)
            self.__env.notification_client.send_claim_email(entry)
            log.info('Added user %s to registry using email %s', entry.email,
                     entry.auth_email)
            return

        creation_date = self.__get_creation_date(person_list)
        if not creation_date:
            log.warning('person record for %s has no creation date',
                        entry.email)
            return

        entry.registration_date = creation_date

        claimed = self.__get_claimed(person_list)
        if claimed:
            registry_id = self.__get_registry_id(claimed)
            if not registry_id:
                log.error('User %s has no registry ID', entry.email)
                return

            self.__claimed_queue.enqueue(entry.register(registry_id))
            return

        self.__unclaimed_queue.enqueue(entry)

    def __get_claimed(
            self, person_list: List[RegistryPerson]) -> List[RegistryPerson]:
        """Builds the sublist of claimed members of the person list.

        Args:
          person_list: the list of person objects
        Returns:
          the claimed registry person objects
        """
        return [person for person in person_list if person.is_claimed()]

    def __add_to_registry(self, *, user_entry: UserEntry) -> List[Identifier]:
        """Adds a user to the registry using the user entry data.

        Note: the comanage API was not returning any identifers last checked

        Args:
        user_entry: the user directory entry
        Returns:
        the list of identifiers for the new registry record
        """
        assert user_entry.auth_email, "user entry must have auth email"
        identifier_list = self.__env.user_registry.add(
            RegistryPerson.create(firstname=user_entry.first_name,
                                  lastname=user_entry.last_name,
                                  email=user_entry.auth_email,
                                  coid=self.__env.user_registry.coid))

        return identifier_list

    def __get_registry_id(self,
                          person_list: List[RegistryPerson]) -> Optional[str]:
        """Gets the registry ID for a list of RegistryPerson objects with the
        same email address.

        Should only have one registry ID.

        Args:
        person_list: list of person objects representing "same" person
        Returns:
        registry ID from person object. None if none is found.
        """
        registered = {
            person.registry_id()
            for person in person_list if person.registry_id()
        }
        if not registered:
            return None
        if len(registered) > 1:
            log.error('More than one registry ID found: %s', registered)
            return None

        return registered.pop()

    def __get_creation_date(
            self, person_list: List[RegistryPerson]) -> Optional[datetime]:
        """Gets the most recent creation date from the person objects in the
        list.

        A person object will not have a creation date if was created locally.

        Args:
        person_list: the list of person objects
        Return:
        the max creation date if there is one. None, otherwise.
        """
        dates = [
            person.creation_date for person in person_list
            if person.creation_date
        ]
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
        log.info('**Processing active entries')
        queue.apply(self)

        claimed_process = ClaimedUserProcess(
            environment=self.__env, claimed_queue=self.__claimed_queue)
        claimed_process.execute(self.__claimed_queue)

        unclaimed_process = UnclaimedUserProcess(
            self.__env.notification_client)
        unclaimed_process.execute(self.__unclaimed_queue)


class UserProcess(BaseUserProcess[UserEntry]):
    """Defines the main process for handling directory user entries, which
    splits the queue into active and inactive subqueues."""

    def __init__(self, environment: UserProcessEnvironment) -> None:
        self.__active_queue: UserQueue[ActiveUserEntry] = UserQueue()
        self.__inactive_queue: UserQueue[UserEntry] = UserQueue()
        self.__env = environment

    def visit(self, entry: UserEntry) -> None:
        """Adds the entry to the active queue if it is active, or to the
        inactive queue otherwise.

        Args:
          entry: the user entry
        """
        if entry.active:
            if not entry.auth_email:
                log.info("Ignoring active user with no auth email: %s",
                         entry.email)
                return

            if isinstance(entry, ActiveUserEntry):
                self.__active_queue.enqueue(entry)
                return

        self.__inactive_queue.enqueue(entry)

    def execute(self, queue: UserQueue[UserEntry]) -> None:
        """Splits the queue into active and inactive queues of entries, and
        then applies appropriate processes to each.

        Args:
          queue: the user queue
        """
        log.info('**Processing directory entries')
        queue.apply(self)

        ActiveUserProcess(self.__env).execute(self.__active_queue)
        InactiveUserProcess().execute(self.__inactive_queue)
