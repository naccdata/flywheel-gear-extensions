import logging
import re
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Dict, Iterator, List, MutableMapping, Optional

from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from flywheel_gear_toolkit import GearToolkitContext
from flywheel_gear_toolkit.utils.curator import FileCurator

log = logging.getLogger(__name__)
# log.setLevel("DEBUG")


def create_naccnihr(race: Optional[int], racex: Optional[str],
                    racesec: Optional[int], racesecx: Optional[str],
                    raceter: Optional[int], raceterx: Optional[str]) -> int:

    if not race:
        return 99

    whitex = 0
    blackx = 0
    nativex = 0
    hawaiix = 0
    asianx = 0
    multix = 0
    multipx = 0
    unx = 0

    white_responses = {
        "arab",
        "arabic",
        "armenian",
        "ashkenazijew",
        "asirian",
        "assyrian",
        "australian",
        "caucasian",
        "cicilan",
        "dutch",
        "easterneurope",
        "easterneuropean",
        "easterneuropean/jewish",
        "egyptian",
        "england",
        "english",
        "european",
        "european/english",
        "europeanamerican",
        "french",
        "frenchamerican",
        "german",
        "german/european",
        "germanic",
        "grece",
        "greek",
        "hispanic",
        "hollander",
        "hungarian",
        "iranian",
        "irish",
        "italian-american",
        "italian",
        "itialianamerican",
        "jewish",
        "lebanese",
        "lebannon",
        "maltese",
        "middleeast",
        "middleeasten",
        "middleeastern",
        "middleeasternisraeli",
        "norweigian",
        "persian",
        "polandromania",
        "polish",
        "portugese",
        "portuguese",
        "romanian",
        "russian,polish",
        "russian",
        "scandinavian",
        "scotch"
        "scotch",
        "scotch/irish",
        "sephardicjewish",
        "sicilian",
        "sicilian/french",
        "somepersian",
        "spanish",
        "spanishfromspain",
        "swedish,irish.russian",
        "switzerland",
        "syria,caucasian,arabic,french,hebrew",
        "syrian",
        "turkish",
        "turkish/arab",
        "ukrain",
        "westerneurope",
    }

    black_responses = {
        "african american",
        "bahamanian",
        "bahamas",
        "barbadian",
        "barbardian",
        "black/african-american",
        "caribbean",
        "caribian",
        "dominican/hispanic",
        "eritrian",
        "haitian",
        "hatian",
        "hispanic dominican",
        "jamacian",
        "jamaica",
        "jamaican",
        "nigerian",
        "trinidadian",
        "west indian",
        "west indies"
        "west indies",
        "west indies",
    }

    native_american_responses = {
        "native america",
        "native american",
    }

    pacific_islander_responses = {
        "samoan",
        "tahitian",
    }

    asian_responses = {
        "asian indian",
        "asian",
        "chinese american",
        "chinese",
        "east indian",
        "filipino american",
        "filipino",
        "india south indian",
        "india",
        "indian",
        "japanese american",
        "japanese",
        "korean",
        "malay",
        "okanawa japanese",
        "phillipino",
        "south asian",
        "sri lankan",
        "vietnamese",
    }

    multiracial_responses = {
        "bi-racial",
        "biracial",
        "black hispanic",
        "caucasian/asian",
        "dutch indonesian",
        "half hisp/half white",
        "hispanic- mestiza",
        "japanese caucasian",
        "mestino",
        "mestito",
        "mestiza",
        "mestizo",
        "meztizo",
        "mix black and white",
        "mixed cuban",
        "mixed race",
        "mixed",
        "moreno/mestizo",
        "mulato",
        "mulato/black and white",
        "mulit-racial",
        "multi -racial",
        "multi racial",
        "multi- racial",
        "multi-racial",
        "multiracial",
        "mututo",
        "white/african american",
    }

    multiple_race_responses = {
        "african and american indian",
        "canadian indian",
        "caribbean indian",
        "dutch indonesian",
        "east indian",
        "east indian/jamacican",
        "jamaican indian",
        # "korean",
        "mix black and white",
        "mixed black and white",
        "panamanian",
        "puerto rican",
        # "sicilian"
        "wht/blk",
    }

    unknown_responses = {
        "brazilian", "brown", "columbian", "criollo", "cuban", "guyanese",
        "hispan ic", "hispanic", "hispanic/ latino", "hspanic", "human",
        "humana", "indian", "indigenous", "indio", "latin,trigueno",
        "latina hispanic", "latina", "latino", "mexican american", "mexican",
        "other", "puerto rican", "puerto rician", "refused", "see report",
        "usa"
    }

    if racex:
        whitex = 1 if racex.lower() in white_responses else whitex

    if race == 1 and racesec == 50 and racesecx:
        whitex = 1 if racesecx.lower() in white_responses else whitex

    if raceterx:
        whitex = 1 if raceterx.lower() in white_responses else whitex

    whitex = 0 if race == 1 and raceter == 3 else whitex

    if racesecx:
        blackx = 1 if racesecx.lower() in black_responses else blackx
    if racex:
        blackx = 1 if racex.lower() in black_responses else blackx
        nativex = 1 if racex.lower() in native_american_responses else nativex
        hawaiix = 1 if racex.lower() in pacific_islander_responses else hawaiix
        asianx = 1 if racex.lower() in asian_responses else asianx
        multix = 1 if racex.lower() in multiracial_responses else multix

    if racesecx:
        hawaiix = 1 if racesecx.lower(
        ) in pacific_islander_responses else hawaiix
        asianx = 1 if racesecx.lower() in asian_responses else asianx
        multix = 1 if racesecx.lower() in multiracial_responses else multix

    if racex:
        multipx = 1 if racex.lower() in multiple_race_responses else multipx
        multipx = 1 if racesec == 3 and racex == "European" else multipx
    if racesecx:
        multipx = 1 if race in {2, 3, 4, 5
                                } and racesecx == "Irish" else multipx
    if raceterx:
        multipx = 1 if race == 1 and raceter == 50 and raceterx == "Irish" else multipx
    if racesecx and raceterx:
        multipx = 1 if race == 50 and racesecx == "German" and raceterx == "Central American Indian" else multipx
    if raceterx:
        multipx = 1 if race == 3 and raceterx == "Irish" else multipx
    if racesecx:
        multipx = 1 if race == 3 and racesecx == "Irisih" else multipx
        multipx = 1 if race == 4 and racesecx == "Filipino" else multipx
    if raceterx:
        multipx = 1 if race == 1 and raceterx == "NATIVE AMERICAN" else multipx
    if racesecx and raceterx:
        multipx = 1 if race == 5 and racesecx == "Portuguese" and raceterx == "Slovene" else multipx
        multipx = 1 if race == 5 and racesecx == "Korean" and raceterx == "Portuguese" else multipx
    if racesecx:
        multipx = 1 if race == 1 and racesecx == "West Indian" else multipx
        multipx = 1 if racesecx.lower() in multiple_race_responses else multipx
    if raceterx:
        multipx = 1 if raceterx.lower() in multiple_race_responses else multipx

    if racex:
        unx = 1 if racex.lower() in unknown_responses else unx

    naccnihr = race

    naccnihr = 6 if race == 1 and raceter in {2, 3, 4} else naccnihr
    naccnihr = 6 if race == 1 and racesec in {2, 3, 4, 5, 50} else naccnihr
    naccnihr = 6 if (race == 1 or race == 50) and multix == 1 else naccnihr
    naccnihr = 1 if (race == 1 or race == 50) and whitex == 1 else naccnihr
    naccnihr = 6 if race == 2 and raceter in {1, 3} else naccnihr
    naccnihr = 6 if race == 2 and racesec in {1, 3, 4, 5, 50} else naccnihr
    naccnihr = 6 if race == 3 and racesec in {1, 2, 5} else naccnihr
    naccnihr = 6 if race == 4 and racesec in {1, 2, 3, 5} else naccnihr
    naccnihr = 6 if race == 5 and racesec in {1, 2, 3, 4} else naccnihr
    naccnihr = 6 if race == 5 and whitex == 1 else naccnihr
    naccnihr = 5 if (race == 5 | race == 50) and asianx == 1 else naccnihr
    naccnihr = 6 if race == 5 and asianx == 1 and whitex == 1 else naccnihr

    naccnihr = 6 if race == 50 and racesec == 5 and raceter in {1, 2, 3, 4
                                                                } else naccnihr
    naccnihr = 6 if racesec == 5 and raceter in {1, 2, 3} else naccnihr
    naccnihr = 6 if race == 50 and racesec == 4 and raceter == 1 else naccnihr
    naccnihr = 6 if race == 50 and racesec == 1 else naccnihr

    naccnihr = 99 if race == 99 and racesec in {2, 3} else naccnihr

    naccnihr = 99 if race == 50 and unx == 1 else naccnihr

    naccnihr = 6 if multipx == 1 else naccnihr
    naccnihr = 6 if multix == 1 else naccnihr

    naccnihr = 4 if race == 50 and hawaiix == 1 else naccnihr
    naccnihr = 6 if race == 50 and asianx == 1 and whitex == 1 else naccnihr
    naccnihr = 6 if race == 50 and asianx == 1 and hawaiix == 1 else naccnihr
    naccnihr = 3 if race == 50 and nativex == 1 else naccnihr
    naccnihr = 5 if race == 50 and asianx == 1 else naccnihr
    naccnihr = 99 if (race == 50 and whitex != 1 and blackx != 1
                      and hawaiix != 1 and asianx != 1 and multix != 1
                      and multipx != 1 and nativex != 1) else naccnihr
    naccnihr = 6 if race == 50 and racesec == 2 and raceter == 3 else naccnihr
    naccnihr = 2 if blackx == 1 else naccnihr

    naccnihr = 6 if blackx == 1 and race == 50 and racesec == 1 and raceter in {
        2, 3, 4, 5
    } else naccnihr
    naccnihr = 6 if blackx == 1 and race == 50 and racesec == 5 else naccnihr

    naccnihr = 6 if racex == "HISPANIC" and racesecx == "MEZTIZA" else naccnihr

    return naccnihr


class Form(ABC):
    """Base class for forms."""

    def __init__(self, file_object: FileEntry) -> None:
        self.__file_object = file_object

    def get_variable(self, key: str) -> Optional[Any]:
        """Get the data value for the specified key from the form data file.

        Args:
            key (str): attribute key

        Returns:
            attribute value
        """
        return self.__file_object.get("info", {}).get("forms",
                                                      {}).get("json").get(key)

    def update_info(self, values: Dict[str, Any]) -> None:
        """Updates the custom info for the file of this form.

        Args:
          values: the dictionary to update with
        """
        self.__file_object.update_info(values)

    @abstractmethod
    def get_form_date(self) -> Optional[datetime]:
        """Gets the date of the session of form.

        Returns:
          the date of session
        """
        return None

    def is_form(self,
                name: Optional[str] = None,
                version: Optional[str] = None) -> bool:
        """Checks if the file object is a form. Also, checks module name and
        version if provided.

        Note: tests the info of the file.

        Args:
          name: the module name (optional)
          version: the version (optional)
        Returns:
          True if the file is a form, and matches name and version if given.
          False otherwise.
        """
        if not self.__file_object.get("info").get("forms"):
            return False

        if not name:
            return True

        module = self.get_variable('module')
        assert module, "assume module is set"
        if name.lower() != module.lower():
            return False

        if not version:
            return True

        form_version = self.get_variable('formver')
        assert form_version, "assume formver is set"
        return version.lower() != str(form_version).lower()


def datetime_from_form_date(date_string: str) -> datetime:
    """Converts date string to datetime based on format.

    Expects either `%Y-%m-%d` or `%m/%d/%Y`.

    Args:
      date_string: the date string
    Returns:
      the date as datetime
    """
    if re.match(r"\d{4}-\d{2}-\d{2}", date_string):
        return datetime.strptime(date_string, "%Y-%m-%d")

    return datetime.strptime(date_string, "%m/%d/%Y")


class UDSV3Form(Form):
    """Class for curation of UDSv3 forms."""

    def is_initial_visit(self) -> bool:
        """Indicates whether this form represents an initial visit packet.

        Returns:
          True if this form is an initial visit packet. False, otherwise.
        """
        packet = self.get_variable('packet')
        if not packet:
            return False

        return packet.startswith('I')

    def get_form_date(self) -> Optional[datetime]:
        """Get date of session from visit date on A1 form of UDSv3.

        Args:
        file_o: the UDSv3 file entry
        Returns:
        the date time value for the A1 visit, None if not found
        """
        visit_datetime = None
        visit_date = self.get_variable("visitdate")
        if visit_date:
            visit_datetime = datetime_from_form_date(visit_date)
        return visit_datetime

    def get_subject_dob(self) -> Optional[datetime]:
        """Gets the subject date of birth from the UDSv3 file entry.

        Returns:
          date of birth determined from the data file, None if not found
        """
        birth_year = self.get_variable("birthyr")
        if not birth_year:
            return None

        birth_month = self.get_variable("birthmo")
        if not birth_month:
            return None

        # Set the day to the first of the birth month
        dob = datetime(int(birth_year), int(birth_month), 1)
        return dob

    def get_age_in_years(self, date: datetime) -> Optional[int]:
        """Get age at session.

        Computes difference between visit date and the first of birth month.

        Args:
        file_o: the file entry for UDSv3 file
        visit_datetime: the visit date
        """

        birth_datetime = self.get_subject_dob()
        if not birth_datetime:
            return None

        diff_datetime = date - birth_datetime
        return diff_datetime // timedelta(days=365)

    RACE_MAPPING = MappingProxyType({
        1: "White",
        2: "Black or African American",
        3: "American Indian or Alaska Native",
        4: "Native Hawaiian or Other Pacific Islander",
        5: "Asian",
        6: "Multiracial",
        50: "Unknown or ambiguous",
        88: "Unknown or ambiguous",
        99: "Unknown or ambiguous",
    })

    def get_subject_race(self) -> str:

        racecode = create_naccnihr(race=self.get_variable('race'),
                                   racex=self.get_variable('racex'),
                                   racesec=self.get_variable('racesec'),
                                   racesecx=self.get_variable('racesecx'),
                                   raceter=self.get_variable('raceter'),
                                   raceterx=self.get_variable('raceterx'))

        if not racecode:
            return 'Unknown or ambiguous'
        if racecode in ['50', '88', '99']:
            return 'Unknown or ambiguous'

        race_string = self.RACE_MAPPING.get(int(racecode))
        if not race_string:
            return 'Unknown or ambiguous'

        return race_string

    SEX_MAPPING = MappingProxyType({1: "Male", 2: "Female"})

    def get_subject_sex(self) -> Optional[str]:
        """Gets the subject sex from the UDSv3 file entry.

        Returns:
          sex value determined from data file
        """
        sex_code = self.get_variable("sex")
        if not sex_code:
            return None

        return self.SEX_MAPPING.get(int(sex_code), None)

    LANG_MAPPING = MappingProxyType({
        1: "English",
        2: "Spanish",
        3: "Mandarin",
        4: "Cantonese",
        5: "Russian",
        6: "Japanese",
        8: "Other",
        9: "Unknown or Not Reported",
    })

    def get_primary_language(self) -> Optional[str]:

        primlang_code = self.get_variable("primlang")
        if primlang_code:
            return self.LANG_MAPPING.get(int(primlang_code),
                                         "Unknown or Not Reported")
        else:
            return "Unknown or Not Reported"


class SymbolTable(MutableMapping):
    """Implements a dictionary like object for using metadata paths as keys."""

    def __init__(self, symbol_dict: Optional[Dict[str, Any]] = None) -> None:
        self.__table = symbol_dict if symbol_dict else {}

    def __setitem__(self, key: str, value: Any) -> None:
        table = self.__table
        key_list = deque(key.split('.'))
        while key_list:
            sub_key = key_list.popleft()
            obj = table.get(sub_key)
            if not obj:
                if not key_list:
                    table[sub_key] = value
                    return

                table[sub_key] = {}
                table = table[sub_key]
                continue

            if not key_list:
                table[sub_key] = value
                return

            if not isinstance(obj, dict):
                # TODO: raise something ?
                # log.error("expecting dict, got %s", type(obj))
                return None

            table = obj

    def __getitem__(self, key: str) -> Optional[Any]:
        value = self.__table
        key_list = key.split('.')
        while key_list:
            sub_key = key_list.pop(0)
            if not isinstance(value, dict):
                raise KeyError()

            value = value.get(sub_key)

        return value

    def __delitem__(self, key: Any) -> None:
        return

    def __iter__(self) -> Iterator:
        return self.__table.__iter__()

    def __len__(self) -> int:
        return len(self.__table)


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
          date: the date to check for lastest assignments
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
