"""Defines repository as interface to user registry."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Union

from coreapi_client.api.default_api import DefaultApi
from coreapi_client.exceptions import ApiException
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.co_person_role import CoPersonRole
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.get_co_person200_response import (
    GetCoPerson200Response as CoPersonResponse,
)
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.name import Name
from coreapi_client.models.org_identity import OrgIdentity
from pydantic import ValidationError

from users.domain_config import (
    DomainRelationshipConfig,
    canonicalize_domain,
)

log = logging.getLogger(__name__)


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
        cls,
        *,
        firstname: str,
        lastname: str,
        email: "Union[str, List[str]]",
        coid: int,
    ) -> "RegistryPerson":
        """Creates a RegistryPerson object with the name and email(s).

        Note: the coid must match that of the registry.
        Accepts a single email string (backward compatible) or a list of
        email strings. Each email produces an EmailAddress with type="official".

        Args:
          firstname: the first (given) name of person
          lastname: the last (family) name of the person
          email: a single email address or list of email addresses
          coid: the CO ID for the COManage registry
        Returns:
          the RegistryPerson with name and email(s)
        """
        # Strip whitespace from names to ensure consistency with registry
        firstname = firstname.strip() if isinstance(firstname, str) else firstname
        lastname = lastname.strip() if isinstance(lastname, str) else lastname

        # Normalize single string to list for uniform handling
        email_list = [email] if isinstance(email, str) else email

        coperson = CoPerson(co_id=coid, status="A")
        email_addresses = [
            EmailAddress(mail=addr, type="official", verified=True)
            for addr in email_list
        ]
        role = CoPersonRole(cou_id=None, affiliation="member", status="A")
        name = Name(
            given=firstname, family=lastname, type="official", primary_name=True
        )
        return RegistryPerson(
            coperson_message=CoPersonMessage(
                CoPerson=coperson,
                EmailAddress=email_addresses,
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
        Strips whitespace from individual name components to normalize names
        that may have been stored with trailing spaces.

        Returns:
          String representation of full primary name. None if there is none.
        """
        if not self.__coperson_message.name:
            return None

        for name in self.__coperson_message.name:
            if name.primary_name:
                # Strip whitespace from name components for consistency
                given = name.given.strip() if name.given else ""
                family = name.family.strip() if name.family else ""
                return f"{given} {family}"

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

    def is_suspended(self) -> bool:
        """Indicates whether the CoPerson record is suspended.

        A person is considered suspended if their CoPerson status is "S"
        (suspended). Suspended status removes the user from the
        CO:members:active group, revoking OIDC authorization.

        Returns:
          True if the CoPerson status is "S" (Suspended). False otherwise.
        """
        if self.__coperson_message.co_person is None:
            return False

        return self.__coperson_message.co_person.status == "S"

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

    def _has_oidcsub(self) -> bool:
        """Check whether the record has any oidcsub identifier from
        cilogon.org.

        Returns:
          True if the record has at least one oidcsub identifier from cilogon.org.
        """

        def is_cilogon_oidcsub(identifier: Identifier) -> bool:
            return identifier.type == "oidcsub" and identifier.identifier.startswith(
                "http://cilogon.org"
            )

        return bool(self.identifiers(predicate=is_cilogon_oidcsub))

    def is_incomplete_claim(self) -> bool:
        """Indicates whether the CoPerson record is an incomplete claim.

        An incomplete claim represents a user who logged in via an IdP
        (has an oidcsub identifier) but the IdP did not return an email
        address, so the record has no verified email.

        Returns:
          True if the record has an oidcsub identifier but no verified email.
          False otherwise.
        """
        return self._has_oidcsub() and not self.verified_email_addresses

    def is_unclaimed(self) -> bool:
        """Indicates whether the CoPerson record is unclaimed.

        An unclaimed record has no oidcsub identifier, meaning the user
        has never logged in to claim their account.

        Returns:
          True if the record has no oidcsub identifier. False otherwise.
        """
        return not self._has_oidcsub()

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


@dataclass
class DomainCandidate:
    """A candidate record found via domain-aware lookup."""

    person: RegistryPerson
    matched_email: str
    query_domain: str
    candidate_domain: str
    parent_domain: str


class UserRegistry:
    """Repository class for COManage user registry."""

    def __init__(
        self,
        api_instance: DefaultApi,
        coid: int,
        name_normalizer: Callable[[str], str],
        domain_config: Optional[DomainRelationshipConfig] = None,
        dry_run: bool = False,
    ):
        self.__api_instance = api_instance
        self.__coid = coid
        self.__loaded = False
        self.__registry_map: Dict[str, List[RegistryPerson]] = {}
        self.__bad_claims: Dict[str, List[RegistryPerson]] = {}
        self.__registry_map_by_id: Dict[str, RegistryPerson] = {}
        self.__parent_domain_map: Dict[str, List[RegistryPerson]] = {}
        self.__name_map: Dict[str, List[RegistryPerson]] = {}
        self.__domain_config = domain_config or DomainRelationshipConfig()
        self.__name_normalizer = name_normalizer
        self.__dry_run = dry_run

    @property
    def dry_run(self) -> bool:
        """Returns whether dry-run mode is enabled.

        When dry-run mode is enabled, write operations (suspend, re-enable)
        are logged but not executed against the COmanage API.

        Returns:
          True if dry-run mode is enabled. False otherwise.
        """
        return self.__dry_run

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

    def suspend(self, registry_id: str) -> None:
        """Suspend a CO Person by setting status to 'S'.

        Retrieves the full CoPersonMessage, sets CoPerson.status to 'S',
        and PUTs the entire record back. In dry-run mode, logs the
        intended action without calling PUT.

        Args:
            registry_id: the NACC registry ID (naccid identifier)

        Raises:
            RegistryError: if the person cannot be found, has no registry ID,
                          or the API call fails
        """
        self.__update_status(registry_id, "S")

    def re_enable(self, registry_id: str) -> None:
        """Re-enable a suspended CO Person by setting status to 'A'.

        Retrieves the full CoPersonMessage, sets CoPerson.status to 'A',
        and PUTs the entire record back. In dry-run mode, logs the
        intended action without calling PUT.

        Args:
            registry_id: the NACC registry ID (naccid identifier)

        Raises:
            RegistryError: if the person cannot be found or the API call fails
        """
        self.__update_status(registry_id, "A")

    def __get_person_message(self, registry_id: str) -> CoPersonMessage:
        """Retrieve the full CoPersonMessage for a registry ID via GET.

        Uses the DefaultApi.get_co_person with the identifier parameter
        to fetch a single record.

        Args:
            registry_id: the NACC registry ID

        Returns:
            The full CoPersonMessage

        Raises:
            RegistryError: if the API call fails or no record is found
        """
        try:
            response = self.__api_instance.get_co_person(
                coid=self.__coid, identifier=registry_id
            )
        except ApiException as error:
            raise RegistryError(f"API get_co_person call failed: {error}") from error

        if not response.var_0:
            raise RegistryError(
                f"No COmanage record found for registry ID {registry_id}"
            )

        return response.var_0

    def __update_status(self, registry_id: str, target_status: str) -> None:
        """Retrieve the full CoPersonMessage, change only the status, PUT it
        back.

        Args:
            registry_id: the NACC registry ID
            target_status: the target CoPerson status ('S' or 'A')

        Raises:
            RegistryError: on API errors or missing records
        """
        if not registry_id:
            raise RegistryError("Cannot update person: no registry ID")

        person_message = self.__get_person_message(registry_id)

        if not person_message.co_person:
            raise RegistryError(
                f"No CoPerson object in record for registry ID {registry_id}"
            )

        person_message.co_person.status = target_status

        if self.__dry_run:
            log.info(
                "DRY RUN: Would update registry ID %s to status %s",
                registry_id,
                target_status,
            )
            return

        try:
            self.__api_instance.update_co_person(
                coid=self.__coid,
                identifier=registry_id,
                co_person_message=person_message,
            )
        except ApiException as error:
            raise RegistryError(f"API update_co_person call failed: {error}") from error

    def get(self, email: str) -> List[RegistryPerson]:
        """Returns the list of person objects with the email address.

        Args:
          email: the email address
        Returns:
          the list of person objects with the email address
        """
        if not self.__loaded:
            self.__list()

        return self.__registry_map[email]

    def find_by_registry_id(self, registry_id: str) -> Optional[RegistryPerson]:
        """Returns the registry person object with matching registry id.

        Args:
          registry_id: the registry id

        Returns:
          the registry person objects if a match found, else None
        """

        if not self.__loaded:
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
        if not self.__loaded:
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
        if not self.__loaded:
            self.__list()

        return self.__bad_claims.get(name, [])

    def get_by_parent_domain(self, email: str) -> List[DomainCandidate]:
        """Fallback lookup: find candidates sharing the same parent domain.

        Extracts the domain from the query email, resolves its parent domain
        via the DomainRelationshipConfig, and returns all RegistryPerson
        records indexed under that parent domain with match context.

        Args:
          email: the query email address
        Returns:
          list of DomainCandidate objects with match context
        """
        if not self.__loaded:
            self.__list()

        if "@" not in email:
            return []

        query_domain = canonicalize_domain(email.split("@")[-1])
        query_parent = self.__domain_config.resolve_parent(query_domain)

        candidates = self.__parent_domain_map.get(query_parent, [])
        results: List[DomainCandidate] = []
        seen: set[str] = set()

        for person in candidates:
            person_key = person.registry_id() or str(id(person))
            if person_key in seen:
                continue
            seen.add(person_key)

            for addr in person.email_addresses:
                addr_domain = (
                    canonicalize_domain(addr.mail.split("@")[-1])
                    if "@" in addr.mail
                    else ""
                )
                addr_parent = self.__domain_config.resolve_parent(addr_domain)
                if addr_parent == query_parent:
                    results.append(
                        DomainCandidate(
                            person=person,
                            matched_email=addr.mail,
                            query_domain=query_domain,
                            candidate_domain=addr_domain,
                            parent_domain=query_parent,
                        )
                    )
                    break

        return results

    def get_by_name(self, full_name: str) -> List[RegistryPerson]:
        """Lookup candidates by normalized full name.

        Args:
          full_name: the full name to search for
        Returns:
          list of RegistryPerson objects with matching normalized name
        """
        if not self.__loaded:
            self.__list()

        normalized = self.__name_normalizer(full_name)
        return self.__name_map.get(normalized, [])

    def __list(self) -> None:
        """Returns the dictionary of RegistryPerson objects for records in the
        comanage registry.

        Dictionary maps from an email address to a list of person objects with
        the email address.

        Returns:
          the dictionary of email addresses RegistryPerson objects
        """
        self.__loaded = True
        self.__registry_map = defaultdict(list)
        self.__bad_claims = defaultdict(list)
        self.__registry_map_by_id = {}
        self.__parent_domain_map = defaultdict(list)
        self.__name_map = defaultdict(list)

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

        Indexes the person by registry ID (always), by email (if
        present), by parent domain (if domain_config available), and by
        name (if present). Records without email that are claimed go to
        __bad_claims.
        """
        # Always index by registry ID regardless of email
        registry_id = person.registry_id()
        if registry_id:
            self.__registry_map_by_id[registry_id] = person

        # Index by normalized name if present
        name = person.primary_name
        if name:
            try:
                normalized = self.__name_normalizer(name)
                if normalized:
                    self.__name_map.setdefault(normalized, []).append(person)
            except (TypeError, ValueError):
                log.warning(
                    "Name normalizer failed for '%s', skipping name index",
                    name,
                    exc_info=True,
                )

        if not person.email_addresses:
            if not person.is_claimed():
                return

            if name:
                self.__bad_claims[name].append(person)

            return

        for address in person.email_addresses:
            self.__registry_map[address.mail].append(person)

            # Index by parent domain
            email_domain = address.mail.split("@")[-1] if "@" in address.mail else ""
            if email_domain:
                parent = self.__domain_config.resolve_parent(email_domain)
                self.__parent_domain_map.setdefault(parent, []).append(person)

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
    """Error raised by UserRegistry operations."""
