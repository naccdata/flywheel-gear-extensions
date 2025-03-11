"""Defines legacy_identifier_transfer."""

import logging
from datetime import datetime
from typing import Dict, List, Mapping, Optional

from datastore.forms_store import FormFilter, FormsStore
from dates.form_dates import DEFAULT_DATE_FORMAT, DateFormatException, parse_date
from enrollment.enrollment_project import EnrollmentProject
from enrollment.enrollment_transfer import EnrollmentRecord
from gear_execution.gear_execution import GearExecutionError
from identifiers.model import CenterIdentifiers, IdentifierObject
from keys.keys import DefaultValues, FieldNames, MetadataKeys
from notifications.email import EmailClient, create_ses_client
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
    record = EnrollmentRecord(naccid=identifier.naccid,
                              guid=identifier.guid,
                              center_identifier=center_identifiers,
                              start_date=enrollment_date,
                              legacy=True)

    return record


def process_record_collection(record_collection: LegacyEnrollmentCollection,
                              enrollment_project: EnrollmentProject,
                              failed_ids: List[str], dry_run: bool) -> bool:
    """Process a collection of enrollment records.

    Args:
        record_collection: Collection of legacy enrollment records to process
        enrollment_project: Project where enrollments will be added
        failed_ids: List of identifiers that failed processing
        dry_run: If True, simulate execution without making changes

    Returns:
        bool: True if processing was successful with no errors
    """
    success_count = 0
    error_count = 0
    for record in record_collection:
        if not record.naccid:
            error_count += 1
            log.error('Missing NACCID for record: %s', record)
            continue

        if dry_run:
            log.info('Dry run: would create enrollment for subject %s',
                     record.naccid)
            success_count += 1
            continue

        try:
            subject = enrollment_project.add_subject(record.naccid)
            subject.add_enrollment(record)
            success_count += 1
        except Exception as e:
            log.error('Failed to create enrollment record for %s: %s',
                      record.naccid, str(e))
            failed_ids.append(record.naccid)
            error_count += 1

    if error_count:
        log.error('Failed to import %d records', error_count)

    log.info('Successfully imported %d legacy enrollment records',
             success_count)
    return error_count == 0  # Returns True only if no errors occurred


def get_enrollment_date(subject_id: str,
                        forms_store: FormsStore) -> Optional[datetime]:

    ivp_filter = FormFilter(field=FieldNames.PACKET,
                            value=DefaultValues.UDS_I_PACKET,
                            operator="=")
    initial_visits = forms_store.query_form_data_with_custom_filters(
        subject_lbl=subject_id,
        module=DefaultValues.UDS_MODULE,
        legacy=True,
        order_by=FieldNames.DATE_COLUMN,
        list_filters=[ivp_filter])

    # If no UDS IVP found check for MDS or BDS visit
    if not initial_visits:
        initial_visits = forms_store.query_form_data_with_custom_filters(
            subject_lbl=subject_id,
            module=[DefaultValues.MDS_MODULE, DefaultValues.BDS_MODULE],
            legacy=True,
            order_by=FieldNames.DATE_COLUMN)

    if initial_visits and len(initial_visits) > 1:
        log.error('Multiple IVP/MDS packets found for subject %s', subject_id)
        return None

    ivp_packet = initial_visits[0] if initial_visits else None

    if not ivp_packet:
        return None

    date_col_lbl = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.DATE_COLUMN}'

    try:
        enroll_date = parse_date(date_string=ivp_packet[date_col_lbl],
                                 formats=[DEFAULT_DATE_FORMAT])
        return enroll_date
    except DateFormatException:
        log.error('Unable to parse initial visit date %s for subject %s',
                  ivp_packet[date_col_lbl], subject_id)
        return None


def process_legacy_identifiers(  # noqa: C901
        identifiers: Mapping[str, IdentifierObject],
        enrollment_project: EnrollmentProject,
        forms_store: FormsStore,
        failed_ids: List[str],
        dry_run: bool = True) -> bool:
    """Process legacy identifiers and create enrollment records.

    Args:
        identifiers: Dictionary of legacy identifiers
        enrollment_project: Project to add enrollments to
        forms_store: Class to retrieve form data from Flywheel ingest project
        failed_ids: List of identifiers that failed processing
        dry_run: If True, do not actually add enrollments to Flywheel

    Returns:
        bool: True if processing was successful
    """
    record_collection = LegacyEnrollmentCollection()

    success = True
    skipped_count = 0
    failed_count = 0
    for naccid, identifier in identifiers.items():
        try:
            if enrollment_project.find_subject(label=naccid):
                log.warning(
                    'Subject with NACCID %s already exists - skipping creation',
                    naccid)
                skipped_count += 1
                continue

            enrollment_date = get_enrollment_date(subject_id=naccid,
                                                  forms_store=forms_store)
            if not enrollment_date:
                log.error(
                    'Failed to find the enrollment date for NACCID %s PTID %s ADCID %s',
                    naccid, identifier.ptid, identifier.adcid)
                success = False
                failed_ids.append(naccid)
                failed_count += 1
                continue

            record = validate_and_create_record(naccid, identifier,
                                                enrollment_date)
            if record:
                record_collection.add(record)
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
            success = False
            failed_ids.append(naccid)
            failed_count += 1

    if skipped_count > 0:
        log.warning('Number of skipped records: %s', skipped_count)

    if failed_count > 0:
        log.error('Number of records that failed validation: %s', failed_count)

    if not record_collection:
        log.warning('No valid legacy identifiers to process')
        return success

    return success and process_record_collection(
        record_collection=record_collection,
        enrollment_project=enrollment_project,
        failed_ids=failed_ids,
        dry_run=dry_run)


def send_email(sender_email: str, target_emails: List[str], group_lbl: str,
               project_lbl: str, failed_count: int) -> None:
    """Send a raw email notifying target emails of the error.

    Args:
        sender_email: The sender email
        target_emails: The target email(s)
        group_lbl: Flywheel group label
        project_lbl: Flywheel project label
        failed_count: Number of identifiers that failed processing
    """
    client = EmailClient(client=create_ses_client(), source=sender_email)

    subject = f'Legacy identifier transfer failure for {group_lbl}/{project_lbl}'
    body = f'Failed to transfer {failed_count} legacy identifiers ' \
        + f'to project {group_lbl}/{project_lbl}.\n' \
        + 'Check the job error log for the list of failed IDs.\n\n'

    client.send_raw(destinations=target_emails, subject=subject, body=body)


def run(*,
        identifiers: Dict[str, IdentifierObject],
        enrollment_project: EnrollmentProject,
        forms_store: FormsStore,
        sender_email: str,
        target_emails: List[str],
        dry_run: bool = True) -> bool:
    """Runs legacy identifier enrollment process.

    Args:
        identifiers: Dictionary of identifier objects from legacy system
        enrollment_project: Project to add enrollments to
        forms_store: Class to retrieve form data from Flywheel ingest project
        sender_email: The sender email
        target_emails: The target email(s)
        dry_run(optional): Whether to do a dry run. Default False

    Returns:
        bool: True if processing was successful, False otherwise
    """

    try:
        failed_ids: List[str] = []
        success = process_legacy_identifiers(
            identifiers=identifiers,
            enrollment_project=enrollment_project,
            forms_store=forms_store,
            failed_ids=failed_ids,
            dry_run=dry_run)

        if len(failed_ids) > 0:
            log.error("List of failed IDs: %s", failed_ids)
            log.error("Number of failed records: %s", len(failed_ids))
            send_email(sender_email=sender_email,
                       target_emails=target_emails,
                       group_lbl=enrollment_project.group,
                       project_lbl=enrollment_project.label,
                       failed_count=len(failed_ids))

        if not success:
            log.error("Error(s) occurred while importing legacy identifiers")
            return False

    except GearExecutionError as error:
        log.error("Error during gear execution: %s", str(error))
        return False
    except Exception as error:
        log.error("Unexpected error during processing: %s", str(error))
        raise GearExecutionError(str(error)) from error

    return True
