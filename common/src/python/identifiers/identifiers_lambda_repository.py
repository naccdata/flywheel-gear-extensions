"""Identifiers repository using AWS Lambdas."""

from typing import List, Literal, Optional, overload

from lambdas.lambda_function import BaseRequest, LambdaClient, LambdaInvocationError
from pydantic import BaseModel, Field, ValidationError

from identifiers.identifiers_repository import (
    IdentifierQueryObject,
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import (
    GUID_PATTERN,
    NACCID_PATTERN,
    CenterIdentifiers,
    IdentifierList,
    IdentifierObject,
)


class ListRequest(BaseRequest):
    """Model for requests that could result in a list."""
    offset: int = 0
    limit: int = Field(le=100)


class IdentifierRequest(BaseRequest, CenterIdentifiers):
    """Request model for creating Identifier."""
    guid: Optional[str] = Field(None, max_length=13, pattern=GUID_PATTERN)


class IdentifierListRequest(BaseRequest):
    """Model for request to lambda."""
    identifiers: List[IdentifierQueryObject]


class ADCIDRequest(ListRequest):
    """Model for request object with ADCID, and offset and limit."""
    adcid: int = Field(ge=0)


class GUIDRequest(BaseRequest):
    """Request model for search by GUID."""
    guid: str = Field(max_length=13, pattern=GUID_PATTERN)


class NACCIDRequest(BaseRequest):
    """Request model for search by NACCID."""
    naccid: str = Field(max_length=10, pattern=NACCID_PATTERN)


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

    def create(self, adcid: int, ptid: str,
               guid: Optional[str]) -> IdentifierObject:
        """Creates an Identifier in the repository.

        Args:
          adcid: the ADCID
          ptid: the participant ID
          guid: the NIA GUID
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
                                          ptid=ptid,
                                          guid=guid))
        except (LambdaInvocationError, ValidationError) as error:
            raise IdentifierRepositoryError(error) from error

        if response.statusCode not in (200, 201):
            raise IdentifierRepositoryError("No identifier created")

        return IdentifierObject.model_validate_json(response.body)

    def create_list(
            self, identifiers: List[IdentifierQueryObject]) -> IdentifierList:
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
          guid: the NIA GUID
        Returns:
          the IdentifierObject for the nacc_id or the adcid-ptid pair
        Raises:
          IdentifierRepositoryError: if no Identifier record was found
          TypeError: if the arguments are nonsensical
        """
        if naccid is not None:
            return self.__get_by_naccid(naccid)

        if adcid is not None and ptid:
            return self.__get_by_ptid(adcid=adcid, ptid=ptid, guid=guid)

        if guid:
            return self.__get_by_guid(guid)

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
        Raises:
          IdentifierRepositoryError if the lambda invocation has an error
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

    def __get_by_naccid(self, naccid: str) -> Optional[IdentifierObject]:
        """Returns the IdentifierObject for the NACCID.

        Args:
          naccid: the (integer part of the) NACCID
        Returns:
          the IdentifierObject for the naccid
        Raises:
          IdentifierRepositoryError if no Identifier record was found
        """
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

    def __get_by_ptid(self, *, adcid: int, ptid: str,
                      guid: Optional[str]) -> Optional[IdentifierObject]:
        """Returns the IdentifierObject for the NACCID.

        Args:
          adcid: the center ID
          ptid: the participant ID assigned by the center
          guid: the NIA GUID
        Returns:
          the IdentifierObject for the ptid
        Raises:
          IdentifierRepositoryError if no Identifier record was found
        """
        try:
            response = self.__client.invoke(
                name='Identifier-ADCID-PTID-Lambda-Function',
                request=IdentifierRequest(mode=self.__mode,
                                          adcid=adcid,
                                          ptid=ptid,
                                          guid=guid))
        except (LambdaInvocationError, ValidationError) as error:
            raise IdentifierRepositoryError(error) from error

        if response.statusCode == 200:
            return IdentifierObject.model_validate_json(response.body)
        if response.statusCode == 404:
            return None

        raise IdentifierRepositoryError(response.body)

    def __get_by_guid(self, guid: str) -> Optional[IdentifierObject]:
        """Returns the IdentifierObject for the GUID.

        Args:
          guid: the NIA GUID
        Returns:
          the IdentifierObject for the guid
        Raises:
          IdentifierRepositoryError if no Identifier record was found
        """
        try:
            response = self.__client.invoke(
                name='identifier-guid-lambda-function',
                request=GUIDRequest(mode=self.__mode, guid=guid))
        except LambdaInvocationError as error:
            raise IdentifierRepositoryError(error) from error

        if response.statusCode == 200:
            return IdentifierObject.model_validate_json(response.body)
        if response.statusCode == 404:
            return None

        raise IdentifierRepositoryError(response.body)
