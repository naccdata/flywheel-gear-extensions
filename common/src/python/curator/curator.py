"""Defines a base abstract curator for scheduling."""

import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional

from flywheel import Client
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from fw_gear import GearContext
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import ScopeLiterals
from utils.decorators import api_retry

from .scheduling_models import ProcessedFile

log = logging.getLogger(__name__)


class ProjectCurationError(Exception):
    pass


class Curator(ABC):
    """Base curator abstract class."""

    def __init__(
        self, curation_tag: Optional[str] = None, force_curate: bool = False
    ) -> None:
        self.__curation_tag = curation_tag
        self.__force_curate = force_curate
        self.__sdk_client: Client | None = None

    @property
    def sdk_client(self) -> Client:
        if not self.__sdk_client:
            raise ProjectCurationError("SDK Client not set")

        return self.__sdk_client

    @property
    def curation_tag(self) -> Optional[str]:
        return self.__curation_tag

    @property
    def force_curate(self) -> bool:
        return self.__force_curate

    def set_client(self, context: GearContext) -> None:
        """Set the SDK client. For multiprocessing, this client must be
        separate per process, so expected to be set at the worker instantiation
        level.

        Args:
            context: Context to set client from
        """
        self.__sdk_client = context.get_client()

    @api_retry
    def get_subject(self, subject_id: str) -> Subject:
        """Get the subject for the given subject ID.

        Args:
          subject_id: the subject ID
        Returns:
          the corresponding Subject
        """
        return self.sdk_client.get_subject(subject_id)

    @api_retry
    def get_table(
        self, subject: Subject, subject_table: SymbolTable, file_entry: FileEntry
    ) -> SymbolTable:
        """Returns the SymbolTable with all relevant information for curation.

        Args:
            subject: The subject the file belongs to
            subject_table: SymbolTable containing subject-specific metadata
                to curate to. Iteratively added onto for each file curation
            file_entry: The file being curated
        """
        # add the metadata
        table = SymbolTable({})

        # SymbolTable.to_dict() returns the internal dict object; this same object
        # is passed to each file's iteration of this table, so in practice is
        # mutated globally
        table["subject.info"] = subject_table.to_dict()
        table["file.info"] = file_entry.reload().info

        return table

    @api_retry
    def curate_file(
        self, subject: Subject, subject_table: SymbolTable, file_id: str
    ) -> ProcessedFile:
        """Curates a file.

        Args:
            subject: Subject the file belongs to
            subject_table: SymbolTable containing subject-specific metadata
                to curate to. Iteratively added onto for each file curation
            file_id: FW ID of file to curate

        Returns:
            ProcessedFile: the ProcessedFile object; if not succesfully curated,
                file_info will be None
        """
        file_entry = self.sdk_client.get_file(file_id)
        scope = determine_scope(file_entry.name)

        processed_file = ProcessedFile(
            name=file_entry.name,
            file_id=file_id,
            tags=file_entry.tags,
            scope=scope,
        )

        if (
            self.curation_tag
            and not self.force_curate
            and self.curation_tag in file_entry.tags
        ):
            log.debug(f"{file_entry.name} already curated, skipping")
            return processed_file

        if not scope:
            log.warning("could not determine scope for %s, skipping", file_entry.name)
            return processed_file

        table = self.get_table(subject, subject_table, file_entry)
        log.debug("curating file %s with scope %s", file_entry.name, scope)
        if not self.execute(subject, file_entry, table, scope):
            return processed_file

        processed_file.file_info = table.get("file.info", {})
        return processed_file

    def pre_curate(self, subject: Subject, subject_table: SymbolTable) -> None:
        """Run pre-curation on the entire subject. Not required.

        Args:
            subject: Subject to pre-process
            subject_table: SymbolTable containing subject-specific metadata
        """
        return

    def post_curate(
        self,
        subject: Subject,
        subject_table: SymbolTable,
        processed_files: List[ProcessedFile],
    ) -> None:
        """Run post-curation on the entire subject. Not required.

        Args:
            subject: Subject to post-process
            subject_table: SymbolTable containing subject-specific metadata
                and curation results
            processed_files: List of ProcessedFiles that were successfully processed
        """
        return

    @abstractmethod
    def execute(
        self,
        subject: Subject,
        file_entry: FileEntry,
        table: SymbolTable,
        scope: ScopeLiterals,
    ) -> bool:
        """Perform contents of curation.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        return True


SCOPE_PATTERN = re.compile(
    r"^"
    r"(?P<bds>.+_BDS\.json)|"
    r"(?P<cls>.+_CLS\.json)|"
    r"(?P<csf>.+_CSF\.json)|"
    r"(?P<np>.+_NP\.json)|"
    r"(?P<mds>.+_MDS\.json)|"
    r"(?P<milestone>.+_MLST\.json)|"
    r"(?P<covid>.+_COVID\.json)|"
    r"(?P<apoe>.+apoe_genotype\.json)|"
    r"(?P<ncrad_biosamples>.+NCRAD-SAMPLES.+\.json)|"
    r"(?P<niagads_availability>.+niagads_availability\.json)|"
    r"(?P<scan_mri_qc>.+SCAN-MR-QC.+\.json)|"
    r"(?P<scan_mri_sbm>.+SCAN-MR-SBM.+\.json)|"
    r"(?P<scan_pet_qc>.+SCAN-PET-QC.+\.json)|"
    r"(?P<scan_amyloid_pet_gaain>.+SCAN-AMYLOID-PET-GAAIN.+\.json)|"
    r"(?P<scan_amyloid_pet_npdka>.+SCAN-AMYLOID-PET-NPDKA.+\.json)|"
    r"(?P<scan_fdg_pet_npdka>.+SCAN-FDG-PET-NPDKA.+\.json)|"
    r"(?P<scan_tau_pet_npdka>.+SCAN-TAU-PET-NPDKA.+\.json)|"
    r"(?P<mri_summary>.+MRI-SUMMARY-DATA.+\.json)|"
    r"(?P<mri_dicom>.+MR.+\.dicom\.zip)|"
    r"(?P<mri_nifti>.+MR.+\.nii\.gz)|"
    r"(?P<pet_dicom>.+PET.+\.dicom\.zip)|"
    r"(?P<meds>.+_MEDS\.json)|"
    r"(?P<ftld>.+_FTLD\.json)|"
    r"(?P<lbd>.+_LBD\.json)|"
    r"(?P<uds>.+_UDS\.json)"
    r"$"
)


def determine_scope(filename: str) -> Optional[ScopeLiterals]:
    """Maps the file name to a scope symbol for the attribute deriver.

    Args:
        filename: the name of the file
    Returns:
        the scope name matching the file
    """
    # need to handle historic apoe separately as it does not work well with regex
    if "historic_apoe_genotype" in filename:
        return "historic_apoe"

    match = SCOPE_PATTERN.match(filename)
    if not match:
        return None

    groups = match.groupdict()
    names = {key for key in groups if groups.get(key) is not None}
    if len(names) != 1:
        raise ProjectCurationError(f"error matching file name {filename} to scope")

    return names.pop()  # type: ignore
