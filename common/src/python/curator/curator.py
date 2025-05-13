"""Defines a base abstract curator for scheduling."""
import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional

from flywheel import Client
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals
from utils.decorators import api_retry

log = logging.getLogger(__name__)


class Curator(ABC):
    """Base curator abstract class."""

    def __init__(self,
                 sdk_client: Client,
                 curation_tag: Optional[str] = None,
                 force_curate: bool = False) -> None:
        self.__sdk_client = sdk_client
        self.__curation_tag = curation_tag
        self.__force_curate = force_curate

    @property
    def sdk_client(self):
        return self.__sdk_client

    @property
    def curation_tag(self):
        return self.__curation_tag

    @property
    def force_curate(self):
        return self.__force_curate

    def get_subject(self, subject_id: str) -> Subject:
        """Get the subject for the given subject ID.

        Args:
          subject_id: the subject ID
        Returns:
          the corresponding Subject
        """
        return self.sdk_client.get_subject(subject_id)

    def get_table(self, subject: Subject,
                  file_entry: FileEntry) -> SymbolTable:
        """Returns the SymbolTable with all relevant information for curation.

        Args:
            subject: The subject the file belongs to
            file_entry: The file being curated
        """
        # need to reload since info isn't automatically loaded
        subject = subject.reload()
        file_entry = file_entry.reload()

        # add the metadata
        table = SymbolTable({})
        table['subject.info'] = subject.info
        table['file.info'] = file_entry.info
        return table

    @api_retry
    def curate_file(self, subject: Subject, file_id: str) -> None:
        """Curates a file.

        Args:
            subject: Subject the file belongs to
            file_id: File ID curate
        """
        file_entry = self.sdk_client.get_file(file_id)

        if (self.curation_tag and not self.force_curate
                and self.curation_tag in file_entry.tags):
            log.info(f"{file_entry.name} already curated, skipping")
            return

        scope = determine_scope(file_entry.name)
        if not scope:
            log.warning("could not determine scope for %s, skipping",
                        file_entry.name)
            return

        table = self.get_table(subject, file_entry)
        log.info("curating file %s", file_entry.name)
        self.execute(subject, file_entry, table, scope)

    def pre_process(self, subject: Subject) -> None:
        """Run pre-processing on the entire subject. Not required.

        Args:
            subject: Subject to pre-process
        """
        return

    def post_process(self, subject: Subject,
                     processed_files: List[str]) -> None:
        """Run post-processing on the entire subject. Not required.

        Args:
            subject: Subject to pre-process
            processed_files: List of file IDs that were processed
        """
        return

    @abstractmethod
    def execute(self, subject: Subject, file_entry: FileEntry,
                table: SymbolTable, scope: ScopeLiterals) -> None:
        """Perform contents of curation.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        pass


def determine_scope(filename: str) -> Optional[ScopeLiterals]:
    """Maps the file name to a scope symbol for the attribute deriver.

    Args:
        filename: the name of the file
    Returns:
        the scope name matching the file
    """
    # need to handle historic apoe separately as it does not work well with regex
    if 'historic_apoe_genotype' in filename:
        return 'historic_apoe'

    pattern = (r"^"
               r"(?P<np>.+_NP\.json)|"
               r"(?P<mds>.+_MDS\.json)|"
               r"(?P<milestone>.+_MLST\.json)|"
               r"(?P<apoe>.+apoe_genotype\.json)|"
               r"(?P<ncrad_samples>.+NCRAD-SAMPLES.+\.json)|"
               r"(?P<niagads_availability>.+niagads_availability\.json)|"
               r"(?P<scan_mri_qc>.+SCAN-MR-QC.+\.json)|"
               r"(?P<scan_mri_sbm>.+SCAN-MR-SBM.+\.json)|"
               r"(?P<scan_pet_qc>.+SCAN-PET-QC.+\.json)|"
               r"(?P<scan_amyloid_pet_gaain>.+SCAN-AMYLOID-PET-GAAIN.+\.json)|"
               r"(?P<scan_amyloid_pet_npdka>.+SCAN-AMYLOID-PET-NPDKA.+\.json)|"
               r"(?P<scan_fdg_pet_npdka>.+SCAN-FDG-PET-NPDKA.+\.json)|"
               r"(?P<scan_tau_pet_npdka>.+SCAN-TAU-PET-NPDKA.+\.json)|"
               r"(?P<uds>.+_UDS\.json)"
               r"$")
    match = re.match(pattern, filename)
    if not match:
        return None

    groups = match.groupdict()
    names = {key for key in groups if groups.get(key) is not None}
    if len(names) != 1:
        raise ValueError(f"error matching file name {filename}")

    return names.pop()  # type: ignore
