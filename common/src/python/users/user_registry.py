"""Defines repository as interface to user registry."""
from datetime import datetime
from typing import List, Optional

from coreapi_client.api.default_api import DefaultApi
from coreapi_client.exceptions import ApiException
from coreapi_client.models.co_person import CoPerson
from coreapi_client.models.co_person_message import CoPersonMessage
from coreapi_client.models.co_person_role import CoPersonRole
from coreapi_client.models.email_address import EmailAddress
from coreapi_client.models.identifier import Identifier
from coreapi_client.models.name import Name

from users.user_metadata import PersonInfo, RegistryMetadataManager


class RegistryPerson:
    """Wrapper for COManage CoPersonMessage object.

    Enables predicates needed for processing.
    """

    def __init__(self, coperson: CoPersonMessage,
                 create_date: datetime) -> None:
        self.__coperson = coperson
        self.__create_date = create_date

    @classmethod
    def create(cls, *, firstname: str, lastname: str, email: str,
               coid: str) -> 'RegistryPerson':
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
        email_address = EmailAddress(mail=email,
                                     type="official",
                                     verified=True)
        role = CoPersonRole(cou_id=None, affiliation="member", status="A")
        name = Name(given=firstname,
                    family=lastname,
                    type="official",
                    primary_name=True)
        return RegistryPerson(coperson=CoPersonMessage(
            CoPerson=coperson,
            EmailAddress=[email_address],
            CoPersonRole=[role],
            Name=[name]),
                              create_date=datetime.now())

    def as_coperson_message(self) -> CoPersonMessage:
        return self.__coperson

    @property
    def creation_date(self) -> datetime:
        return self.__create_date

    @property
    def email_address(self) -> Optional[List[EmailAddress]]:
        return self.__coperson.email_address

    def is_claimed(self) -> bool:
        """Indicates whether the CoPerson record is claimed.

        The record is claimed if there is an OrgIdentity that has an
        Identifier with type "oidcsub" and login True.

        Returns:
          True if the record has been claimed. False, otherwise.
        """
        if not self.__coperson.org_identity:
            return False

        for org_identity in self.__coperson.org_identity:
            if not org_identity.identifier:
                return False

            for identifier in org_identity.identifier:
                if identifier.type == "oidcsub" and identifier.login:
                    return True

        return False

    def registry_id(self) -> Optional[str]:
        """Returns the registry ID for the person.

        Returns:
          the registry ID for the person
        """
        if not self.__coperson.identifier:
            return None

        for identifier in self.__coperson.identifier:
            if identifier.type == "naccid" and identifier.status == "A":
                return identifier.identifier

        return None


class UserRegistry:
    """Repository class for COManage user registry."""

    def __init__(self, api_instance: DefaultApi,
                 metadata_manager: RegistryMetadataManager, coid: int):
        self.__api_instance = api_instance
        self.__metadata_manager = metadata_manager
        self.__coid = coid

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
            identifiers = self.__api_instance.add_co_person(
                coid=self.__coid,
                co_person_message=person.as_coperson_message())
        except ApiException as error:
            raise RegistryError(f"API call failed: {error}")

        assert person.email_address, "person objects are created with email"
        self.__metadata_manager.add(
            PersonInfo(email=person.email_address[0].mail,
                       creation_date=person.creation_date))
        return identifiers

    def list(self, email: str) -> List[RegistryPerson]:
        """Returns the list of CoPersonMessage objects with the email.

        Args:
          the email address
        Returns:
          the list of CoPersonMessage objects with the email address
        """
        person_info = self.__metadata_manager.get(email=email)
        if not person_info:
            raise RegistryError(
                f"No creation date for registry person {email}")

        limit = 100
        page_index = 0
        read_length = limit

        result = []
        while read_length == limit:
            try:
                response = self.__api_instance.get_co_person(coid=self.__coid,
                                                             direction='asc',
                                                             limit=limit,
                                                             page=page_index)
            except ApiException as error:
                raise RegistryError(f"API call failed: {error}")

            coperson_dict = response.to_dict()
            read_length = len(coperson_dict.keys())
            page_index += 1

            person_list = UserRegistry.create_person_objects(
                coperson_dict, creation_date=person_info.creation_date)
            for person in person_list:
                if not person.email_address:
                    continue

                email_addresses = [
                    address for address in person.email_address
                    if email == address.mail
                ]
                if not email_addresses:
                    continue

                result.append(person)

        return result

    @classmethod
    def create_person_objects(cls, coperson_dict,
                              creation_date: datetime) -> List[RegistryPerson]:
        """Extracts RegistryPerson objects from the response dict.

        Args:
          coperson_dict: the dictionary response from get_co_person
        Returns:
          the list of RegistryPerson objects in the dict
        """
        result = []
        for person_message in coperson_dict.values():
            coperson = CoPersonMessage.from_dict(person_message)
            if not coperson:
                continue

            result.append(RegistryPerson(coperson, create_date=creation_date))

        return result


class RegistryError(Exception):
    pass
