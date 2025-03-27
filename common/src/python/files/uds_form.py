"""Defines the form class for UDSv3 forms."""
import logging
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Optional

from dates.dates import datetime_from_form_date

from files.form import Form

log = logging.getLogger(__name__)


def create_naccnihr(  # noqa: C901
        race: Optional[int], racex: Optional[str], racesec: Optional[int],
        racesecx: Optional[str], raceter: Optional[int],
        raceterx: Optional[str]) -> int:

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
        multipx = 1 if (race == 50 and racesecx == "German"
                        and raceterx == "Central American Indian") else multipx
    if raceterx:
        multipx = 1 if race == 3 and raceterx == "Irish" else multipx
    if racesecx:
        multipx = 1 if race == 3 and racesecx == "Irisih" else multipx
        multipx = 1 if race == 4 and racesecx == "Filipino" else multipx
    if raceterx:
        multipx = 1 if race == 1 and raceterx == "NATIVE AMERICAN" else multipx
    if racesecx and raceterx:
        multipx = 1 if (race == 5 and racesecx == "Portuguese"
                        and raceterx == "Slovene") else multipx
        multipx = 1 if (race == 5 and racesecx == "Korean"
                        and raceterx == "Portuguese") else multipx
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


class UDSV3Form(Form):
    """Class for curation of UDSv3 forms."""

    @classmethod
    def create(cls, form: Form) -> 'UDSV3Form':
        return form  # type: ignore

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
