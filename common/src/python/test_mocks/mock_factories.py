"""Mock data factories for testing."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import Mock

from flywheel.models.file_entry import FileEntry
from nacc_common.error_models import (
    QC_STATUS_PASS,
    FileQCModel,
    GearQCModel,
    ValidationModel,
    VisitMetadata,
)

from .mock_flywheel import MockFile


def create_mock_file_entry(
    name: str, info: Optional[Dict[str, Any]] = None
) -> FileEntry:
    """Create a mock FileEntry with the given info."""
    file_entry = Mock(spec=FileEntry)
    file_entry.name = name
    file_entry.info = info or {}
    file_entry.modified = datetime.now()
    file_entry.created = datetime.now()
    return file_entry


class QCMetadataFactory:
    """Factory for creating QC metadata objects."""

    @staticmethod
    def create_qc_metadata_with_status(
        gears: Dict[str, str],
    ) -> FileQCModel:
        """Create QC metadata with specified status for each gear.

        Args:
            gears: Dict mapping gear names to their states

        Returns:
            FileQCModel instance with specified status
        """
        qc_gears: dict[str, GearQCModel] = {}

        for gear_name, state in gears.items():
            # Create ValidationModel with specified state
            validation_model = ValidationModel(
                state=state,
                data=[],  # No errors for PASS status
                cleared=[],  # No cleared alerts needed
            )

            # Create GearQCModel
            qc_gears[gear_name] = GearQCModel(validation=validation_model)

        return FileQCModel(qc=qc_gears)

    @staticmethod
    def create_pass_qc_metadata(
        gear_names: Optional[List[str]] = None,
    ) -> FileQCModel:
        """Create QC metadata with PASS status for all gears.

        Args:
            gear_names: List of gear names. If None, uses default set.

        Returns:
            FileQCModel instance with PASS status
        """
        if gear_names is None:
            gear_names = [
                "identifier-lookup",
                "form-transformer",
                "form-qc-coordinator",
                "form-qc-checker",
            ]

        gears = {gear_name: QC_STATUS_PASS for gear_name in gear_names}
        return QCMetadataFactory.create_qc_metadata_with_status(gears)

    @staticmethod
    def create_fail_qc_metadata(
        failing_gear: str = "form-qc-checker",
        gear_names: Optional[List[str]] = None,
    ) -> FileQCModel:
        """Create QC metadata with one failing gear.

        Args:
            failing_gear: Name of the gear that should fail
            gear_names: List of gear names. If None, uses default set.

        Returns:
            FileQCModel instance with one failing gear
        """
        if gear_names is None:
            gear_names = [
                "identifier-lookup",
                "form-transformer",
                "form-qc-coordinator",
                "form-qc-checker",
            ]

        gears = {gear_name: QC_STATUS_PASS for gear_name in gear_names}
        gears[failing_gear] = "FAIL"
        return QCMetadataFactory.create_qc_metadata_with_status(gears)


class FileEntryFactory:
    """Factory for creating mock file entries."""

    @staticmethod
    def create_mock_json_file_with_forms_metadata(
        name: str,
        ptid: str,
        visitdate: str,
        visitnum: str,
        module: str,
        packet: Optional[str] = None,
        parent_id: str = "acquisition-123",
    ) -> MockFile:
        """Create a mock JSON file with forms metadata.

        Args:
            name: File name
            ptid: Participant ID
            visitdate: Visit date
            visitnum: Visit number
            module: Module name
            packet: Packet identifier (optional)
            parent_id: Parent acquisition ID

        Returns:
            MockFile with forms metadata
        """
        forms_metadata = {
            "forms": {
                "json": {
                    "ptid": ptid,
                    "visitdate": visitdate,
                    "visitnum": visitnum,
                    "module": module,
                }
            }
        }

        if packet:
            forms_metadata["forms"]["json"]["packet"] = packet

        return MockFile(
            name=name,
            info=forms_metadata,
            parent_id=parent_id,
        )

    @staticmethod
    def create_mock_qc_status_file_with_visit_metadata(
        ptid: str,
        date: str,
        module: str,
        qc_metadata: FileQCModel,
        visit_metadata: Optional[VisitMetadata] = None,
        modified: Optional[datetime] = None,
    ) -> MockFile:
        """Create a mock QC-status file with visit metadata in custom info.

        Args:
            ptid: Participant ID
            date: Visit date
            module: Module name (e.g., "uds")
            qc_metadata: FileQCModel instance
            visit_metadata: VisitMetadata to include in custom info
            modified: File modification timestamp

        Returns:
            MockFile with QC metadata and visit metadata in custom info
        """
        filename = f"{ptid}_{date}_{module}_qc-status.log"

        # Convert FileQCModel to dict for MockFile info using aliases
        info_dict = qc_metadata.model_dump(by_alias=True)

        # Add visit metadata to custom info if provided
        if visit_metadata:
            info_dict["visit"] = visit_metadata.model_dump(
                exclude_none=True, mode="raw"
            )

        return MockFile(name=filename, info=info_dict, modified=modified)

    @staticmethod
    def create_mock_qc_status_file_for_project(
        filename: str,
        qc_status: str,
        custom_info: Optional[Dict[str, Any]] = None,
        qc_completion_time: Optional[datetime] = None,
    ) -> FileEntry:
        """Create a QC status file for MockProjectAdaptor.

        Args:
            filename: QC status file name
            qc_status: QC status (PASS, FAIL, etc.)
            custom_info: Additional custom info
            qc_completion_time: QC completion timestamp

        Returns:
            Mock FileEntry for QC status file
        """
        # Create QC model with proper structure
        qc_data = {
            "test-gear": GearQCModel(
                validation=ValidationModel(
                    state=qc_status,
                    data=[],
                )
            )
        }

        # Create file entry
        file_entry = Mock(spec=FileEntry)
        file_entry.name = filename
        file_entry.modified = qc_completion_time or datetime.now()

        # Put QC data in custom info, not file contents
        file_entry.info = custom_info or {}
        file_entry.info["qc"] = qc_data

        return file_entry


class VisitMetadataFactory:
    """Factory for creating visit metadata objects."""

    @staticmethod
    def create_visit_metadata(
        ptid: str = "TEST001",
        date: str = "2024-01-15",
        visitnum: str = "01",
        module: str = "UDS",
        packet: Optional[str] = "I",
        adcid: Optional[int] = None,
        naccid: Optional[str] = None,
    ) -> VisitMetadata:
        """Create a VisitMetadata object with specified values.

        Args:
            ptid: Participant ID
            date: Visit date
            visitnum: Visit number
            module: Module name
            packet: Packet identifier
            adcid: ADC ID
            naccid: NACC ID

        Returns:
            VisitMetadata object
        """
        return VisitMetadata(
            ptid=ptid,
            date=date,
            visitnum=visitnum,
            module=module,
            packet=packet,
            adcid=adcid,
            naccid=naccid,
        )
