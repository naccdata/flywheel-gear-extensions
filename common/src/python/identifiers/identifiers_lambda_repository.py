"""Identifiers repository using AWS Lambdas."""

from typing import List, Literal, Optional, overload

from identifiers.identifiers_repository import (IdentifierRepository,
                                                IdentifierRepositoryError)
from identifiers.model import (CenterIdentifiers, IdentifierList,
                               IdentifierObject)
from lambdas.lambda_function import (BaseRequest, LambdaClient,
                                     LambdaInvocationError)
from pydantic import BaseModel, Field


class ListRequest(BaseRequest):
    """Model for requests that could result in a list."""
    offset: int = 0
    limit: int = Field(le=100)


class IdentifierRequest(BaseRequest, CenterIdentifiers):
    """Request model for creating Identifier."""


class IdentifierListRequest(BaseRequest):
    """Model for request to lambda."""
    identifiers: List[CenterIdentifiers]


class ADCIDRequest(ListRequest):
    """Model for request object with ADCID, and offset and limit."""
    adcid: int = Field(ge=0)


class NACCIDRequest(BaseRequest):
    """Request model for search by NACCID."""
    naccid: str = Field(min_length=10, pattern=r"^NACC\d{6}$")


class ListResponseObject(BaseModel):
    """Model for return object with partial list of Identifiers."""
    offset: int
    limit: int
    data: List[IdentifierObject]


IdentifiersMode = Literal['dev', 'prod']


class IdentifiersLambdaRepository(IdentifierRepository):
    """Implementation of IdentifierRepository based on AWS Lambdas."""

    def __init__(self, client: LambdaClient, mode: IdentifiersMode) -> None:
        self.__client = client
        self.__mode: Literal['dev', 'prod'] = mode

    def create(self, adcid: int, ptid: str) -> IdentifierObject:
        """Creates an Identifier in the repository.

        Args:
          adcid: the ADCID
          ptid: the participant ID
        Returns:
          The created Identifier
        Raises:
          IdentifierRepositoryError if an error occurs creating the identifier
        """
        try:
            response = self.__client.invoke(
                name='create-identifier-lambda-function',
                request=IdentifierRequest(mode=self.__mode,
                                          adcid=adcid,
                                          ptid=ptid))
        except LambdaInvocationError as error:
            raise IdentifierRepositoryError(error) from error
        if response.statusCode != 200 and response.statusCode != 201:
            raise IdentifierRepositoryError("No identifier created")

        return IdentifierObject.model_validate_json(response.body)

    def create_list(self,
                    identifiers: List[CenterIdentifiers]) -> IdentifierList:
        """Creates several Identifiers in the repository.

        Args:
          identifiers: list of identifiers requests
        Returns:
           list of Identifier objects
        Raises:
          IdentifierRepositoryError if an error occurs creating the identifier
        """
        try:
            response = self.__client.invoke(
                name='create-identifier-list-lambda-function',
                request=IdentifierListRequest(mode=self.__mode,
                                              identifiers=identifiers))
        except LambdaInvocationError as error:
            raise IdentifierRepositoryError(error) from error
        if response.statusCode != 200:
            raise IdentifierRepositoryError("No identifier created")

        return IdentifierList.model_validate_json(response.body)

    @overload
    def get(self, *, naccid: str) -> IdentifierObject:
        ...

    # pylint: disable=(arguments-differ)
    @overload
    def get(self, *, guid: str) -> IdentifierObject:
        ...

    # pylint: disable=(arguments-differ)
    @overload
    def get(self, *, adcid: int, ptid: str) -> IdentifierObject:
        ...

    # pylint: disable=(arguments-differ)
    def get(self,
            naccid: Optional[str] = None,
            adcid: Optional[int] = None,
            ptid: Optional[str] = None,
            guid: Optional[str] = None) -> Optional[IdentifierObject]:
        """Returns IdentifierObject object for the IDs given.

        Note: some valid arguments can be falsey.
        These are explicitly checked that they are not None.

        Args:
          naccid: the (integer part of the) NACCID
          adcid: the center ID
          ptid: the participant ID assigned by the center
        Returns:
          the IdentifierObject for the nacc_id or the adcid-ptid pair
        Raises:
          NoMatchingIdentifier: if no Identifier record was found
          TypeError: if the arguments are nonsensical
        """
        if naccid is not None:
            try:
                response = self.__client.invoke(
                    name='identifier-naccid-lambda-function',
                    request=NACCIDRequest(mode=self.__mode, naccid=naccid))
            except LambdaInvocationError as error:
                raise IdentifierRepositoryError(error) from error

            if response.statusCode == 200:
                return IdentifierObject.model_validate_json(response.body)
            if response.statusCode == 404:
                return None

            raise IdentifierRepositoryError(response.body)

        if adcid is not None and ptid:
            try:
                response = self.__client.invoke(
                    name='Identifier-ADCID-PTID-Lambda-Function',
                    request=IdentifierRequest(mode=self.__mode,
                                              adcid=adcid,
                                              ptid=ptid))
            except LambdaInvocationError as error:
                raise IdentifierRepositoryError(error) from error

            if response.statusCode == 200:
                return IdentifierObject.model_validate_json(response.body)
            if response.statusCode == 404:
                return None

            raise IdentifierRepositoryError(response.body)

        raise TypeError("Invalid arguments")

    @overload
    def list(self, adcid: int) -> List[IdentifierObject]:
        ...

    @overload
    def list(self) -> List[IdentifierObject]:
        ...

    def list(self, adcid: Optional[int] = None) -> List[IdentifierObject]:
        """Returns the list of all identifiers in the repository.

        If an ADCID is given filters identifiers by the center.

        Args:
          adcid: the ADCID used for filtering

        Returns:
          List of all identifiers in the repository
        """
        if adcid is None:
            # TODO: this is not implemented by lambda
            return []

        identifier_list: List[IdentifierObject] = []
        index = 0
        limit = 100
        read_length = limit
        while read_length == limit:
            try:
                response = self.__client.invoke(
                    name='identifier-adcid-lambda-function',
                    request=ADCIDRequest(mode=self.__mode,
                                         adcid=adcid,
                                         offset=index,
                                         limit=limit))
            except LambdaInvocationError as error:
                raise IdentifierRepositoryError(error) from error

            if response.statusCode != 200:
                raise IdentifierRepositoryError(response.body)

            response_object = ListResponseObject.model_validate_json(
                response.body)
            identifier_list += response_object.data
            read_length = len(response_object.data)
            index += limit

        return identifier_list
