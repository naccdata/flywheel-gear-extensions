"""Defines repository as interface to user registry."""

from collections import defaultdict
from datetime import datetime
from typing import Callable, Dict, List, Optional

from coreapi_client.api.default_api import DefaultApi
from coreapi_client.exceptions import ApiException
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.co_person_role import CoPersonRole
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.inline_object import InlineObject as CoPersonResponse
from coreapi_client.models.name import Name
from coreapi_client.models.org_identity import OrgIdentity
from pydantic import ValidationError


def org_name_is(name: str) -> Callable[[OrgIdentity], bool]:
    """Creates a predicate function for testing organizational identity name.

    Args:
      name: the organization name to match (case-insensitive)
    Returns:
      a predicate function that returns True if org identity has matching name
    """

    def predicate(org_identity: OrgIdentity) -> bool:
        return org_identity.o is not None and org_identity.o.upper() == name.upper()

    return predicate


class RegistryPerson:
    """Wrapper for COManage CoPersonMessage object.

    Provides convenient access to person attributes from COManage including
    emails, names, identifiers, and status information. The class implements
    a priority-based email selection strategy and provides filtering methods
    for multi-valued attributes.

    Key Concepts:
        - **Active Person**: A person with CoPerson status="A" (active)
        - **Claimed Account**: An active person with a verified email AND an
          oidcsub identifier from cilogon.org (indicating they have logged in)
        - **Primary Email**: The highest priority email selected from:
          organizational → official → verified → any → None
        - **Organizational Email**: Email from a claimed organizational identity
        - **Official Email**: Email with type="official"
        - **Verified Email**: Email with verified=True

    Email Selection:
        The email_address property returns a single email using priority logic,
        while email_addresses returns all emails. Use email_address for the
        "best" email to contact a person, and email_addresses when you need
        to see all available emails.

    Attributes are read-only and computed on-demand from the underlying
    CoPersonMessage object.
    """

    def __init__(self, coperson_message: CoPersonMessage) -> None:
        self.__coperson_message = coperson_message

    @classmethod
    def create(
        cls, *, firstname: str, lastname: str, email: str, coid: int
    ) -> "RegistryPerson":
        """Creates a RegistryPerson object with the name and email.

        Note: the coid must match that of the registry

        Args:
          firstname: the first (given) name of person
          lastname: the last (family) name of the person
          email: the email address of the person
          coid: the CO ID for the COManage registry
        Returns:
          the RegistryPerson with name and email
        """
        coperson = CoPerson(co_id=coid, status="A")
        email_address = EmailAddress(mail=email, type="official", verified=True)
        role = CoPersonRole(cou_id=None, affiliation="member", status="A")
        name = Name(
            given=firstname, family=lastname, type="official", primary_name=True
        )
        return RegistryPerson(
            coperson_message=CoPersonMessage(
                CoPerson=coperson,
                EmailAddress=[email_address],
                CoPersonRole=[role],
                Name=[name],
            )
        )

    def as_coperson_message(self) -> CoPersonMessage:
        return self.__coperson_message

    @property
    def creation_date(self) -> Optional[datetime]:
        """Returns the creation date for this person in the registry.

        Will be None for person that is created locally.

        Returns:
          the creation date for this person. None if not set.
        """
        if not self.__coperson_message.co_person:
            return None
        if not self.__coperson_message.co_person.meta:
            return None

        return self.__coperson_message.co_person.meta.created

    @property
    def email_addresses(self) -> List[EmailAddress]:
        """Returns all email addresses for this person.

        This property provides access to the complete list of email addresses
        from COManage, regardless of type or verification status. Use this
        when you need to see all available emails.

        For selecting a single "best" email to use, see the email_address
        property which implements priority-based selection.

        Returns:
          List of all EmailAddress objects. Empty list if no emails exist.
        """
        if not self.__coperson_message.email_address:
            return []

        return self.__coperson_message.email_address

    @property
    def email_address(self) -> Optional[EmailAddress]:
        """Returns the primary email address for this person.

        Implements a priority-based selection strategy to choose the "best"
        email address from all available emails. This is the recommended
        property to use when you need a single email to contact a person.

        Priority Hierarchy:
          1. Organizational email (from claimed OrgIdentity) - most authoritative
          2. Official email (type="official") - designated by administrators
          3. Verified email (verified=True) - confirmed by the user
          4. Any email (first available) - fallback option
          5. None (no emails exist)

        The priority ensures we prefer emails that are more authoritative and
        verified over arbitrary email addresses.

        For access to all emails without priority filtering, use the
        email_addresses property instead.

        Returns:
          The highest priority EmailAddress if one exists. None if no emails.
        """
        # Priority 1: Organizational email
        if self.organization_email_addresses:
            return self.organization_email_addresses[0]

        # Priority 2: Official email
        if self.official_email_addresses:
            return self.official_email_addresses[0]

        # Priority 3: Verified email
        if self.verified_email_addresses:
            return self.verified_email_addresses[0]

        # Priority 4: Any email
        if self.__coperson_message.email_address:
            return self.__coperson_message.email_address[0]

        # Priority 5: None
        return None

    @property
    def primary_name(self) -> Optional[str]:
        """Returns the primary name of this person as a string.

        Concatenates firstname and lastname separated by a space.

        Returns:
          String representation of full primary name. None if there is none.
        """
        if not self.__coperson_message.name:
            return None

        for name in self.__coperson_message.name:
            if name.primary_name:
                return f"{name.given} {name.family}"

        return None

    def has_email(self, email: str) -> bool:
        """Indicates whether this person has the email address.

        Args:
          email: the email address
        Returns:
          True if this person has the email address. False, otherwise.
        """
        if not self.email_addresses:
            return False

        email_addresses = [
            address for address in self.email_addresses if email == address.mail
        ]
        return bool(email_addresses)

    def is_active(self) -> bool:
        """Indicates whether the CoPerson record is active.

        A person is considered active if their CoPerson status is "A" (active).
        Inactive persons may have status "D" (deleted), "S" (suspended), or
        other non-active statuses.

        Active status is one of the requirements for a claimed account.

        Returns:
          True if the CoPerson status is "A" (active). False otherwise.
        """
        if self.__coperson_message.co_person is None:
            return False

        return self.__coperson_message.co_person.status == "A"

    def identifiers(
        self, predicate: Callable[[Identifier], bool] = lambda x: True
    ) -> List[Identifier]:
        """Returns the list of identifiers for this CoPerson.

        If a predicate is given, returns the identifiers satisfying the predicate.
        Default predicate includes all identifiers.

        Args:
          predicate: a function indicating identifiers to include
        Returns:
          the list of identifiers satisfying the predicate
        """
        if self.__coperson_message.identifier is None:
            return []

        return [
            identifier
            for identifier in self.__coperson_message.identifier
            if predicate(identifier)
        ]

    def org_identities(
        self, predicate: Callable[[OrgIdentity], bool] = lambda x: True
    ) -> List[OrgIdentity]:
        """Returns the list of organizational identities for this CoPerson.

        If a predicate is given, returns the org identities satisfying the predicate.
        Default predicate includes all org identities.

        Args:
          predicate: a function indicating org identities to include
        Returns:
          the list of org identities satisfying the predicate
        """
        if self.__coperson_message.org_identity is None:
            return []

        return [
            org_identity
            for org_identity in self.__coperson_message.org_identity
            if predicate(org_identity)
        ]

    def is_claimed(self) -> bool:
        """Indicates whether the CoPerson record is claimed.

        A claimed account represents a person who has successfully logged in
        and verified their identity. This is determined by checking three
        conditions that must ALL be true:

        1. **Active Status**: The person must be active (status="A")
        2. **Verified Email**: Must have at least one verified email address
        3. **OIDC Identifier**: Must have an oidcsub identifier from cilogon.org

        The oidcsub identifier is created when a user logs in through the
        identity provider (CILogon), indicating they have claimed their account.
        The verified email requirement ensures we can reliably contact them.

        Use this method to distinguish between:
        - Provisioned accounts (created but never logged in)
        - Claimed accounts (user has logged in and verified)

        Returns:
          True if all three conditions are met. False otherwise.
        """
        if not self.is_active():
            return False

        if not self.verified_email_addresses:
            return False

        identifiers = self.identifiers(
            predicate=lambda identifier: identifier.type == "oidcsub"
            and identifier.identifier.startswith("http://cilogon.org")
        )
        return bool(identifiers)

    def __get_claim_org(self) -> Optional[OrgIdentity]:
        """Returns the first claimed organizational identity.

        Returns:
          The first claimed organization identity if there is one. None, otherwise.
        """
        if not self.__coperson_message.org_identity:
            return None

        for org_identity in self.__coperson_message.org_identity:
            if not org_identity.identifier:
                continue

            for identifier in org_identity.identifier:
                if identifier.type == "oidcsub" and identifier.login:
                    return org_identity

        return None

    @property
    def organization_email_addresses(self) -> List[EmailAddress]:
        """Returns emails from the claimed organizational identity.

        Organizational emails are associated with a claimed OrgIdentity,
        which represents the person's affiliation with an organization.
        These are considered the most authoritative emails.

        An organizational identity is "claimed" if it has an oidcsub
        identifier with login=True, indicating the user logged in using
        that organizational identity.

        Returns:
          List of EmailAddress objects from the claimed org identity.
          Empty list if no claimed org identity or no emails in it.
        """
        org_identity = self.__get_claim_org()
        if not org_identity:
            return []
        if not org_identity.email_address:
            return []

        return org_identity.email_address

    @property
    def official_email_addresses(self) -> List[EmailAddress]:
        """Returns all emails with type='official'.

        Filters the email addresses to return only those marked as official.
        Preserves the order from COManage.

        Returns:
          List of official email addresses. Empty list if no official emails exist.
        """
        return [addr for addr in self.email_addresses if addr.type == "official"]

    @property
    def verified_email_addresses(self) -> List[EmailAddress]:
        """Returns all emails with verified=True.

        Filters the email addresses to return only those marked as verified.
        Preserves the order from COManage.

        Returns:
          List of verified email addresses. Empty list if no verified emails exist.
        """
        return [addr for addr in self.email_addresses if addr.verified]

    def registry_id(self) -> Optional[str]:
        """Returns the registry ID for the person.

        Returns:
          the registry ID for the person
        """
        if not self.__coperson_message.identifier:
            return None

        for identifier in self.__coperson_message.identifier:
            if identifier.type == "naccid" and identifier.status == "A":
                return identifier.identifier

        return None


class UserRegistry:
    """Repository class for COManage user registry."""

    def __init__(self, api_instance: DefaultApi, coid: int):
        self.__api_instance = api_instance
        self.__coid = coid
        self.__registry_map: Dict[str, List[RegistryPerson]] = {}
        self.__bad_claims: Dict[str, List[RegistryPerson]] = {}
        self.__registry_map_by_id: Dict[str, RegistryPerson] = {}

    @property
    def coid(self) -> int:
        """Returns the community ID (coid).

        Returns:
          the coid for the registry
        """
        return self.__coid

    def add(self, person: RegistryPerson) -> List[Identifier]:
        """Creates a CoPerson record in the registry with name and email.

        Args:
          person: the person to add
        Returns:
          a list of CoManage Identifier objects
        """

        try:
            return self.__api_instance.add_co_person(
                coid=self.__coid, co_person_message=person.as_coperson_message()
            )
        except ApiException as error:
            raise RegistryError(f"API add_co_person call failed: {error}") from error

    def get(self, email: str) -> List[RegistryPerson]:
        """Returns the list of person objects with the email address.

        Args:
          email: the email address
        Returns:
          the list of person objects with the email address
        """
        if not self.__registry_map:
            self.__list()

        return self.__registry_map[email]

    def find_by_registry_id(self, registry_id: str) -> Optional[RegistryPerson]:
        """Returns the registry person object with matching registry id.

        Args:
          registry_id: the registry id

        Returns:
          the registry person objects if a match found, else None
        """

        if not self.__registry_map_by_id:
            self.__list()

        return self.__registry_map_by_id.get(registry_id)

    def has_bad_claim(self, name: str) -> bool:
        """Returns true if a RegistryPerson with the primary name has an
        incomplete claim.

        A claim is incomplete if it does not have a corresponding email address.

        Args:
          name: the registry person name
        Returns:
          True if the name corresponds to an incomplete claim
        """
        if not self.__registry_map:
            self.__list()

        return name in self.__bad_claims

    def get_bad_claim(self, name: str) -> List[RegistryPerson]:
        """Returns the list of RegistryPerson objects with incomplete claims
        for the given name.

        Args:
          name: the registry person name
        Returns:
          the list of RegistryPerson objects with incomplete claims, empty list if none
        """
        if not self.__registry_map:
            self.__list()

        return self.__bad_claims.get(name, [])

    def __list(self) -> None:
        """Returns the dictionary of RegistryPerson objects for records in the
        comanage registry.

        Dictionary maps from an email address to a list of person objects with
        the email address.

        Returns:
          the dictionary of email addresses RegistryPerson objects
        """
        self.__registry_map = defaultdict(list)
        self.__bad_claims = defaultdict(list)
        self.__registry_map_by_id = {}

        limit = 100
        page_index = 1

        remaining_count = self.__person_count()

        while remaining_count > 0:
            try:
                response = self.__api_instance.get_co_person(
                    coid=self.__coid, direction="asc", limit=limit, page=page_index
                )
            except ApiException as error:
                raise RegistryError(
                    f"API get_co_person call failed: {error}"
                ) from error

            person_list = self.__parse_response(response)

            remaining_count -= len(person_list)
            page_index += 1

            for person in person_list:
                self.__add_person(person)

    def __add_person(self, person: RegistryPerson) -> None:
        """Adds the person from the comanage registry to this registry object.

        To be added the person must have email addresses and be claimed.
        """
        if not person.email_addresses:
            if not person.is_claimed():
                return

            name = person.primary_name
            if name:
                self.__bad_claims[name].append(person)

            return

        for address in person.email_addresses:
            self.__registry_map[address.mail].append(person)

        registry_id = person.registry_id()
        if registry_id:
            self.__registry_map_by_id[registry_id] = person

    def __person_count(self) -> int:
        """Returns the count of coperson objects in the comanage registry.

        Raises:
          RegistryError if there is an API error
        """
        try:
            response = self.__api_instance.get_co_person(coid=self.__coid)
        except ApiException as error:
            raise RegistryError(f"Failed to read person count: {error}") from error

        if not response.total_results:
            return 0

        return int(response.total_results)

    def __parse_response(self, response: CoPersonResponse) -> List[RegistryPerson]:
        """Collects the CoPersonMessages from the response object and creates a
        list of RegistryPerson objects.

        The response object has the first person object in response.var_0 as a
        CoPersonMessage. If there are more person objects, they are in the
        additional_properties as dictionary objects and have to be loaded
        as CoPersonMessage objects using Pydantic model_validate.

        Args:
          the response object
        Returns:
          the list of registry person objects
        """
        person_list: List[RegistryPerson] = []
        if response.var_0:
            person_list.append(RegistryPerson(response.var_0))

        if response.additional_properties:
            for message_object in response.additional_properties.values():
                try:
                    person = RegistryPerson(
                        CoPersonMessage.model_validate(message_object)
                    )
                except ValidationError as error:
                    raise RegistryError(
                        f"Error parsing registry response: {error}"
                    ) from error

                person_list.append(person)

        return person_list


class RegistryError(Exception):
    pass
