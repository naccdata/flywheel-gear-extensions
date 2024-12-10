"""Defines legacy_identifier_transfer."""

from datetime import datetime
import logging
from typing import Dict, Mapping

from pydantic import ValidationError

from enrollment.enrollment_project import EnrollmentProject
from enrollment.enrollment_transfer import EnrollmentRecord
from gear_execution.gear_execution import GearExecutionError
from identifiers.model import CenterIdentifiers, IdentifierObject
from outputs.errors import ErrorWriter, ListErrorWriter, identifier_error, legacy_naccid_error, unexpected_value_error

log = logging.getLogger(__name__)


class LegacyEnrollmentBatch:
    """Handles batch processing of legacy enrollment records."""

    def __init__(self) -> None:
        self.__records: Dict[str, EnrollmentRecord] = {}

    def add(self, record: EnrollmentRecord) -> None:
        """Adds an enrollment record to the batch.

        Args:
            record: EnrollmentRecord to add to the batch
        """
        if record.naccid:  # We know this will exist for legacy records
            self.__records[record.naccid] = record
        else:
            log.warning('Skipping record with missing NACCID: %s', record)

    def __len__(self) -> int:
        return len(self.__records)

    def __iter__(self):
        return iter(self.__records.values())


def process_legacy_identifiers(
    identifiers: Mapping[str, IdentifierObject],
    enrollment_date: datetime,  # Added parameter for enrollment date
    enrollment_project: EnrollmentProject,
    error_writer: ErrorWriter,
    dry_run: bool = True
) -> bool:
    """
    Process legacy identifiers and create enrollment records.

    Args:
        identifiers: Dictionary of legacy identifiers
        enrollment_date: Date to use as start_date for enrollments
        enrollment_project: Project to add enrollments to
        error_writer: For reporting errors
        dry_run: If True, do not actually add enrollments to Flywheel

    Returns:
        bool: True if processing was successful
    """
    batch = LegacyEnrollmentBatch()

    for naccid, identifier in identifiers.items():
        try:
            # Verify the NACCID matches between dict key and object
            if naccid != identifier.naccid:
                error_writer.write(
                    legacy_naccid_error(
                        field='naccid',
                        value=naccid,
                        message=f'NACCID mismatch: key {naccid} != value {identifier.naccid}'
                    )
                )
                return False

            # Create CenterIdentifiers first to validate ADCID/PTID pair
            center_identifiers = CenterIdentifiers(
                adcid=identifier.adcid,
                ptid=identifier.ptid
            )

            # Create enrollment record
            record = EnrollmentRecord(
                center_identifier=center_identifiers,
                naccid=identifier.naccid,
                guid=identifier.guid,  # Optional field
                start_date=enrollment_date,
                # Not setting optional fields:
                # end_date=None
                # transfer_from=None
                # transfer_to=None
            )

            batch.add(record)
            log.info('Added legacy enrollment for NACCID %s (ADCID: %s, PTID: %s)',
                     identifier.naccid, identifier.adcid, identifier.ptid)

        except ValidationError as validation_error:
            for error in validation_error.errors():
                if error['type'] == 'string_pattern_mismatch':
                    field_name = str(error['loc'][0])
                    context = error.get('ctx', {'pattern': ''})
                    error_writer.write(
                        unexpected_value_error(
                            field=field_name,
                            value=error['input'],
                            expected=context['pattern'],
                            message=f'Invalid {field_name.upper()}',
                            # FIXME - line number is not available in the error
                            line=0
                        )
                    )
                else:
                    # Handle other validation errors
                    error_writer.write(
                        identifier_error(
                            field=str(error['loc'][0]),
                            value=str(error.get('input', '')),
                            message=f"Validation error: {error['msg']}",
                            # FIXME - line number is not available in the error
                            line=0
                        )
                    )
            return False

    if not batch:
        log.warning('No valid legacy identifiers to process')
        return True

    # Process the batch
    success = True
    for record in batch:
        if not record.naccid:
            error_writer.write(
                legacy_naccid_error(
                    field='naccid',
                    value='',
                    message='Missing NACCID'
                )
            )
            continue

        if enrollment_project.find_subject(label=record.naccid):
            log.error(
                'Subject with NACCID %s already exists - skipping creation', record.naccid)
            error_writer.write(
                identifier_error(
                    field='naccid',
                    value=record.naccid,
                    message=f'Subject with NACCID {record.naccid} already exists',
                    # FIXME - line number is not available in the error
                    line=0
                )
            )
            # Skip adding enrollments to Flywheel if subject already exists
            continue

        if not dry_run:
            subject = enrollment_project.add_subject(record.naccid)
            subject.add_enrollment(record)
            log.info('Created enrollment for subject %s', record.naccid)
    return success


def run(*,
        adcid: int,
        identifiers: Dict[str, IdentifierObject],
        enrollment_project: EnrollmentProject,
        dry_run: bool = True,
        error_writer: ListErrorWriter) -> bool:
    """Runs legacy identifier enrollment process.

    Args:
        identifiers: Dictionary of identifier objects from legacy system
        enrollment_project: Project to add enrollments to
        error_writer: For reporting errors

    Returns:
        bool: True if processing was successful, False otherwise
    """
    log.info(f"Running the Legacy Identifier Transfer gear for ADCID {adcid}")
    log.info(f'found {len(identifiers)} identifiers')

    try:
        success = process_legacy_identifiers(
            identifiers=identifiers,
            # TODO: refactor identifiers API to get actual enrollment date?
            enrollment_date=datetime.now(),
            enrollment_project=enrollment_project,
            dry_run=dry_run,
            error_writer=error_writer
        )

        # Retrieve and print accumulated errors
        accumulated_errors = error_writer.errors()
        for err in accumulated_errors:
            log.error(err)

        if not success:
            log.error("No changes made due to errors in identifier processing")
            return False

        log.info("Successfully processed %d legacy identifiers", len(identifiers))

    except GearExecutionError as error:
        log.error("Error during gear execution: %s", str(error))
        return False
    except Exception as error:
        log.error("Unexpected error during processing: %s", str(error))
        raise GearExecutionError(str(error)) from error
    return True
