import copy
import importlib.metadata
import logging
import typing as typing
from multiprocessing import Manager
from multiprocessing.managers import DictProxy
from typing import Any, Dict, List, MutableMapping, Optional

from curator.curator import Curator, ProjectCurationError, determine_scope
from curator.scheduling_models import FileModel
from flywheel.models.file_entry import FileEntry
from flywheel.models.subject import Subject
from nacc_attribute_deriver.attribute_deriver import (
    AttributeDeriver,
    MissingnessDeriver,
)
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.constants import (
    ALL_RX_CLASSES,
    COMBINATION_RX_CLASSES,
)
from nacc_attribute_deriver.utils.errors import (
    AttributeDeriverError,
    MissingRequiredError,
)
from nacc_attribute_deriver.utils.scope import (
    FormScope,
    GeneticsScope,
    SCANMRIScope,
    SCANPETScope,
    ScopeLiterals,
)
from rxnav.rxnav_connection import RxClassConnection
from utils.decorators import api_retry

from .curation_keys import (
    BACKPROP_SCOPES,
    CHILD_SCOPES,
    RESOLVED_SCOPES,
    FormCurationTags,
)

log = logging.getLogger(__name__)


class FormCurator(Curator):
    """Curator that uses NACC Attribute Deriver."""

    def __init__(
        self,
        curation_tag: str,
        force_curate: bool = False,
        rxclass_concepts: Optional[MutableMapping] = None,
    ) -> None:
        super().__init__(curation_tag=curation_tag, force_curate=force_curate)
        version = importlib.metadata.version("nacc_attribute_deriver")
        log.info(f"Running nacc-attribute-deriver version {version}")

        self.__attribute_deriver = AttributeDeriver()
        self.__file_missingness = MissingnessDeriver("file")
        self.__subject_missingness = MissingnessDeriver("subject")

        # prev record needed to pull across values for missingness checks
        self.__prev_record = None
        self.__prev_scope = None

        self.__failed_files = Manager().dict()

        # get expected cross-sectional derived variables by scope
        self.__scoped_variables = {
            scope: self.__extract_attributes(scope) for scope in BACKPROP_SCOPES
        }

        # due to the nature of UDS/NP, it also includes additional scopes
        # TODO: this is currently a hack because the ETL process cannot
        # pull multiple sources (e.g. file.info and subject.info), so for
        # now we are stuffing the necessary variables back into the file
        # level
        for scope, child_scopes in CHILD_SCOPES.items():
            if scope not in self.__scoped_variables:
                self.__scoped_variables[scope] = []

            for child_scope in child_scopes:
                self.__scoped_variables[scope].extend(
                    self.__extract_attributes(child_scope)
                )

        if rxclass_concepts is not None:
            log.info("RxClass concepts provided, will not query RxNav")
            self.__rxclass = rxclass_concepts
        else:
            log.info("Querying RxClass concepts...")
            self.__rxclass = RxClassConnection.get_all_rxclass_members(
                ALL_RX_CLASSES, combination_rx_classes=COMBINATION_RX_CLASSES
            )

    def __extract_attributes(self, scope: str) -> List[str]:
        """Extracts the attributes for the given scope.

        Args:
            scope: the scope to extract rules for
        Returns:
            List of attributes (locations)
        """
        curation_rules = self.__attribute_deriver.get_curation_rules(scope)
        if not curation_rules:
            raise ProjectCurationError(
                f"Cannot find any curation rules for scope: {scope}"
            )

        attributes = []
        for rule in curation_rules:
            for assignment in rule.assignments:
                attributes.append(assignment.attribute)

        # in this context we only care about those at
        # subject.info.derived.cross-sectional,
        # so parse out and strip down to the derived variable name
        parent_location = "subject.info.derived.cross-sectional."
        return [
            x.replace(parent_location, "")
            for x in attributes
            if x.startswith(parent_location)
        ]

    @property
    def failed_files(self) -> DictProxy:
        return self.__failed_files

    def get_table(
        self, subject: Subject, subject_table: SymbolTable, file_entry: FileEntry
    ) -> SymbolTable:
        """Returns the SymbolTable with all relevant information for
        curation."""
        table = super().get_table(subject, subject_table, file_entry)

        # before, we were directly updating with file_entry.delete_info
        # however, this seems like it was somewhat unreliable, as FW could
        # silently fail to delete these fields, causing issues when we try to
        # set the resolved metadata below. since we update the table with the
        # new local derivation anyways, it is actually more efficient to just
        # clear the local table's information. that way, we avoid the above
        # issue + remove a lot of delete_info API calls
        if self.force_curate:
            for field in ["derived", "resolved"]:
                table.pop(f"file.info.{field}")

        return table

    def __set_working_metadata(
        self, table: SymbolTable, location: str, data: Any
    ) -> None:
        """Set working metadata at the specified location in the table.

        Args:
            table: SymbolTable to write metadata to
            location: Location in the table to write metadata; throws an error if data
                already exists here
            data: The metadata to write
        """
        if table.get(location) is not None:
            raise ProjectCurationError(f"{location} is already set, cannot override")

        table[location] = data

    def check_qc(self, table: SymbolTable, scope: ScopeLiterals) -> bool:
        """Check that the file actually passed QC.

        Args:
            table: Table with the file.info data - can also access QC
                metadata this way
            scope: the scope
        """
        imaging_scopes = list(SCANMRIScope) + list(SCANPETScope)
        if scope in imaging_scopes:
            return (
                table.get("file.info.qc.nacc-file-validator.validation.state") == "PASS"
            )

        if scope in list(FormScope):
            # V4 (ingest-form)
            if "file.info.qc.form-qc-checker.validation.state" in table:
                return (
                    table.get("file.info.qc.form-qc-checker.validation.state") == "PASS"
                )

            # legacy (retrospective-form)
            return table.get("file.info.qc.file-validator.validation.state") == "PASS"

        if scope in list(GeneticsScope):
            return (
                table.get("file.info.qc.form-importer.metadata-extraction.state")
                == "PASS"
            )

        # rest pass by default
        return True

    def prepare_table(
        self, file_entry: FileEntry, table: SymbolTable, scope: ScopeLiterals
    ) -> None:
        """Prepare the table with working metadata for curation work.

        Anything at the root level starting with a _ generally indicates
        something that is NOT pushed back to flywheel, and is just a
        means to store intermediate information necessary for curation
        work.
        """
        # for derived work, also provide filename (namely needed for MP).
        self.__set_working_metadata(table, "_filename", file_entry.name)

        # For UDS A4 derived work, store the RxClass information under _rxclass
        if scope == FormScope.UDS and self.__rxclass:
            self.__set_working_metadata(table, "_rxclass", self.__rxclass)

        # for missingness work (and some derived work), also provided information about
        # the previous record if it was in the same scope. again not pushed to FW
        if self.__prev_scope == scope and self.__prev_record:
            self.__set_working_metadata(table, "_prev_record.info", self.__prev_record)

        # to resolve raw and missingness values, we create a copy of
        # file.info.forms.json at file.info.resolved. this information IS
        # pushed back to flywheel depending on the missing values in
        # file.info.forms.json, the missingness logic may write/overwrite results
        # in file.info.resolved as such, file.info.resolved represents the overlay
        # of raw <- missingness, ensuring we have a resolved location for data model
        # querying without touching the raw data
        if scope in RESOLVED_SCOPES:
            self.__set_working_metadata(
                table,
                "file.info.resolved",
                copy.deepcopy(table["file.info.forms.json"]),
            )

    def execute(
        self,
        subject: Subject,
        file_entry: FileEntry,
        table: SymbolTable,
        scope: ScopeLiterals,
    ) -> None:
        """Perform contents of curation. Keeps track of files that failed to be
        curated.

        Args:
            subject: Subject the file belongs to
            file_entry: FileEntry of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        # due to issues with soft copy we should double
        # check this file actually passed QC
        if not self.check_qc(file_entry, scope):
            log.error(f"File {file_entry.name} did not pass QC; skipping")
            self.__failed_files[file_entry.name] = "failed QC"

        try:
            self.prepare_table(file_entry, table, scope)
            self.__attribute_deriver.curate(table, scope)
            self.__file_missingness.curate(table, scope)
        except (AttributeDeriverError, MissingRequiredError, ProjectCurationError) as e:
            self.__failed_files[file_entry.name] = str(e)
            log.error(f"Failed to curate {file_entry.name}: {e}")
            return

        # keep track of the last succesful curation
        self.__prev_scope = scope
        self.__prev_record = table["file.info"]

        # file/subject metadata will be pushed to FW in post-processing

    @api_retry
    def pre_curate(self, subject: Subject, subject_table: SymbolTable) -> None:
        """Run pre-curating on the entire subject. Clean up metadata as needed.

        Args:
            subject: Subject to pre-process
            subject_table: SymbolTable containing subject-specific metadata
        """
        # if forcing new curation, wipe the subject metadata
        # related to curation.
        if self.force_curate:
            log.debug(
                f"Force curation set to True, cleaning up {subject.label} metadata"
            )
            for field in [
                "cognitive.uds",
                "demographics.uds",
                "derived",
                "imaging",
                "genetics",
                "longitudinal-data.uds",
                "neuropathology",
                "study-parameters.uds",
                "working",
            ]:
                subject_table.pop(field)

    @api_retry
    def post_curate(
        self,
        subject: Subject,
        subject_table: SymbolTable,
        processed_files: Dict[FileModel, Dict[str, Any]],
    ) -> None:
        """Run post-curating on the entire subject.

        1. Run cross-module scope derived curations
        2. Run subject-level missingness curations across all scopes
        3. Pushes final subject_table back to FW
        4. Tags affiliates and UDS participants
        5. Run a second pass over forms that require back-prop and apply
            cross-sectional values.
        Args:
            subject: Subject to post-process
            subject_table: SymbolTable containing subject-specific metadata
                and curation results
            processed_files: Dict of FileModels to file info that were processed
        """
        if not processed_files:
            return

        # hash the processed files by scope
        scoped_files: Dict[ScopeLiterals, Dict[FileModel, Dict[str, Any]]] = {}
        for file, file_info in processed_files.items():
            scope = determine_scope(file.filename)
            if not scope:  # sanity check
                raise ProjectCurationError(f"Unknown scope to post-curate: {scope}")
            if scope not in scoped_files:
                scoped_files[scope] = {}

            scoped_files[scope][file] = file_info

        # 1/2: subject-level curations
        if not self.subject_level_curation(subject, subject_table, scoped_files):
            return

        # 3. push subject metadata; need to replace due to potentially
        # cleaned-up metadata and subject-level missingness
        if subject_table:
            subject.replace_info(subject_table.to_dict())  # type: ignore

        derived = subject_table.get("derived", {})

        # 4. add associated tags
        self.handle_tags(subject, scoped_files, derived.get("affiliate", False))

        # 5. backprop
        self.back_propagate_scopes(
            subject, scoped_files, derived.get("cross-sectional", None)
        )

    def subject_level_curation(
        self,
        subject: Subject,
        subject_table: SymbolTable,
        scoped_files: Dict[ScopeLiterals, Dict[FileModel, Dict[str, Any]]],
    ) -> bool:
        """
        1. Cross-module derived variables need to be done at the end
        and at the subject level since it needs complete data from
        all scopes.

        2. UDS-subjects requires subject-level missingness curations
        across all scopes, to handle files and data that did not
        exist for the subject. Since we couldn't curate missingness
        on a non-existent file earlier, it needs to be done
        explicitly here

        Returns true if curations are successful, false otherwise
        """
        table = SymbolTable()
        table["subject.info"] = subject_table.to_dict()

        # 1. run cross-module subject-level derivations, which require completed
        # curated data from NP, MLST, UDS, and MDS
        try:
            log.debug(f"Running cross-module curation for {subject.label}")
            self.__attribute_deriver.curate(table, FormScope.CROSS_MODULE.value)
        except (AttributeDeriverError, MissingRequiredError) as e:
            self.__failed_files[subject.label] = str(e)
            log.error(
                "Failed to apply cross-module curation to "
                + f"{subject.label} on scope {FormScope.CROSS_MODULE.value}: {e}"
            )
            return False

        # 2. run subject-level missingness curation
        for scope in typing.get_args(ScopeLiterals):
            # means it was curated at some point, so no need to handle
            if scope in scoped_files:
                continue

            try:
                log.debug(
                    f"Applying subject-level missingness to {subject.label} "
                    + f"for scope {scope.value}"
                )
                self.__subject_missingness.curate(table, scope.value)
            except (AttributeDeriverError, MissingRequiredError) as e:
                self.__failed_files[subject.label] = str(e)
                log.error(
                    "Failed to apply subject-level missingness to "
                    + f"{subject.label} on scope {scope.value}: {e}"
                )
                return False

        return True

    @api_retry
    def handle_tags(
        self,
        subject: Subject,
        scoped_files: Dict[ScopeLiterals, Dict[FileModel, Dict[str, Any]]],
        affiliate: bool,
    ) -> None:
        """Handle curation tags.

        Args:
            subject: Subject to potentially tag
            processed_files: processed files to potentially tag
            affiliate: whether or not this is an affiliate subject
        """
        if affiliate:
            affiliate_tag = FormCurationTags.AFFILIATE
            log.debug(f"Tagging affiliate: {subject.label}")

            if affiliate_tag not in subject.tags:
                subject.add_tag(affiliate_tag)

            # not ideal, but need to also tag all files to get around data model
            # luckily the number of affiliates is relatively small, so this shouldn't
            # add too many more API calls
            for _, files in scoped_files.items():
                for file in files:
                    file_entry = self.sdk_client.get_file(file.file_id)
                    if affiliate_tag not in file_entry.tags:
                        file_entry.add_tag(affiliate_tag)

        # add uds-participant tag
        uds_tag = FormCurationTags.UDS_PARTICIPANT
        if FormScope.UDS in scoped_files and uds_tag not in subject.tags:
            log.debug(f"Tagging UDS participant: {subject.label}")
            subject.add_tag(uds_tag)

    @api_retry
    def back_propagate_scopes(
        self,
        subject: Subject,
        scoped_files: Dict[ScopeLiterals, Dict[FileModel, Dict[str, Any]]],
        cs_derived: Dict[str, Any] | None,
    ) -> None:
        """Performs back-propagation on cross-sectional variables.

        These are "finalized" only after curation over the entire
        subject has completed and need to be applied back to each
        corresponding file's file.info.derived.
        """
        if not cs_derived:
            log.debug(
                "No cross-sectional derived variables to "
                f"back-propogate for {subject.label}"
            )
            return

        # filter out to scopes that need to be back-propagated
        scope_derived: Dict[str, Dict[str, Any]] = {
            scope: {} for scope in self.__scoped_variables
        }

        for k, v in cs_derived.items():
            for scope, scoped_vars in self.__scoped_variables.items():
                if k in scoped_vars:
                    scope_derived[scope][k] = v

        log.debug(f"Back-propagating cross-sectional variables for {subject.label}")
        for scope, files in scoped_files.items():
            # ignore non-scopes of interest
            if scope not in self.__scoped_variables:
                continue

            for file, file_info in files.items():
                file_entry = self.sdk_client.get_file(file.file_id)

                # update cross-sectional derived variables to file
                derived = file_info.get("derived", {})
                derived.update(scope_derived[scope])
                file_info["derived"] = derived

                self.apply_file_curation(file_entry, file_info)

    @api_retry
    def apply_file_curation(
        self, file_entry: FileEntry, file_info: Dict[str, Any]
    ) -> None:
        """Applies the file-specific curated information back to FW.

        Grabs file.info.derived (derived variables) and
        file.info.resolved (resolved raw + missingness data) and pushes
        back to flywheel.
        """
        # collect so we only do one API call, not one per curation type
        updated_info = {}
        for curation_type in ["derived", "resolved"]:
            curated_file_info = file_info.get(curation_type)
            if curated_file_info:
                updated_info.update({curation_type: curated_file_info})

        if updated_info:
            file_entry.update_info(updated_info)

        if self.curation_tag not in file_entry.tags:
            file_entry.add_tag(self.curation_tag)
