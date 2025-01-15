"""Module for applying required transformations to an input visit record."""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

from dates.form_dates import DEFAULT_DATE_FORMAT, convert_date
from keys.keys import FieldNames
from outputs.errors import ErrorWriter, unexpected_value_error
from pydantic import BaseModel, RootModel

log = logging.getLogger(__name__)

ModuleName = str  # Literal['UDS', 'LBD']


class VersionMap(BaseModel):
    """Represents a mapping from an input record to the module version name for
    the record."""
    fieldname: str
    value_map: Dict[str, str] = {}
    default: str

    def apply(self, record: Dict[str, Any]) -> str:
        """Applies this map to determine the version."""
        field_value = record.get(self.fieldname)
        if field_value and field_value in self.value_map:
            return self.value_map.get(str(field_value))  # type: ignore

        return self.default


class FieldFilter(BaseModel):
    """Defines a map of form field names for different versions of the form."""
    version_map: VersionMap
    fields: Dict[str, List[str]] = {}

    def __unique_fields(self, version_name: str) -> Set[str]:
        """Finds the field names unique to the version.

        Args:
          version_name: the name of the form version
        Returns:
          the set of field names unique to the version
        """
        field_set = set(self.fields.get(version_name, set()))
        if not field_set:
            return field_set

        for key in self.fields:
            if key == version_name:
                continue

            key_fields = self.fields.get(key)
            if not key_fields:
                continue

            field_set = field_set.difference(set(key_fields))

        return field_set

    def apply(self, input_record: Dict[str, Any]) -> Dict[str, Any]:
        """Filters the input record by dropping the key-value pairs for fields
        unique to the version.

        Args:
          input_record: the record to filter
          version_name: the name of version for excluded fields
        Returns:
          the input_record without the keys for the excluded fields
        """
        version_name = self.version_map.apply(input_record)
        drop_fields = self.__unique_fields(version_name)
        if not drop_fields:
            return input_record

        return {
            field: value
            for field, value in input_record.items()
            if field not in drop_fields
        }


class FieldTransformations(RootModel):
    """Root model for the form field schema."""
    root: Dict[ModuleName, List[FieldFilter]] = {}  # noqa: RUF012

    def __getitem__(self, key: ModuleName) -> List[FieldFilter]:
        """Returns the FormField schema for the module.

        Args:
          key: the module name
        Returns:
          the FormFields object for the module
        """
        return self.root[key]

    def get(
            self,
            key: ModuleName,
            default: List[FieldFilter] = []  # noqa: B006
    ) -> List[FieldFilter]:
        return self.root.get(key, default)

    def __setitem__(self, key: ModuleName, value: List[FieldFilter]) -> None:
        """Sets the form field schema for a module.

        Args:
          key: the module name
          value: the form fields object
        """
        self.root[key] = value

    def add(self, key: ModuleName, value: FieldFilter) -> None:
        """Adds the filter to the filters for the module name.

        Args:
          key: the module name
          value: the field filter
        """
        if key not in self.root:
            self.root[key] = []

        self.root[key].append(value)


class BaseRecordTransformer(ABC):

    @abstractmethod
    def transform(self, input_record: Dict[str, Any],
                  line_num: int) -> Optional[Dict[str, Any]]:
        """Defines a transform on an input record.

        Args:
          input_record: the record to be transformed
          line_num: the line number of the record in the input
        Returns:
          the transformed record. None, if transform cannot be performed.
        """


class RecordTransformer(BaseRecordTransformer):
    """Defines a composition of transformers that are applied in sequence to
    the input record."""

    def __init__(self, transformers: List[BaseRecordTransformer]) -> None:
        self.__transformers = transformers

    def transform(self, input_record: Dict[str, Any],
                  line_num: int) -> Optional[Dict[str, Any]]:
        """Applies the transformers in sequence to the input record.

        If there are no transformers, returns the record untransformed.

        Args:
          input_record: the input record
          line_number: the line number of the input record

        Returns:
          the transformed record. None, if any transform returns None.
        """
        log.info('Transforming input record %s', line_num)

        record: Optional[Dict[str, Any]] = input_record
        for transformer in self.__transformers:
            if record is None:
                return None

            record = transformer.transform(record, line_num)

        return record


class DateTransformer(BaseRecordTransformer):
    """Defines a transformer that normalizes date fields."""

    def __init__(self, error_writer: ErrorWriter) -> None:
        """Initialize the CSV Transformer.

        Args:
            schema_file(optional): name of the transformation schema file
        """
        self._error_writer = error_writer

    def transform(self, input_record: Dict[str, Any],
                  line_num: int) -> Optional[Dict[str, Any]]:
        """Normalizes the date column of the record.

        Args:
            input_record: input record from CSV file
            line_num (int): line number in CSV file

        Returns:
            Transformed record or None if there's processing errors
        """
        if FieldNames.DATE_COLUMN not in input_record:
            return input_record

        normalized_date = convert_date(
            date_string=input_record[FieldNames.DATE_COLUMN],
            date_format=DEFAULT_DATE_FORMAT)  # type: ignore
        if not normalized_date:
            self._error_writer.write(
                unexpected_value_error(
                    field=FieldNames.DATE_COLUMN,
                    value=input_record[FieldNames.DATE_COLUMN],
                    expected='',
                    message='Expected a valid date string',
                    line=line_num))
            return None

        input_record[FieldNames.DATE_COLUMN] = normalized_date
        return input_record


class FilterTransformer(BaseRecordTransformer):
    """Defines a transform that applies a field filter to a record."""

    def __init__(self, field_filter: FieldFilter) -> None:
        self._transform = field_filter

    def transform(self, input_record: Dict[str, Any],
                  line_num: int) -> Optional[Dict[str, Any]]:
        """Applies the FieldFilter to the input record.

        Args:
          input_record: the input record
          line_num: the line number of the record in the input
        Returns:
          the record with fields filtered
        """
        return self._transform.apply(input_record)


class TransformerFactory:

    def __init__(self, transformations: FieldTransformations) -> None:
        self.__transformations = transformations

    def create(self, module: Optional[str],
               error_writer: ErrorWriter) -> RecordTransformer:
        """Creates a transformer for the module using the transformations in
        this object.

        If the module name is none or has no corresponding transforms, a
        transformer with just the date transformation is returned.

        Args:
          module: the module name
        Returns:
          the record transformer
        """
        transformer_list: List[BaseRecordTransformer] = []
        transformer_list.append(DateTransformer(error_writer))
        if module:
            filter_list = self.__transformations.get(module)
            for field_filter in filter_list:
                transformer_list.append(FilterTransformer(field_filter))

        return RecordTransformer(transformer_list)
