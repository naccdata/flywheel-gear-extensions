# """Utilities for curating UDSv3 forms."""

# import logging
# from typing import Any, Dict, Optional

# from dates.dates import datetime_from_form_date, get_localized_timestamp
# from files.uds_form import UDSV3Form
# from flywheel import Session, Subject
# from flywheel.models.file_entry import FileEntry

# from curator.form_curator import FormCurator, curate_session_timestamp

# log = logging.getLogger(__name__)

# class UDSv3Curator(FormCurator):
#     """File Curator for UDSv3 Forms."""

#     def curate_form(self, file_entry: FileEntry):
#         """Curates metadata for UDSv3 forms.

#         Arg:
#           file_entry: the file entry for the form
#         """
#         form = UDSV3Form(file_entry)
#         subject = self.get_subject(file_entry)

#         packet = form.get_variable("packet")
#         if packet and packet.startswith("I"):
#             curate_subject_initial(subject=subject, form=form)

#         session = self.get_session(file_entry)
#         curate_session(subject, session, form)

# def curate_session(subject: Subject, session: Session, form: UDSV3Form):
#     """Set session attributes.

#     Args:
#         subject (Subject): the subject object
#         session (Session): the session object
#         Form (UDSV3Form): the file entry for UDSv3 file
#     """

#     # Set session weight
#     weight_kg = form.get_weight_at_session()
#     if weight_kg:
#         session.update({"weight": weight_kg})
#     else:
#         log.warning("Weight unknown for %s", session.label)

#     visit_datetime = form.get_form_date()
#     if not visit_datetime:
#         log.warning("No visit date given for %s", session.label)
#         return

#     # Set session timestamp
#     curate_session_timestamp(session, form)

#     # Set age at session
#     age = form.get_age_at_session(visit_datetime)
#     if age:
#         session.update({"age": age})
#     else:
#         log.warning("Age unknown for %s", session.label)

#     # Set/update latest CDR info for the subject
#     set_subject_cdr_info(subject, form)

# def curate_subject_initial(*, subject: Subject, form: UDSV3Form):
#     """Sets subject fields based on data from a UDSv3 data file for an initial
#     visit.

#     Args:
#         subject: the subject object
#         form: the UDSv3 form object
#     """
#     subject.update(type="human")
#     sex = form.get_subject_sex()
#     race = form.get_subject_race()
#     ethnicity = form.get_subject_ethnicity()
#     dob_timestamp = None
#     date_of_birth = form.get_subject_dob()
#     if date_of_birth:
#         dob_timestamp = get_localized_timestamp(date_of_birth)
#     else:
#         log.warning("DOB undetermined for %s", subject.label)
#     info = form.get_subject_initial_info_fields()

#     subject.update(
#         firstname="not-collected",
#         lastname="not-collected",
#         sex=sex,
#         cohort="Study",
#         race=race,
#         ethnicity=ethnicity,
#         date_of_birth=dob_timestamp,
#         info=info,
#     )

# def set_subject_cdr_info(subject: Subject, form: UDSV3Form):
#     """Sets the latest CDR info for the subject.

#     Args:
#     subject: the subject object
#     form: the file entry for the file
#     """
#     cdr_info = form.get_cdr_info()
#     current_date = dotty_get(cdr_info, "cognitive.cdr-latest.date")
#     assert current_date
#     last_date = dotty_get(subject.info, "cognitive.cdr-latest.date")
#     assert last_date

#     if last_date:
#         current_date = datetime_from_form_date(current_date)
#         last_date = datetime_from_form_date(last_date)

#     if current_date > last_date:
#         log.debug("Updating subject CDR info with new values")
#         subject.update(info=cdr_info)
#     else:
#         log.debug("Setting subject CDR info")
#         subject.update(info=cdr_info)

# def dotty_get(full_dict: Dict[str, Any], dotty_key: str) -> Optional[Any]:
#     """Gets value by hierarchical key from dictionary.

#     A hierarchical key is of the form "top.middle.bottom".

#     Args:
#       full_dict: a hierarchical dictionary
#       dotty_key: a hierarchical key
#     Returns:
#       value from lowest dictionary corresponding to key,
#       None if key doesn't match
#     """
#     keys = dotty_key.split(".")
#     val = full_dict
#     while keys:
#         key = keys.pop(0)
#         val = val.get(key, {})
#     if not val:
#         return None

#     return val
