"""Module for applying required transformations to an input visit record."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional, Set

from configs.ingest_configs import ModuleConfigs
from keys.keys import SysErrorCodes
from nacc_common.data_identification import (
    DataIdentification,
)
from nacc_common.field_names import FieldNames
from nacc_common.form_dates import DEFAULT_DATE_FORMAT, convert_date
from outputs.error_writer import ErrorWriter
from outputs.errors import preprocessing_error, unexpected_value_error
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


class Transformation(BaseModel, ABC):
    """Base class for transformations applied to an input record."""

    nofill: bool = True

    @abstractmethod
    def apply(
        self,
        input_record: Dict[str, Any],
        error_writer: ErrorWriter,
        line_num: int,
        module_configs: ModuleConfigs,
    ) -> Optional[Dict[str, Any]]:
        """Applies this transformation to the input record.

        Args:
          input_record: the record to transform
          error_writer: error metadata writer
          line_num: line number in the input CSV
          module_configs: form ingest configs for the module

        Returns:
          the transformed input_record, or None on error
        """


class FieldTransformation(Transformation, ABC):
    """Base class for transformations that drop individual fields from an input
    record."""


class FormTransformation(Transformation, ABC):
    """Base class for transformations that remove an entire form from an input
    record."""


class VersionMapTransformation(FieldTransformation):
    """Defines a map of form field names for different versions of the form."""

    transform_type: Literal["version_map"] = "version_map"
    version_map: VersionMap
    fields: Dict[str, List[str]] = {}

    def __unique_fields(self, version_name: str) -> Set[str]:
        """Finds the field names unique to the version.

        Args:
          version_name: the name of the form version

        Returns:
          the set of field names unique to the version
        """
        return set(self.fields.get(version_name, set()))

    def apply(
        self,
        input_record: Dict[str, Any],
        error_writer: ErrorWriter,
        line_num: int,
        module_configs: ModuleConfigs,
    ) -> Optional[Dict[str, Any]]:
        """Filters the input record by dropping the key-value pairs for fields
        unique to the version.

        Args:
          input_record: the record to filter
          error_writer: error metadata writer
          line_num: line number in the input CSV
          module_configs: form ingest configs for the module

        Returns:
          the input_record without the keys for the excluded fields or None
        """
        date_field = module_configs.date_field
        version_name = self.version_map.apply(input_record)
        drop_fields = self.__unique_fields(version_name)
        if not drop_fields:
            return input_record

        transformed = {}
        incorrectly_filled: List[str] = []
        for field, value in input_record.items():
            if field in drop_fields:
                # report error if excluded fields expected to be empty, but filled
                if self.nofill and input_record.get(field):
                    incorrectly_filled.append(field)

                continue

            transformed[field] = value

        if incorrectly_filled:
            visit_keys = DataIdentification.from_form_record_safe(
                record=input_record, date_field=date_field
            )
            error_writer.write(
                preprocessing_error(
                    field=self.version_map.fieldname,
                    value=input_record.get(self.version_map.fieldname, ""),
                    line=line_num,
                    error_code=SysErrorCodes.EXCLUDED_FIELDS,
                    visit_keys=visit_keys,
                    extra_args=[incorrectly_filled],
                )
            )
            return None

        return transformed


class ReleaseDateTransformation(FormTransformation):
    """Drops fields for a form not yet released for the visit and not
    submitted: when visit date < the form's release date and the mode field
    value is not one of retain_modes, the data fields, header fields, and the
    mode field are removed.

    The release date is looked up by form_name from the module's release_dates;
    a form with no configured release date is treated as already released. The
    mode field is derived as MODE + form_name.

    If nofill is set and any data field is non-empty, an error is reported and
    the record rejected (header fields are exempt from this check).
    """

    transform_type: Literal["release_date"] = "release_date"
    form_name: str
    retain_modes: List[str] = ["1"]
    header_fields: List[str] = []
    fields: List[str] = []

    def apply(
        self,
        input_record: Dict[str, Any],
        error_writer: ErrorWriter,
        line_num: int,
        module_configs: ModuleConfigs,
    ) -> Optional[Dict[str, Any]]:
        """Drops the form fields when the visit predates the form release date
        and the form was not submitted.

        Args:
          input_record: the record to filter
          error_writer: error metadata writer
          line_num: line number in the input CSV
          module_configs: form ingest configs for the module

        Returns:
          the record without the dropped fields, the record unchanged if the
          drop condition is not met, or None if data fields are incorrectly
          filled
        """
        date_field = module_configs.date_field
        release_dates = module_configs.release_dates
        if not release_dates:
            # no release config; treat the form as already released
            return input_record

        packet = str(input_record.get(FieldNames.PACKET, "")).strip()
        release_date = release_dates.get_release_date(packet, self.form_name.lower())
        if not release_date:
            # no configured release date; treat the form as already released
            return input_record

        mode_field = f"{FieldNames.MODE}{self.form_name.lower()}"
        visit_date = str(input_record.get(date_field, "")).strip()
        mode = str(input_record.get(mode_field, "")).strip()
        # dates are normalized to YYYY-MM-DD by DateTransformer, so string
        # comparison is lexicographically correct
        if not (
            visit_date and visit_date < release_date and mode not in self.retain_modes
        ):
            return input_record

        # report error if data fields expected to be empty, but filled
        incorrectly_filled = [
            field for field in self.fields if self.nofill and input_record.get(field)
        ]
        if incorrectly_filled:
            visit_keys = DataIdentification.from_form_record_safe(
                record=input_record, date_field=date_field
            )
            error_writer.write(
                preprocessing_error(
                    field=mode_field,
                    value=mode,
                    line=line_num,
                    error_code=SysErrorCodes.EXCLUDED_FIELDS,
                    visit_keys=visit_keys,
                    extra_args=[incorrectly_filled],
                )
            )
            return None

        drop = set(self.fields) | set(self.header_fields) | {mode_field}
        return {
            field: value for field, value in input_record.items() if field not in drop
        }


# Single member per category for now; the transform_type Literal tag makes
# extension trivial. To add a second type in a category, switch to a
# discriminated union, e.g.:
#   FieldTransformationType = Annotated[
#       Union[VersionMapTransformation, NewFieldTransformation],
#       Field(discriminator="transform_type")]
FieldTransformationType = VersionMapTransformation
FormTransformationType = ReleaseDateTransformation


class ModuleTransformations(BaseModel):
    """Groups the transformations for a module by category."""

    field_transformations: List[FieldTransformationType] = []
    form_transformations: List[FormTransformationType] = []


class TransformationSchema(RootModel):
    """Root model for the per-module transformation schema."""

    root: Dict[ModuleName, ModuleTransformations] = {}

    def get(self, key: ModuleName) -> Optional[ModuleTransformations]:
        """Returns the transformations for the module, or None if not defined.

        Args:
          key: the module name
        Returns:
          the ModuleTransformations for the module, or None
        """
        return self.root.get(key)


class BaseRecordTransformer(ABC):
    @abstractmethod
    def transform(
        self, input_record: Dict[str, Any], line_num: int
    ) -> Optional[Dict[str, Any]]:
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

    def transform(
        self, input_record: Dict[str, Any], line_num: int
    ) -> Optional[Dict[str, Any]]:
        """Applies the transformers in sequence to the input record.

        If there are no transformers, returns the record untransformed.

        Args:
          input_record: the input record
          line_number: the line number of the input record

        Returns:
          the transformed record. None, if any transform returns None.
        """
        log.info("Transforming input record %s", line_num)

        record: Optional[Dict[str, Any]] = input_record
        for transformer in self.__transformers:
            if record is None:
                return None

            record = transformer.transform(record, line_num)

        return record


class DateTransformer(BaseRecordTransformer):
    """Defines a transformer that normalizes date fields."""

    def __init__(
        self, error_writer: ErrorWriter, date_field: Optional[str] = None
    ) -> None:
        self._error_writer = error_writer
        self._date_field = date_field if date_field else FieldNames.DATE_COLUMN

    def transform(
        self, input_record: Dict[str, Any], line_num: int
    ) -> Optional[Dict[str, Any]]:
        """Normalizes the date column of the record.

        Args:
            input_record: input record from CSV file
            line_num (int): line number in CSV file

        Returns:
            Transformed record or None if there's processing errors
        """

        if self._date_field not in input_record:
            return input_record

        normalized_date = convert_date(
            date_string=input_record[self._date_field],
            date_format=DEFAULT_DATE_FORMAT,
        )  # type: ignore
        if not normalized_date:
            visit_keys = DataIdentification.from_form_record_safe(
                record=input_record, date_field=self._date_field
            )
            self._error_writer.write(
                unexpected_value_error(
                    field=self._date_field,
                    value=input_record[self._date_field],
                    expected="",
                    message="Expected a valid date string",
                    line=line_num,
                    visit_keys=visit_keys,
                )
            )
            return None

        input_record[self._date_field] = normalized_date
        return input_record


class FilterTransformer(BaseRecordTransformer):
    """Defines a transform that applies a single transformation to a record."""

    def __init__(
        self,
        transformation: Transformation,
        error_writer: ErrorWriter,
        module_configs: ModuleConfigs,
    ) -> None:
        self._transform = transformation
        self._error_writer = error_writer
        self._module_configs = module_configs

    def transform(
        self, input_record: Dict[str, Any], line_num: int
    ) -> Optional[Dict[str, Any]]:
        """Applies the transformation to the input record.

        Args:
          input_record: the input record
          line_num: the line number of the record in the input

        Returns:
          the record with fields filtered
        """
        return self._transform.apply(
            input_record=input_record,
            error_writer=self._error_writer,
            line_num=line_num,
            module_configs=self._module_configs,
        )


class TransformerFactory:
    def __init__(self, transformations: TransformationSchema) -> None:
        self.__transformations = transformations

    def create(
        self,
        module: Optional[str],
        error_writer: ErrorWriter,
        module_configs: ModuleConfigs,
    ) -> RecordTransformer:
        """Creates a transformer for the module using the transformations in
        this object.

        If the module name is none or has no corresponding transforms, a
        transformer with just the date transformation is returned.

        Args:
          module: the module name
          error_writer: error metadata writer
          module_configs: form ingest configs for the module

        Returns:
          the record transformer
        """
        transformer_list: List[BaseRecordTransformer] = []
        transformer_list.append(
            DateTransformer(error_writer, date_field=module_configs.date_field)
        )
        if module:
            module_transforms = self.__transformations.get(module)
            if module_transforms:
                for transformation in (
                    *module_transforms.field_transformations,
                    *module_transforms.form_transformations,
                ):
                    transformer_list.append(
                        FilterTransformer(transformation, error_writer, module_configs)
                    )

        return RecordTransformer(transformer_list)
