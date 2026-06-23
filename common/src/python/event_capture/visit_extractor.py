import logging
from typing import Any, Dict, Optional

from configs.ingest_configs import FormProjectConfigs
from deletions.models import DeleteRequest
from flywheel.models.file_entry import FileEntry
from nacc_common.data_identification import DataIdentification
from nacc_common.field_names import FieldNames
from pydantic import ValidationError

log = logging.getLogger(__name__)

# forms.json stores the raw form record, so the visit date lives under the
# module-specific date column. Most modules use FieldNames.DATE_COLUMN
# ("visitdate"); some (e.g. NP) use a module-specific field (FieldNames.NPDATE).
KNOWN_DATE_FIELDS = (FieldNames.DATE_COLUMN, FieldNames.NPDATE)


class DataIdentificationExtractor:
    """Utility for extracting DataIdentification from QC status or JSON
    files."""

    @staticmethod
    def from_qc_status_custom_info(
        custom_info: Dict[str, Any],
    ) -> Optional[DataIdentification]:
        """Extract DataIdentification from QC status custom info.

        Args:
            custom_info: Custom info from QC status log file

        Returns:
            DataIdentification instance or None if not found/invalid
        """
        if not custom_info:
            return None

        visit_data = custom_info.get("visit")
        if not visit_data:
            return None

        try:
            return DataIdentification.from_visit_metadata(**visit_data)
        except (ValidationError, ValueError, TypeError):
            return None

    @staticmethod
    def from_json_file_metadata(
        json_file: FileEntry, form_configs: Optional[FormProjectConfigs] = None
    ) -> Optional[DataIdentification]:
        """Extract DataIdentification from a JSON file's forms.json metadata.

        The visit date is resolved from the module-specific date column. When
        form_configs is provided and the file's module is known, the configured
        date field is used; otherwise the date column is auto-detected from the
        known module date fields.

        Args:
            json_file: JSON file with forms metadata
            form_configs: optional form module configs used to resolve the
                module-specific date field

        Returns:
            DataIdentification instance or None if not found/invalid
        """

        if not json_file:
            return None

        json_file = json_file.reload()
        if not json_file.info:
            return None

        forms_json = json_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return None

        date_field = DataIdentificationExtractor._date_field_from_configs(
            forms_json, form_configs
        )
        return DataIdentificationExtractor.from_forms_json(
            forms_json, date_field=date_field
        )

    @staticmethod
    def _date_field_from_configs(
        forms_json: dict[str, Any],
        form_configs: Optional[FormProjectConfigs],
    ) -> Optional[str]:
        """Resolve the module-specific date field for a forms.json record.

        Looks up the record's module in the form module configs. Returns None
        when configs are unavailable or the module is unknown, letting the
        extractor auto-detect the date column.

        Args:
            forms_json: the forms.json record (raw visit record)
            form_configs: optional form module configs

        Returns:
            the module-specific date field, or None if it cannot be resolved
        """
        if not form_configs:
            return None

        module = forms_json.get(FieldNames.MODULE)
        if not module:
            return None

        module_configs = form_configs.module_configs.get(module.upper())
        return module_configs.date_field if module_configs else None

    @staticmethod
    def from_deletion_request_file(
        request_file: FileEntry,
        adcid: int,
    ) -> Optional[DataIdentification]:
        """Extract DataIdentification from a deletion request file.

        Reads and parses the deletion request JSON file content.

        Args:
            request_file: The deletion request FileEntry
            adcid: The ADC ID for the project

        Returns:
            DataIdentification instance or None if parsing fails
        """
        try:
            content = request_file.read().decode("utf-8")
            delete_request = DeleteRequest.model_validate_json(content)
            return DataIdentification.from_visit_metadata(
                adcid=adcid,
                ptid=delete_request.ptid,
                date=delete_request.visitdate,
                module=delete_request.module,
                visitnum=delete_request.visitnum,
            )
        except (ValidationError, ValueError, TypeError) as error:
            log.error(
                "Failed to extract data identification from %s: %s",
                request_file.name,
                error,
            )
            return None

    @staticmethod
    def from_forms_json(
        forms_json: dict[str, Any], date_field: Optional[str] = None
    ) -> Optional[DataIdentification]:
        """Extract DataIdentification from a forms.json record.

        Args:
            forms_json: the forms.json record (raw visit record)
            date_field: the module-specific date column name. If None, the date is
                auto-detected from the known date fields present in the record.

        Returns:
            DataIdentification instance or None if required fields are missing/invalid
        """
        if not forms_json:
            return None

        # module is required to build a DataIdentification
        if not forms_json.get(FieldNames.MODULE):
            log.warning(
                "Failed to extract DataIdentification: "
                "Missing 'module' field in forms.json metadata"
            )
            return None

        # Resolve the visit date from the module-specific date column.
        if date_field:
            date_value = forms_json.get(date_field)
        else:
            date_value = next(
                (
                    forms_json[field]
                    for field in KNOWN_DATE_FIELDS
                    if forms_json.get(field)
                ),
                None,
            )

        # Map only the identification fields (forms.json also carries many other
        # form columns that are not from_visit_metadata parameters).
        try:
            return DataIdentification.from_visit_metadata(
                ptid=forms_json.get(FieldNames.PTID),
                date=date_value,
                module=forms_json.get(FieldNames.MODULE),
                visitnum=forms_json.get(FieldNames.VISITNUM),
                packet=forms_json.get(FieldNames.PACKET),
                naccid=forms_json.get(FieldNames.NACCID),
                adcid=forms_json.get(FieldNames.ADCID),
            )
        except (ValidationError, ValueError, TypeError) as err:
            log.warning("Invalid forms.json metadata: %s", err)
            return None
