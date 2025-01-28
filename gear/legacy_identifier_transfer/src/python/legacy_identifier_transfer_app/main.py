"""Defines legacy_identifier_transfer."""

import logging
from datetime import datetime
from typing import Dict, Mapping, Optional

from enrollment.enrollment_project import EnrollmentProject
from enrollment.enrollment_transfer import EnrollmentRecord
from gear_execution.gear_execution import GearExecutionError
from identifiers.model import CenterIdentifiers, IdentifierObject
from pydantic import ValidationError

log = logging.getLogger(__name__)


class LegacyEnrollmentCollection:
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


def validate_and_create_record(
        naccid: str, identifier: IdentifierObject,
        enrollment_date: datetime) -> Optional[EnrollmentRecord]:
    """Validate identifier and create an enrollment record."""
    if naccid != identifier.naccid:
        log.error('NACCID mismatch: key %s != value %s', naccid,
                  identifier.naccid)
        return None

    center_identifiers = CenterIdentifiers(adcid=identifier.adcid,
                                           ptid=identifier.ptid)
    record = EnrollmentRecord(
        center_identifier=center_identifiers,
        naccid=identifier.naccid,
        guid=identifier.guid,
        start_date=enrollment_date,
    )
    return record


def process_record_collection(
    record_collection: LegacyEnrollmentCollection,
    enrollment_project: EnrollmentProject,
    dry_run: bool
) -> bool:
    """Process a collection of enrollment records.

    Args:
        record_collection: Collection of legacy enrollment records to process
        enrollment_project: Project where enrollments will be added
        dry_run: If True, simulate execution without making changes

    Returns:
        bool: True if processing was successful with no errors
    """
    success_count = 0
    error_count = 0
    skipped_count = 0
    for record in record_collection:
        if not record.naccid:
            error_count += 1
            log.error('Missing NACCID for record: %s', record)
            continue

        if enrollment_project.find_subject(label=record.naccid):
            log.error(
                'Subject with NACCID %s already exists - skipping creation',
                record.naccid)
            skipped_count += 1
            continue
        
        if not dry_run:
            try:
                subject = enrollment_project.add_subject(record.naccid)
                subject.add_enrollment(record)
                log.info('Created enrollment for subject %s', record.naccid)
                success_count += 1
            except Exception as e:
                log.error('Failed to create enrollment for %s: %s', record.naccid, str(e))
                error_count += 1
        else:
            log.info('Dry run: would create enrollment for subject %s',
                     record.naccid)
            success_count += 1
    
    if error_count:
        log.error('Failed to process %d records', error_count)
    if skipped_count:
        log.warning('Skipped %d records', skipped_count)
    log.info('Successfully processed %d records', success_count)
    return error_count == 0  # Returns True only if no errors occurred


def process_legacy_identifiers(
        identifiers: Mapping[str, IdentifierObject],
        enrollment_date: datetime,  # Added parameter for enrollment date
        enrollment_project: EnrollmentProject,
        dry_run: bool = True) -> bool:
    """Process legacy identifiers and create enrollment records.

    Args:
        identifiers: Dictionary of legacy identifiers
        enrollment_date: Date to use as start_date for enrollments
        enrollment_project: Project to add enrollments to
        dry_run: If True, do not actually add enrollments to Flywheel

    Returns:
        bool: True if processing was successful
    """
    record_collection = LegacyEnrollmentCollection()

    for naccid, identifier in identifiers.items():
        try:
            record = validate_and_create_record(naccid, identifier,
                                                enrollment_date)
            if record:
                record_collection.add(record)
                log.info(
                    'Found legacy enrollment for NACCID %s (ADCID: %s, PTID: %s)',
                    identifier.naccid, identifier.adcid, identifier.ptid)
        except ValidationError as validation_error:
            for error in validation_error.errors():
                if error['type'] == 'string_pattern_mismatch':
                    field_name = str(error['loc'][0])
                    context = error.get('ctx', {'pattern': ''})
                    log.error('Invalid %s: %s (expected pattern: %s)',
                              field_name, error['input'], context['pattern'])
                else:
                    log.error('Validation error in field %s: %s (value: %s)',
                              str(error['loc'][0]), error['msg'],
                              str(error.get('input', '')))
            return False

    if not record_collection:
        log.warning('No valid legacy identifiers to process')
        return True

    return process_record_collection(record_collection, enrollment_project,
                                     dry_run)


def run(*,
        adcid: int,
        identifiers: Dict[str, IdentifierObject],
        enrollment_project: EnrollmentProject,
        dry_run: bool = True) -> bool:
    """Runs legacy identifier enrollment process.

    Args:
        identifiers: Dictionary of identifier objects from legacy system
        enrollment_project: Project to add enrollments to

    Returns:
        bool: True if processing was successful, False otherwise
    """

    try:
        success = process_legacy_identifiers(
            identifiers=identifiers,
            # TODO: refactor identifiers API to get actual enrollment date?
            enrollment_date=datetime.now(),
            enrollment_project=enrollment_project,
            dry_run=dry_run,
        )

        if not success:
            log.error("No changes made due to errors in identifier processing")
            return False

        log.info("Successfully processed %d legacy identifiers",
                 len(identifiers))

    except GearExecutionError as error:
        log.error("Error during gear execution: %s", str(error))
        return False
    except Exception as error:
        log.error("Unexpected error during processing: %s", str(error))
        raise GearExecutionError(str(error)) from error
    return True
