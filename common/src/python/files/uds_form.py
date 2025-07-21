"""Defines the form class for UDSv3 forms."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from dates.dates import datetime_from_form_date

from files.form import Form

log = logging.getLogger(__name__)


class UDSV3Form(Form):
    """Class for UDSv3 forms."""

    RACE_MAPPING = {
        1: "White",
        2: "Black or African American",
        3: "American Indian or Alaska Native",
        4: "Native Hawaiian or Other Pacific Islander",
        5: "Asian",
        50: "Unknown or Not Reported",
        88: "Unknown or Not Reported",
        99: "Unknown or Not Reported",
    }
    MORE_THAN_ONE = "More Than One Race"

    def get_subject_race(self) -> str:
        """Gets the race from a UDSv3 file.

        Uses variables race, racesec, and raceter to determine race for subject
        in Flywheel.

        Returns:
          Flywheel race value
        """
        race_code = self.get_metadata("race")
        if not race_code:
            return self.UNKNOWN
        if race_code in ["50", "88", "99"]:
            return self.UNKNOWN

        race = self.RACE_MAPPING.get(int(race_code))
        if not race:
            log.warning(
                "race value %s unknown, setting to Unknown or Not Reported", race_code
            )
            return self.UNKNOWN

        secondary_code = self.get_metadata("racesec")
        if secondary_code:
            if self.RACE_MAPPING.get(int(secondary_code), self.UNKNOWN) != self.UNKNOWN:
                return self.MORE_THAN_ONE

        tertiary_code = self.get_metadata("raceter")
        if tertiary_code:
            if self.RACE_MAPPING.get(int(tertiary_code), self.UNKNOWN) != self.UNKNOWN:
                return self.MORE_THAN_ONE

        return race

    ETHNICITY_MAPPING = {
        0: "Not Hispanic or Latino",
        1: "Hispanic or Latino",
        9: "Unknown or Not Reported",
    }
    UNKNOWN = "Unknown or Not Reported"

    def get_subject_ethnicity(self) -> str:
        """Gets the ethnicity from the file.

        Returns:
          FW subject ethnicity value
        """
        ethnicity_code = self.get_metadata("ethnicity")
        if not ethnicity_code:
            return self.UNKNOWN
        if ethnicity_code == 9:
            return self.UNKNOWN

        ethnicity = self.ETHNICITY_MAPPING.get(int(ethnicity_code))
        if ethnicity:
            return ethnicity

        log.warning(
            "ethnicity value %s unknown, setting to Unknown or Not Reported",
            ethnicity_code,
        )
        return self.UNKNOWN

    SEX_MAPPING = {1: "male", 2: "female"}

    def get_subject_sex(self) -> Optional[str]:
        """Gets the subject sex from the UDSv3 file entry.

        Returns:
          sex value determined from data file
        """
        sex_code = self.get_metadata("sex")
        if not sex_code:
            return None

        sex = self.SEX_MAPPING.get(int(sex_code), None)
        if sex:
            return sex

        log.warning("sex value %s unknown, and won't be set", sex_code)
        return None

    def get_subject_dob(self) -> Optional[datetime]:
        """Gets the subject date of birth from the UDSv3 file entry.

        Returns:
          date of birth determined from the data file, None if not found
        """
        birth_year = self.get_metadata("birthyr")
        if not birth_year:
            return None

        birth_month = self.get_metadata("birthmo")
        if not birth_month:
            return None

        # Set the day to the first of the birth month
        dob = datetime(int(birth_year), int(birth_month), 1)
        return dob

    def get_subject_initial_info_fields(self) -> Dict[str, Dict[str, Any]]:
        """Builds a subject info dictionary from the file. Gathers visit date
        and demographic information.

        Returns:
          info dictionary
        """
        visit_date = self.get_metadata("vstdate_a1")
        center_id = self.get_metadata("adcid")
        participant_id = self.get_metadata("ptid")
        demographic_info = self.get_demographics()

        info = {
            **demographic_info,
            "enrollment": {
                "adcid": center_id,
                "ptid": participant_id,
                "initial-visit-date": visit_date,
            },
        }
        return info

    EDUC_MAPPING = {
        12: "High School or GED",
        16: "Bachelor's degree",
        18: "Masters's degree",
        20: "Doctorate",
        99: "Unknown or Not Reported",
    }

    LANG_MAPPING = {
        1: "English",
        2: "Spanish",
        3: "Mandarin",
        4: "Cantonese",
        5: "Russian",
        6: "Japanese",
        8: "Other",
        9: "Unknown or Not Reported",
    }

    def get_demographics(self) -> Dict[str, Dict[str, Any]]:
        """Gathers demographic information from the file.

        Returns:
          dictionary containing demographic information
        """
        education_code = self.get_metadata("educ")
        education = "Unknown or Not Reported"
        if education_code:
            education = self.EDUC_MAPPING.get(
                int(education_code), f"{education_code} years completed"
            )

        primlang_code = self.get_metadata("primlang")
        if primlang_code:
            primlang = self.LANG_MAPPING.get(
                int(primlang_code), "Unknown or Not Reported"
            )
        else:
            primlang = "Unknown or Not Reported"

        return {"demographics": {"education": education, "primary-language": primlang}}

    def get_cdr_info(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Gets CDR data from the file.

        Returns:
          dictionary with the CDR global score and sum-of-boxes from the form
        """
        visit_date = self.get_metadata("vstdate_a1")
        cdr_global = self.get_metadata("cdrglob")
        cdr_sum = self.get_metadata("cdrsum")
        info = {
            "cognitive": {
                "cdr-latest": {
                    "cdrglob": cdr_global,
                    "cdrsum": cdr_sum,
                    "date": visit_date,
                }
            }
        }
        return info

    def get_weight_at_session(self) -> Optional[float]:
        """Gets the weight in kilograms for the weight given in the UDSv3 data
        file.

        Args:
        file_o: the file entry
        """
        weight_lbs = self.get_metadata("weight")
        if weight_lbs is None:
            return None

        if weight_lbs in [888, 999]:
            return None

        return round(float(weight_lbs) * 0.45359237, 2)  # Lb to Kg conversion

    def get_session_date(self) -> Optional[datetime]:
        """Get date of session from visit date on A1 form of UDSv3.

        Args:
        file_o: the UDSv3 file entry
        Returns:
        the date time value for the A1 visit, None if not found
        """
        visit_datetime = None
        visit_date = self.get_metadata("vstdate_a1")
        if visit_date:
            visit_datetime = datetime_from_form_date(visit_date)
        return visit_datetime

    def get_age_at_session(self, visit_datetime: datetime) -> Optional[int]:
        """Get age at session.

        Computes difference between visit date and the first of birth month.

        Args:
        file_o: the file entry for UDSv3 file
        visit_datetime: the visit date
        """

        birth_datetime = self.get_subject_dob()
        if not birth_datetime:
            return None

        diff_datetime = visit_datetime - birth_datetime
        return int(
            diff_datetime.total_seconds()
        )  # Age is stored in seconds on flywheel
