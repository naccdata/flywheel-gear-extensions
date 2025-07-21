"""Defines repository as interface to user registry."""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from coreapi_client.api.default_api import DefaultApi
from coreapi_client.exceptions import ApiException
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.co_person_role import CoPersonRole
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.inline_object import InlineObject
from coreapi_client.models.name import Name
from coreapi_client.models.org_identity import OrgIdentity
from pydantic import ValidationError


class RegistryPerson:
    """Wrapper for COManage CoPersonMessage object.

    Enables predicates needed for processing.
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

    def has_matching_auth_email(self, auth_email: str) -> bool:
        """Check whether the auth email matches with the organization email
        that the registry entry was claimed.

        Args:
            auth_email: auth email provided in NACC directory

        Returns:
            bool: True if the auth emailed matches with org email
        """
        if not self.organization_email_addresses:
            return False

        for org_email in self.organization_email_addresses:
            if org_email.mail.lower() == auth_email.lower():
                return True

        return False

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
        if not self.__coperson_message.email_address:
            return []

        return self.__coperson_message.email_address

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

    def is_claimed(self) -> bool:
        """Indicates whether the CoPerson record is claimed.

        The record is claimed if there is an OrgIdentity that has an
        Identifier with type "oidcsub" and login True.

        Returns:
          True if the record has been claimed. False, otherwise.
        """
        return bool(self.__get_claim_org())

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
        """Returns the email from the first organizational identity."""
        org_identity = self.__get_claim_org()
        if not org_identity:
            return []
        if not org_identity.email_address:
            return []

        return org_identity.email_address

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

    def delete(self, registry_id: str) -> None:
        """Removes the person object with the registry ID.

        Args:
            registry_id the registry id for the person object
        """
        # TODO: confirm delete does what we want
        # self.__api_instance.delete_co_person(self.coid, registry_id)
        # self.__registry_map = {}
        # self.__bad_claims = {}

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

    def __parse_response(self, response: InlineObject) -> List[RegistryPerson]:
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
