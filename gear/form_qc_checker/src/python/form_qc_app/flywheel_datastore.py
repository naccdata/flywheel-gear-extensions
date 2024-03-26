"""Handles the connection with a Flywheel project."""

import json
import logging
from json.decoder import JSONDecodeError

from flywheel.client import Client
from flywheel.rest import ApiException
from flywheel.view_builder import ViewBuilder
from form_qc_app.parser import Keys
from validator.datastore import Datastore

log = logging.getLogger(__name__)


class FlywheelDatastore(Datastore):
    """This class defines functions to retrieve previous visits from
    Flywheel."""

    def __init__(self, client: Client, group: str, project: str):
        """

        Args:
            client (Client): the Flywheel SDK client
            group (str): Flywheel group id
            project (str): Flywheel project id
        """

        self.__client = client
        self.__gid = group
        self.__pid = project

        # Retrieve Group, Project containers from Flywheel
        try:
            self.__group = self.__client.get_group(self.__gid)
            self.__project = self.__client.get_project(self.__pid)
        except ApiException as error:
            log.error('Failed to retrieve Flywheel container: %s', error)

    def get_previous_instance(
            self, orderby: str, pk_field: str,
            current_ins: dict[str, str]) -> dict[str, str] | None:
        """Overriding the abstract method, get the previous visit record for
        the specified subject.

        Args:
            orderby (str): Variable name that visits are sorted by
            pk_field (str): Primary key field of the project
            current_ins (dict[str, str]): Visit currently being validated

        Returns:
            dict[str, str]: Previous visit record. None if no previous visit
        """

        group_lbl = self.__group.label
        project_lbl = self.__project.label

        if pk_field not in current_ins:
            log.error(('Variable %s not set in current visit data, '
                       'cannot retrieve the previous visits'), pk_field)
            return None

        if orderby not in current_ins:
            log.error(('Variable %s not set in current visit data, '
                       'cannot retrieve the previous visits'), orderby)
            return None

        if Keys.MODULE not in current_ins:
            log.error(('Variable %s not set in current visit data, '
                       'cannot retrieve the previous visits'), Keys.MODULE)
            return None

        subject_lbl = current_ins[pk_field]
        curr_ob_col_val = current_ins[orderby]
        module = current_ins[Keys.MODULE]

        # Dataview to retrieve the previous visits
        orderby_col = f'file.info.forms.json.{orderby}'
        columns = [
            'file.name', 'file.file_id', "file.parents.acquisition",
            "file.parents.session", orderby_col
        ]
        builder = ViewBuilder(
            label=('Previous visits for - '
                   f'{group_lbl}/{project_lbl}/{subject_lbl}'),
            columns=columns,
            container='acquisition',
            filename='*.json',
            match='all',
            process_files=False,
            filter=(
                f'subject.label={subject_lbl},'
                f'acquisition.label={module},{orderby_col}<{curr_ob_col_val}'),
            include_ids=False,
            include_labels=False)
        view = builder.build()

        dframe = self.__client.read_view_dataframe(view, self.__pid)
        if dframe.empty:
            log.error('No previous visits found for %s - %s', subject_lbl,
                      module)
            return None
        dframe = dframe.sort_values(orderby_col, ascending=False)
        # latest_rec = dframe.head(1)

        latest_rec_info = dframe.head(1).to_dict('records')[0]
        return self.get_visit_data(latest_rec_info['file.name'],
                                   latest_rec_info['file.parents.acquisition'])

    def get_visit_data(self, file_name: str,
                       acq_id: str) -> dict[str, str] | None:
        """Read the previous visit file and convert to python dictionary.

        Args:
            file_name (str): Previous visit file name
            acq_id (str): Previous visit acquisition id

        Returns:
            dict[str, str] | None: Previous visit data or None
        """
        visit_data = None

        acquisition = self.__client.get_acquisition(acq_id)
        file_content = acquisition.read_file(file_name)

        try:
            visit_data = json.loads(file_content)
            log.info('Found previous visit file: %s', file_name)
        except (JSONDecodeError, TypeError, ValueError) as error:
            log.error('Failed to read the previous visit file - %s : %s',
                      file_name, error)

        return visit_data
