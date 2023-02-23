import pytz
import time
import os
import pandas as pd
from flywheel_gear_toolkit.utils.reporters import AggregatedReporter, BaseLogRecord
from flywheel_gear_toolkit.utils.curator import HierarchyCurator
import flywheel
from dataclasses import dataclass
import datetime
import collections
import numpy as np
__version__ = "1.0.2"
print(f'Curator Script Version {__version__}')
# Changelog:

# 1.0.2
# Parsing out certian metadata for subjects, sessions, and acquisitions.
# Removed print statements

# 1.0.1
# Better container names

# 1.0.0
# Initial Version


"""
Constants to be set for run:

- These will be set by the info on the project's metadata in:
project.info.<NAMESPACE>.<PIPELINE_NAME>

"""

PIPELINE_NAME = "CreateContainers"
NAMESPACE = "HierarchyCurator"
BASE_DIR = "/flywheel/v0"
# BASE_DIR="/Users/davidparker/Documents/Flywheel/Clients/NACC/HierarchyCurator/CreateContainers"

GLOBAL_SETTINGS = {"PROJECT_COLUMN": "project",
                   "SUBJECT_COLUMN": "subject",
                   "SESSION_COLUMN": "session",
                   "ACQUISITION_COLUMN": "acquisition"}

LOG_OBJECT = {'csv_project': "",
              'csv_subject': "",
              'csv_session': "",
              'csv_acquisition': "",
              'flywheel_project': "",
              'flywheel_subject': "",
              'flywheel_session': "",
              'flywheel_acquisition': "",
              'project_created': False,
              'project_existed': False,
              'subject_existed': False,
              'session_existed': False,
              'acquisition_existed': False,
              'subject_created': False,
              'session_created': False,
              'acquisition_created': False,
              'msg': "",
              'error': False}


def reset_log():
    global LOG_OBJECT
    LOG_OBJECT = {'csv_project': "",
                  'csv_subject': "",
                  'csv_session': "",
                  'csv_acquisition': "",
                  'flywheel_project': "",
                  'flywheel_subject': "",
                  'flywheel_session': "",
                  'flywheel_acquisition': "",
                  'project_created': False,
                  'project_existed': False,
                  'subject_existed': False,
                  'session_existed': False,
                  'acquisition_existed': False,
                  'subject_created': False,
                  'session_created': False,
                  'acquisition_created': False,
                  'msg': "",
                  'error': False}


def get_global_settings(fw_client, destination_id):
    global GLOBAL_SETTINGS, NAMESPACE, PIPELINE_NAME

    dest = fw_client.get(destination_id)
    if dest.container_type == "project":
        project = dest
    else:
        project = fw_client.get_project(dest.parents["project"])

    info = project.info

    if NAMESPACE not in project.info:
        print(f"{NAMESPACE} not in project info, creating")
        info[NAMESPACE] = {}

    if PIPELINE_NAME not in info[NAMESPACE]:
        print(f"{PIPELINE_NAME} not in project info, creating")
        info[NAMESPACE][PIPELINE_NAME] = GLOBAL_SETTINGS
    project.update_info(info)

    for key in GLOBAL_SETTINGS.keys():
        GLOBAL_SETTINGS[key] = info[NAMESPACE][PIPELINE_NAME].get(key)


@dataclass
class MapLogRecord(BaseLogRecord):
    """
    This is simply the format of the output log report file that the curator will generate.
    """
    csv_project: str = ""
    csv_subject: str = ""
    csv_session: str = ""
    csv_acquisition: str = ""
    flywheel_project: str = ""
    flywheel_subject: str = ""
    flywheel_session: str = ""
    flywheel_acquisition: str = ""
    project_existed: bool = False
    subject_existed: bool = False
    session_existed: bool = False
    project_created: bool = False
    acquisition_existed: bool = False
    subject_created: bool = False
    session_created: bool = False
    acquisition_created: bool = False
    msg: str = ""
    error: bool = False


class Curator(HierarchyCurator):
    def __init__(self, **kwargs):
        # Install backoff
        super().__init__(**kwargs)
        # curate depth first
        self.config.multi = False
        self.config.depth_first = False
        self.config.stop_level = "session"
        self.config.report = True
        self.config.format = MapLogRecord

        # Use this value for execution on flywheel:
        self.config.path = f"{BASE_DIR}/output/curation_report.csv"
        # Use (and modify as necessary) this value for local testing:
        # self.config.path = "/Users/davidparker/Documents/Flywheel/Clients/MtSinai/Curator_Scripts/Launch_Gears/report.csv"

        self.legacy = True
        self.depth_first = self.config.depth_first

        if self.config.report:
            self.reporter = AggregatedReporter(
                self.config.path, format=self.config.format
            )

        # Use this value for execution on flywheel:
        self.fw_client = self.context.client
        # Use (and modify as necessary) this value for local testing:
        #self.fw_client = flywheel.Client(os.environ["FWGA_API"])
        get_global_settings(self.fw_client, self.context.destination.get("id"))
        # self.additional_input_one='/Users/davidparker/Documents/Flywheel/Clients/NACC/HierarchyCurator/CreateContainers/investigator_nacc57_abridged_FullCol.csv'

    def find_or_create(self, container_name, type, parent):
        global LOG_OBJECT
        current_c = find_container(
            self.fw_client, container_name, type, parent)
        if len(current_c) > 0:
            current_c = current_c[0]
            LOG_OBJECT[f'{type}_existed'] = True
            LOG_OBJECT[f'flywheel_{type}'] = current_c.id

        else:
            LOG_OBJECT[f'{type}_existed'] = False

            try:
                current_c = create_container(parent, container_name, type)
                LOG_OBJECT[f'{type}_created'] = True
                LOG_OBJECT[f'flywheel_{type}'] = current_c.id

            except Exception as e:
                print(e)
                LOG_OBJECT[f'{type}_created'] = False
                msg = f"error creating project {container_name} on {parent.label}"
                LOG_OBJECT['msg'] = msg
                LOG_OBJECT['error'] = True
                return None

        return current_c

    def log_current(self):
        # print(LOG_OBJECT)
        self.reporter.append_log(**LOG_OBJECT)
        reset_log()

    def curate_project(self, project: flywheel.Project):

        global LOG_OBJECT
        parent_group = self.fw_client.get_group('uds')

        columns_to_group = [GLOBAL_SETTINGS['PROJECT_COLUMN']]

        df = load_csv(self.additional_input_one)
        grouped_df = group_by_columns(df, columns_to_group)

        start = time.time()

        for project in grouped_df.groups:
         #   print(project)
            project_label = f"ADC-{project}"
            LOG_OBJECT['csv_project'] = str(project)
        #    print(LOG_OBJECT)
            project_c = self.find_or_create(
                project_label, 'project', parent_group)
            if not project_c:
                self.log_current()
                continue

            subject_df = grouped_df.get_group(project)
            # print(subject_df)
            subject_group = group_by_columns(
                subject_df, GLOBAL_SETTINGS['SUBJECT_COLUMN'])

            for subject in subject_group.groups:

                #    print(subject)
                subject_label = str(subject)
                LOG_OBJECT['csv_project'] = str(project)
                LOG_OBJECT['csv_subject'] = str(subject)
                subject_c = self.find_or_create(
                    subject_label, 'subject', project_c)
                if not subject_c:
                    self.log_current()
                    continue

                session_df = subject_group.get_group(subject)
                handle_subject_meta(subject_c, session_df)
                session_group = group_by_columns(
                    session_df, GLOBAL_SETTINGS['SESSION_COLUMN'])

                for session in session_group.groups:
                    #    print(session)
                    session_label = f"visit-{session}"
                    LOG_OBJECT['csv_project'] = str(project)
                    LOG_OBJECT['csv_subject'] = str(subject)
                    LOG_OBJECT['csv_session'] = str(session)
                    session_c = self.find_or_create(
                        session_label, 'session', subject_c)
                    if not session_c:
                        self.log_current()
                        continue

                    acquisitions = session_group.get_group(session)

                    handle_session_timestamps(session_c, acquisitions)
                    handle_session_meta(session_c, acquisitions)

                    for i, acq in acquisitions.iterrows():
                        acq_label = f"Packet {acq['PACKET']} v{acq[GLOBAL_SETTINGS['ACQUISITION_COLUMN']]}"
                        LOG_OBJECT['csv_acquisition'] = str(acq_label)
                        LOG_OBJECT['csv_project'] = str(project)
                        LOG_OBJECT['csv_subject'] = str(subject)
                        LOG_OBJECT['csv_session'] = str(session)
                        acq_c = self.find_or_create(
                            str(acq_label), 'acquisition', session_c)
                        if not acq_c:
                            self.log_current()
                            continue

                        try:
                            if not acq_c.get_file('form_data.json'):
                                self.fw_client.upload_file_to_container(
                                    acq_c.id, flywheel.FileSpec('form_data.json', acq.to_json()))
                                meta_dict = handle_acq_meta(acq)
                                dict_out = {'investigator': meta_dict}
                                acq_c.update_info(dict_out)
                            self.log_current()
                        except Exception as e:
                            msg = e.__str__()
                            LOG_OBJECT['msg'] = msg
                            LOG_OBJECT['error'] = True
                            self.log_current()

        stop = time.time()

        dur = stop-start
        print(f"It took {dur/60} min to process {len(df)} rows")

    def curate_subject(self, subject: flywheel.Subject):
        pass

    def validate_session(self, session: flywheel.Session):
        pass

    def curate_session(self, session: flywheel.Session):
        pass

    def curate_analysis(self, analysis: flywheel.AnalysisOutput):
        pass

    def curate_file(self, file_: flywheel.FileEntry):
        pass


def load_csv(csv):
    print(f'loading {csv}')
    df = pd.read_csv(csv)
    return df


def group_by_columns(df, columns):

    grouped_df = df.groupby(columns)

    return grouped_df


def find_container(fw_client, label, type, parent=None):

    if not parent:
        parent = fw_client

    finder = getattr(parent, f'{type}s')

    found_containers = finder.find(f'label="{label}"')

    return found_containers


def create_container(parent, conatiner_name, type):

    creator = getattr(parent, f"add_{type}")

    container = creator({'label': conatiner_name})

    return container


def get_timestamp(row):
    month = 'VISITMO'
    day = 'VISITDAY'
    year = 'VISITYR'
    m = row[month]
    d = row[day]
    y = row[year]
    timezone = pytz.utc
    ses_time = datetime.datetime(y, m, d, 0, 0, tzinfo=timezone)
    return ses_time


def set_timestamp(session, session_time):
    session.update({'timestamp': session_time})


def handle_session_timestamps(session, acquisitions):
    session = session.reload()
    if session.timestamp:
        return

    example_acq = acquisitions.iloc[0]
    ses_time = get_timestamp(example_acq)
    set_timestamp(session, ses_time)

    return


def testytest():
    import pandas as pd
    csv = "/Users/davidparker/Documents/Flywheel/Clients/NACC/HierarchyCurator/CreateContainers/investigator_nacc57_abridged.csv"
    csv = "/Users/davidparker/Documents/Flywheel/Clients/NACC/HierarchyCurator/CreateContainers/investigator_nacc57_abridged_FullCol.csv"
    df = pd.read_csv(csv)

    col_names = ['NACCADC', 'NACCID']
    gb = df.groupby(col_names)
    gb.get_group()


def handle_subject_meta(subject, df):

    row = df.iloc[0]
    subject_coded_meta = {'SEX': {1: 'male', 2: 'female'},
                          'RACE': {3: 'American Indian or Alaska Native',
                                   5: 'Asian',
                                   4: 'Native Hawaiian or Other Pacific Islander',
                                   2: 'Black or African American',
                                   1: 'White',
                                   50: 'More Than One Race',
                                   99: 'Unknown or Not Reported',
                                   -4: 'Unknown or Not Reported'},
                          }

    sex_val = row['SEX']
    sex_val = subject_coded_meta['SEX'][sex_val]
    race_val = row['RACE']
    race_val = subject_coded_meta['RACE'][race_val]

    subject.update({'sex': sex_val, 'race': race_val})
    import_to_info = ['BIRTHMO', 'BIRTHYR', 'SEX', 'RACE', 'HISPANIC', 'HISPOR', 'HISPORX', 'RACEX', 'RACESEC', 'RACESECX',
                      'RACETER', 'RACETERX', 'PRIMLANG', 'PRIMLANX', 'EDUC', 'MARISTAT', 'NACCLIVS', 'INDEPEND', 'RESIDENC', 'HANDED']
    info_update = {a: row[a] for a in import_to_info}
    info_update = cleanse_numpy(info_update)

    subject.update_info({'NACC_info': info_update})
    return


def handle_session_meta(session, df):
    row = df.iloc[0]

    ses_month = 'VISITMO'
    ses_day = 'VISITDAY'
    ses_year = 'VISITYR'
    birth_month = 'BIRTHMO'
    birth_year = 'BIRTHYR'
    sm = int(row[ses_month])
    sd = int(row[ses_day])
    sy = int(row[ses_year])
    bm = int(row[birth_month])
    by = int(row[birth_year])

    visit_day = datetime.date(sy, sm, sd)
    birth_day = datetime.date(by, bm, 15)
    age_at_visit = visit_day - birth_day
    age_sec = int(age_at_visit.total_seconds())

    weight = row['WEIGHT']
    if not np.isnan(weight):
        weight = int(weight*0.453592)
    else:
        weight = None

    session.update({'age': age_sec, 'weight': weight})  # convert lb to kg

    import_to_info = ['HEIGHT', 'WEIGHT', 'BPSYS', 'BPDIAS', 'HRATE',
                      'VISION', 'VISCORR', 'VISWCORR', 'HEARING', 'HEARAID', 'HEARWAID']
    info_update = {a: row[a] for a in import_to_info}
    info_update = cleanse_numpy(info_update)
    session.update_info({'NACC_info': info_update})
    return


def handle_acq_meta(row):
    drug_array = [row.pop(k) for k in row.keys() if k.startswith('DRUG')]
    row['DRUGS'] = drug_array
    return row.to_dict()

    pass


def cleanse_numpy(update):

    for k, v in update.items():
        if isinstance(v, collections.abc.Mapping):
            update[k] = cleanse_numpy(update.get(k, {}))
        else:
            # Flywheel doesn't like numpy data types:
            if type(v).__module__ == np.__name__:
                v = v.item()
                update[k] = v
    return update
