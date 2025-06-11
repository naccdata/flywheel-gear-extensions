from typing import Dict, List, Optional

from configs.ingest_configs import ModuleConfigs
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from keys.keys import FieldNames, MetadataKeys


def find_visits_for_participant_for_module(
        *,
        proxy: FlywheelProxy,
        container_id: str,
        subject: str,
        module: str,
        module_configs: ModuleConfigs,
        cutoff_date: Optional[str] = None) -> Optional[List[Dict[str, str]]]:
    """Get the list of visits for the specified participant for the specified
    module. If cutoff_date specified, filter visits on date_col >= cutoff_date.

    Note: This method assumes visit date in file metadata is normalized to
    YYYY-MM-DD format at a previous stage of the submission pipeline.

    Args:
        proxy: Flywheel proxy
        container_id: Flywheel subject container ID
        subject: Flywheel subject label for participant
        module: module label, matched with Flywheel acquisition label
        module_configs: form ingest configs for the module
        cutoff_date (optional): If specified, filter visits on date_col >= cutoff_date

    Returns:
        List[Dict]: List of visits matching with the specified cutoff date
    """

    title = f'{module} visits for participant {subject}'

    ptid_key = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PTID}'
    date_col_key = f'{MetadataKeys.FORM_METADATA_PATH}.{module_configs.date_field}'
    columns = [
        ptid_key, date_col_key, 'file.name', 'file.file_id',
        'file.parents.acquisition'
    ]

    if FieldNames.VISITNUM in module_configs.required_fields:
        visitnum_key = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}'
        columns.append(visitnum_key)

    filters = f'acquisition.label={module}'

    if cutoff_date:
        filters += f',{date_col_key}>={cutoff_date}'

    return proxy.get_matching_acquisition_files_info(container_id=container_id,
                                                     dv_title=title,
                                                     columns=columns,
                                                     filters=filters)


def find_module_visits_with_matching_visitdate(
        *, proxy: FlywheelProxy, container_id: str, subject: str, module: str,
        module_configs: ModuleConfigs, visitdate: str,
        visitnum: Optional[str]) -> Optional[List[Dict[str, str]]]:
    """Get the list of visits for the specified participant for the specified
    module matching with the given visitdate and visitnum (if specified).

    Note: This method assumes visit date in file metadata is normalized to
    YYYY-MM-DD format at a previous stage of the submission pipeline.

    Args:
        proxy: Flywheel proxy
        container_id: Flywheel subject container ID
        subject: Flywheel subject label for participant
        module: module label, matched with Flywheel acquisition label
        module_configs: form ingest configs for the module
        visitdate: visitdate to match
        visitnum(optional): visit number to match

    Returns:
        List[Dict]: List of visits matching with the specified visitdate and visitnum
    """

    title = f'{module} visits for participant {subject}'

    ptid_key = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.PTID}'
    date_col_key = f'{MetadataKeys.FORM_METADATA_PATH}.{module_configs.date_field}'
    columns = [
        ptid_key, date_col_key, 'file.name', 'file.file_id',
        'file.parents.acquisition'
    ]

    filters = f'acquisition.label={module},{date_col_key}={visitdate}'

    if visitnum and FieldNames.VISITNUM in module_configs.required_fields:
        visitnum_key = f'{MetadataKeys.FORM_METADATA_PATH}.{FieldNames.VISITNUM}'
        columns.append(visitnum_key)
        filters += f',{visitnum_key}={visitnum}'

    return proxy.get_matching_acquisition_files_info(container_id=container_id,
                                                     dv_title=title,
                                                     columns=columns,
                                                     filters=filters)
