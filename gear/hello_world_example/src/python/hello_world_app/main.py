"""Defines Hello World.

This gear/tutorial illustrates how to navigate through and interact with
the Flywheel hierarchy and associated files. It

1. Reads a plain text file as the input. Assumes it has exactly 4 lines
    with the following values:
    a. The label to say hello to and create a subject for
    b. Comma-deliminated list of tags to add to the output file
    c. Data to add under the `dummy_metadata` key in the output file's custom
        information
    d. NO to fail the QC and YES to pass it and attach that result to the
        input file's metadata (if not a local run)
2. Creates a subject with the label provided by the input file and adds
    `created_by` to the subject's custom information
    a. If a subject with that label already exists, finds the subject and instead
        adds `last_updated_by` to the subject's custom information
3. Grabs the project's metadata. Increments both a count and adds the subject
    label to a list
4. Write data to an output file that is then attached to the subject. The data
    being written includes information about the project and subject
5. Update tags and metadata to both the input and output files

Feel free to modify this gear script to explore your own use cases.
"""
import logging
from datetime import datetime
from io import StringIO

from flywheel.file_spec import FileSpec
from flywheel.rest import ApiException

# from common/src/python
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import InputFileWrapper
from utils.utils import parse_string_to_list

log = logging.getLogger(__name__)


def run(proxy: FlywheelProxy,
        context: GearToolkitContext,
        project: ProjectAdaptor,
        input_file: InputFileWrapper,
        output_filename: str,
        local_run: bool = False) -> None:
    """Runs the Hello World process.

    Args:
        proxy: the proxy for the Flywheel instance, for
            interacting with Flywheel
        context: GearToolkitContext, for applying custom
            information updates to the input file
        project: The corresponding project of this file
        input_file: InputFileWrapper to read the input file
            from, pulls the subject to create and metadata
            to add
        output_filename: Name of file to write results to
            and attach to the created subject
        local_run: Whether or not this is a local run, may
            block certain actions that cannot be done while
            iterating on a local file
    """
    # 1. read the name from the first line of the input file
    with open(input_file.filepath, mode='r') as fh:
        label = fh.readline().strip()
        tags = parse_string_to_list(fh.readline())
        metadata = fh.readline().strip()
        pass_qc = fh.readline().strip().upper() == 'YES'

    log.info(f"Read name {label} from input file")
    log.info(f"Read tags {tags} from input file")
    log.info(f"Read metadata {metadata} from input file")

    # 2. add subject with label
    timestamp = datetime.now()
    if proxy.dry_run:
        log.info(f"DRY RUN: Would have created new subject with label {label}")
    else:
        log.info(f"Creating subject with label {label}")

        # add custom information to the subject with information about
        # the file it was created from
        subject_metadata = {
            'name': input_file.filename,
            'filepath': input_file.filepath,
            'owner': input_file.file_input['object']['origin']['id'],
            'file_id': input_file.file_id,
            'timestamp': timestamp
        }
        try:
            subject = project.add_subject(label)
            subject.update({"created_by": subject_metadata})
        except ApiException as error:
            log.warning(error)
            subject = project.find_subject(label)
            subject.update({"last_updated_by": subject_metadata})

    # 3. get project custom information and increment counter by 1
    # and then also add label to array
    log.info("Grabbing project custom information")
    project_info = project.get_info()
    if project_info.get('count', None) is None:
        project_info['count'] = 0

    if project_info.get('entries', None) is None:
        project_info['entries'] = []

    log.info(f"Previous count: {project_info['count']}")
    log.info(f"Previous entries: {project_info['entries']}")

    if proxy.dry_run:
        log.info("DRY RUN: Would have added to project metadata")
    else:
        log.info("Updating project metadata")
        project_info['count'] += 1
        project_info['entries'].append(label)
        project.update_info(project_info)

    # 4. Write output file and attach it to the subject
    stream = StringIO()
    stream.write(f"Hello {label}!\n")
    stream.write(f"You were created or updated at {timestamp}\n")
    stream.write(f"Your ID is {subject.id}\n")
    stream.write(f"This is the URL of the site instance: {proxy.get_site()}\n")
    stream.write("And this is your project's information:\n")
    stream.write(f"Project ID: {project.id}\n")
    stream.write(f"Label: {project.label}\n")
    stream.write(f"Group: {project.group}")
    contents = stream.getvalue()

    if proxy.dry_run:
        log.info("DRY RUN: Would have written the following " +
                 f"to {output_filename}:")
        log.info(contents)
    else:
        log.info(f"Writing output to {output_filename} and " +
                 f"attaching it to subject {subject.label}")
        file_spec = FileSpec(name=output_filename,
                             contents=contents,
                             content_type='text/plain',
                             size=len(contents))

        output_file_entry = subject.upload_file(file_spec)[0]  # type: ignore
        output_file = proxy.get_file(output_file_entry['file_id'])

    # 5. Update tags/metadata
    if proxy.dry_run:
        log.info(f"DRY RUN: Would have added tags: {tags}")
        log.info(f"DRY RUN: Would have added metadata: {metadata}")
    else:
        output_file.add_tags(tags)
        output_file.update_info({'dummy_metadata': metadata})

        if not local_run:
            context.metadata.add_file_tags(input_file.file_input,
                                           tags=['hello-world-processed'])
            context.metadata.add_qc_result(input_file.file_input,
                                           name='hello-world-qc',
                                           state='PASS' if pass_qc else 'NO',
                                           data=[{
                                               'msg':
                                               f'input file said {pass_qc}'
                                           }])
        else:
            log.info(
                "LOCAL RUN: cannot update metadata for input file, as it does "
                + "not belong to a Flywheel container")
