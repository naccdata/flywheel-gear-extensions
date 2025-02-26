import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from curator.symbol_table import SymbolTable
from files.uds_form import UDSV3Form, datetime_from_form_date
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from flywheel_gear_toolkit import GearToolkitContext
from flywheel_gear_toolkit.utils.curator import FileCurator

log = logging.getLogger(__name__)
# log.setLevel("DEBUG")


class UDSFileCurator(FileCurator):
    """birthyr/birthmo/visitdate, file.info.derived.naccage
    rac/racesec/raceter, file.info.derived.naccnihr.

    file.info.forms.json.formver, subject.info.study-parameters.uds.versions
      - pull existing subject.info.study-parameters.uds.versions
      - insert file.info.forms.json.formver into versions "set"


    file.info.derived.naccage, subject.info.demographics.uds.age.latest
    file.info.forms.json.sex, subject.info.demographics.uds.sex.latest
    file.info.derived.naccnihr, subject.info.demographics.uds.race.latest
    file.info.form.json.cdrglob, subject.info.cognitive.uds.cdrglob.latest
    file.info.form.json.educ, subject.info.demographics.uds.education-level.latest
    file.info.form.json.primlang, subject.info.demographics.uds.primary-language.latest

    For all "latest":
      - create dict with value and session date
      - compare with existing latest object
      - replace object if session date is newer
    """

    def __init__(self,
                 context: Optional[GearToolkitContext] = None,
                 extra_packages: Optional[List[str]] = None,
                 **kwargs) -> None:  # type: ignore
        super().__init__(context, extra_packages, **kwargs)
        self.__symbol_table = SymbolTable()

    def get_subject(self, file_entry: FileEntry) -> Subject:
        """Get the subject for the file entry.

        Args:
          file_entry: the file entry
        Returns:
          the Subject for the file entry
        """
        parents_subject = file_entry.parents.get("subject")
        return self.context.client.get_subject(parents_subject)

    def curate_form(self, form: UDSV3Form) -> None:
        """Computes and sets derived variables for the form."""
        if not form.is_initial_visit():
            return

        form_date = form.get_form_date(
        )  # not sure what we do if form_date is None, probably should be an exception
        self.__symbol_table['mapped.info.form.age'] = form.get_age_in_years(
            form_date) if form_date else ''
        self.__symbol_table['mapped.info.form.race'] = form.get_subject_race()
        self.__symbol_table['mapped.info.form.sex'] = form.get_subject_sex()
        self.__symbol_table[
            'mapped.info.form.primlang'] = form.get_primary_language()

        form.update_info(self.__symbol_table.get('file.info', {}))

    def set_latest(self, *, target_key: str, source_key: str,
                   update_date: datetime) -> None:
        """Sets the value at the target_key to the new value if the new value
        is not null, and the date is more recent.

        Args:
          target_key: the target key for data
          source_key: the key for value to update with
          date: the date corresponding to the new value
        """
        source_value = self.__symbol_table.get(source_key)
        if source_value is None:
            return

        target_value = self.__symbol_table.get(target_key)
        if target_value:
            previous_date = datetime_from_form_date(target_value['date'])
            if previous_date > update_date:
                return

        self.__symbol_table[target_key] = {
            'value': source_value,
            'date': update_date.strftime("%Y-%m-%d")
        }

    def insert_form_version(self, *, subject_version_key: str,
                            form_version_key: str) -> None:
        """Inserts the form version into the subject versions.

        Assumes subject versions is a list of strings

        Args:
          subject_version_key: the key for subject form versions
          form_version_key: the key for the form version
        """
        form_version_value = self.__symbol_table.get(form_version_key)
        assert form_version_value

        versions = self.__symbol_table.get(subject_version_key, [])
        # version_set = set(versions) if versions else set()
        version_set = set()
        if versions:
            version_set = {
                version
                for version in versions if re.match(r"UDSv[1-4]", version)
            }
        version_set.add(f"UDSv{int(float(form_version_value))}")
        self.__symbol_table[subject_version_key] = list(version_set)

    def curate_subject(self, subject: Subject, form: UDSV3Form) -> None:
        """Curates subject object info using the assignments to set latest
        value.

        Args:
          subject: the subject to update
          assignments: the list of assignments for updates
          date: the date to check for latest assignments
        """

        self.insert_form_version(
            subject_version_key='subject.info.study-parameters.uds.versions',
            form_version_key='file.info.forms.json.formver')

        assignments = []
        if form.is_initial_visit():
            assignments = [{
                'target_key': 'subject.info.demographics.uds.age.latest',
                'source_key': 'mapped.info.form.age'
            }, {
                'target_key': 'subject.info.demographics.uds.race.latest',
                'source_key': 'mapped.info.form.race'
            }, {
                'target_key': 'subject.info.demographics.uds.sex.latest',
                'source_key': 'mapped.info.form.sex'
            }, {
                'target_key':
                'subject.info.demographics.uds.primary-language.latest',
                'source_key': 'mapped.info.form.primlang'
            }, {
                'target_key':
                'subject.info.demographics.uds.education-level.latest',
                'source_key': 'file.info.forms.json.educ'
            }]
        assignments.append({
            'target_key': 'subject.info.cognitive.uds.cdrglob.latest',
            'source_key': 'file.info.forms.json.cdrglob'
        })
        update_date = form.get_form_date()
        assert update_date
        for assignment in assignments:
            self.set_latest(**assignment, update_date=update_date)

        subject.update(info=self.__symbol_table.get('subject.info', {}))

    def curate_file(self, file_: Dict[str, Any]) -> None:
        """Performs curation on the file object and corresponding subject."""

        file_entry = self.get_file_entry(file_)
        subject = self.get_subject(file_entry)

        self.__symbol_table['file.info'] = file_entry.info
        self.__symbol_table['subject.info'] = subject.info

        form = UDSV3Form(file_entry)
        if not form.is_form(name='uds'):
            return

        self.curate_form(form)
        self.curate_subject(subject=subject, form=form)

    def get_file_entry(self, file_: Dict[str, Any]) -> FileEntry:
        """Retrieves the FileEntry represented by the dictionary object.

        Args:
          file_: dictionary object representing FileEntry
        Returns:
          the FileEntry corresponding to the dictionary
        """
        acq = self.context.get_container_from_ref(file_.get("hierarchy"))
        filename = self.context.get_input_filename("file-input")
        file_entry = acq.get_file(filename)
        return file_entry
