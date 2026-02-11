import copy
import importlib.metadata
import logging
import typing as typing
from typing import Any, Dict, List, MutableMapping, Optional

from curator.curator import Curator, ProjectCurationError
from curator.scheduling_models import FileModel
from flywheel import DataView
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
        dataview: DataView,
        curation_tag: str,
        force_curate: bool = False,
        rxclass_concepts: Optional[MutableMapping] = None,
        ignore_qc: bool = False,
    ) -> None:
        super().__init__(
            dataview=dataview, curation_tag=curation_tag, force_curate=force_curate
        )
        version = importlib.metadata.version("nacc_attribute_deriver")
        log.info(f"Running nacc-attribute-deriver version {version}")

        self.__attribute_deriver = AttributeDeriver()
        self.__file_missingness = MissingnessDeriver("file")
        self.__subject_missingness = MissingnessDeriver("subject")
        self.__ignore_qc = ignore_qc

        # prev record needed to pull across values for missingness checks
        self.__prev_record = None
        self.__prev_scope = None

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
            # current (ingest-form) or BDS
            if "file.info.qc.form-qc-checker.validation.state" in table:
                return (
                    table.get("file.info.qc.form-qc-checker.validation.state") == "PASS"
                )

            # BDS uses form-qc-checker for both current and legacy, so if
            # it didn't pass that it should fail
            if scope == FormScope.BDS:
                return False

            # legacy (retrospective-form)
            return table.get("file.info.qc.file-validator.validation.state") == "PASS"

        if scope in list(GeneticsScope):
            return (
                table.get("file.info.qc.form-importer.metadata-extraction.state")
                == "PASS"
            )

        # rest pass by default
        return True

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

    def prepare_table(
        self,
        file_model: FileModel,
        table: SymbolTable,
        scope: ScopeLiterals,
    ) -> None:
        """Prepare the table with working metadata for curation work.

        Anything at the root level starting with a _ generally indicates
        something that is NOT pushed back to flywheel, and is just a
        means to store intermediate information necessary for curation
        work.
        """
        # for derived work, also provide filename (namely needed for MP).
        self.__set_working_metadata(table, "_filename", file_model.filename)

        # if the file belongs to the same session as an UDS visit, add the UDS visitdate
        # (mainly needed for MEDS)
        if file_model.uds_visitdate:
            self.__set_working_metadata(
                table, "_uds_visitdate", str(file_model.uds_visitdate)
            )

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
        file_model: FileModel,
        table: SymbolTable,
        scope: ScopeLiterals,
    ) -> bool:
        """Perform contents of curation. Keeps track of files that failed to be
        curated.

        Args:
            subject: Subject the file belongs to
            file_model: FileModel of file being curated
            table: SymbolTable containing file/subject metadata.
            scope: The scope of the file being curated
        """
        filename = file_model.filename
        # due to issues with soft copy we should double
        # check this file actually passed QC
        if not self.__ignore_qc and not self.check_qc(table, scope):
            log.error(f"File {filename} did not pass QC; skipping")
            self.handle_curation_failure(file_model, "failed_qc")
            return False

        try:
            self.prepare_table(file_model, table, scope)
            self.__attribute_deriver.curate(table, scope)
            self.__file_missingness.curate(table, scope)
        except (AttributeDeriverError, MissingRequiredError, ProjectCurationError) as e:
            log.error(f"Failed to curate {filename}: {e}")
            self.handle_curation_failure(file_model, str(e))
            return False

        # keep track of the last succesful curation
        self.__prev_scope = scope
        self.__prev_record = table["file.info"]

        # file/subject metadata will be pushed to FW in post-processing
        return True

    @api_retry
    def pre_curate(
        self,
        subject: Subject,
        subject_table: SymbolTable,
        curation_list: List[FileModel],
    ) -> None:
        """Run pre-curating on the entire subject. Clean up metadata as needed,
        and pre-compute UDS DOB.

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

        # this is super hacky, but fastest solution for pre-computing UDS DOB
        # so it is consistent for curation
        target_fields = {"birthmo": None, "birthyr": None}
        for file in curation_list:
            if file.scope != FormScope.UDS:
                continue

            file_info = SymbolTable(file.file_info)
            for field in target_fields:
                value = file_info.get(f"forms.json.{field}")
                if value is not None:
                    target_fields[field] = value

        for k, v in target_fields.items():
            if v is not None:
                subject_table[f"working.cross-sectional.{k}"] = v

    @api_retry
    def post_curate(
        self,
        subject: Subject,
        subject_table: SymbolTable,
        processed_files: List[FileModel],
    ) -> None:
        """Run post-curating on the entire subject.

        1. Run cross-module scope derived curations
        2. Run subject-level missingness curations across all scopes
        3. Pushes final subject_table back to FW
        4. Tags affiliates and UDS participants
        5. Run a second pass over forms that require back-prop and apply
            cross-sectional values.
        6. Push curated results to FW
        Args:
            subject: Subject to post-process
            subject_table: SymbolTable containing subject-specific metadata
                and curation results
            processed_files: List of FileModels that were successfully processed
        """
        if not processed_files:
            return

        # hash the processed files by scope
        scoped_files: Dict[ScopeLiterals, List[FileModel]] = {}
        for file in processed_files:
            scope = file.scope
            if not scope:  # sanity check
                raise ProjectCurationError(f"Unknown scope to post-curate: {scope}")
            if scope not in scoped_files:
                scoped_files[scope] = []

            scoped_files[scope].append(file)

        curated_scopes = list(scoped_files.keys())

        # 1/2: subject-level curations - return if this fails
        if not self.subject_level_curation(subject, subject_table, curated_scopes):
            log.debug(
                f"Failed subject level curation for {subject.label}, "
                + "will not apply curation"
            )
            return

        # 3. push subject metadata; need to replace due to potentially
        # cleaned-up metadata and subject-level missingness
        if subject_table:
            subject.replace_info(subject_table.to_dict())  # type: ignore

        derived = subject_table.get("derived", {})

        # 4. add subject tags
        affiliate = derived.get("affiliate", False)
        self.handle_subject_tags(subject, curated_scopes, affiliate)

        # 5. backprop as needed (currently only derived, may need to handle resolved)
        self.back_propagate_scopes(
            subject,
            scoped_files,
            "derived",
            self.__scoped_variables,
            derived.get("cross-sectional", None),
        )

        # 6. push curation to FW
        for file in processed_files:
            self.apply_file_curation(file, affiliate)

    def subject_level_curation(
        self,
        subject: Subject,
        subject_table: SymbolTable,
        curated_scopes: List[ScopeLiterals],
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
            log.error(
                "Failed to apply cross-module curation to "
                + f"{subject.label} on scope {FormScope.CROSS_MODULE.value}: {e}"
            )

            self.handle_curation_failure(subject, str(e))
            return False

        # 2. run subject-level missingness curation
        for scope in typing.get_args(ScopeLiterals):
            # means it was curated at some point, so no need to handle
            if scope in curated_scopes:
                continue

            try:
                log.debug(
                    f"Applying subject-level missingness to {subject.label} "
                    + f"for scope {scope.value}"
                )
                self.__subject_missingness.curate(table, scope.value)
            except (AttributeDeriverError, MissingRequiredError) as e:
                log.error(
                    "Failed to apply subject-level missingness to "
                    + f"{subject.label} on scope {scope.value}: {e}"
                )
                self.handle_curation_failure(subject, str(e))
                return False

        return True

    @api_retry
    def handle_subject_tags(
        self,
        subject: Subject,
        curated_scopes: List[ScopeLiterals],
        affiliate: bool,
    ) -> None:
        """Handle curation tags.

        Args:
            subject: Subject to potentially tag
            processed_files: processed files to potentially tag
            affiliate: whether or not this is an affiliate subject
        """
        affiliate_tag = FormCurationTags.AFFILIATE
        if affiliate and affiliate_tag not in subject.tags:
            log.debug(f"Tagging affiliate: {subject.label}")
            subject.add_tag(affiliate_tag)
        elif not affiliate and affiliate_tag in subject.tags:
            subject.delete_tag(affiliate_tag)

        # add uds-participant tag
        # once a UDS participant always a participant so don't
        # really need to delete tags
        uds_tag = FormCurationTags.UDS_PARTICIPANT
        if FormScope.UDS in curated_scopes and uds_tag not in subject.tags:
            log.debug(f"Tagging UDS participant: {subject.label}")
            subject.add_tag(uds_tag)

    def back_propagate_scopes(  # noqa: C901
        self,
        subject: Subject,
        scoped_files: Dict[ScopeLiterals, List[FileModel]],
        category: str,
        scope_reference: Dict[str, List[str]],
        cs_variables: Dict[str, Any] | None,
    ) -> None:
        """Performs back-propagation on cross-sectional variables.

        These are "finalized" only after curation over the entire
        subject has completed and need to be applied back to each
        corresponding file's file.info

        Args:
            subject: The subject
            scoped_files: The curated files, scoped
            category: The variable category (derived vs resolved)
            scope_reference: The scope reference, i.e. which variables
                belong to which scope. Determines which files actually
                get the back-propagated variables.
            cs_variables: The cross-sectional variables, if any
        """
        if not cs_variables:
            log.debug(
                f"No {category} cross-sectional variables to "
                + f"back-propogate for {subject.label}"
            )
            return

        result: Dict[str, Dict[str, Any]] = {scope: {} for scope in scope_reference}

        for k, v in cs_variables.items():
            for scope, scoped_vars in scope_reference.items():
                if k in scoped_vars:
                    result[scope][k] = v

        # remove scope if there is nothing in it
        result = {k: v for k, v in result.items() if v}

        if not result:
            log.debug(
                f"No applicable {category} cross-sectional variables to "
                + f"back-propogate for {subject.label}"
            )
            return

        log.debug(
            f"Back-propagating {category} cross-sectional variables "
            + f"for {subject.label}"
        )
        for scope, processed_files in scoped_files.items():
            # ignore non-scopes of interest
            if scope not in result:
                continue

            for file in processed_files:
                # update cross-sectional derived variables to file
                file_info = file.file_info
                if not file_info:
                    raise ProjectCurationError(
                        f"Cannot back-propogate {category} variables for "
                        + f"scope {scope}; processed file {file.filename} "
                        + "missing file_info"
                    )

                if category not in file_info:
                    file_info[category] = {}

                file_info[category].update(result[scope])

    @api_retry
    def apply_file_curation(self, file: FileModel, affiliate: bool) -> None:
        """Applies the file-specific curated information back to FW.

        Grabs file.info.derived (derived variables) and
        file.info.resolved (resolved raw + missingness data) and pushes
        back to flywheel.
        """
        log.debug(f"Applying file curation to {file.filename}")
        if not file.file_info:
            raise ProjectCurationError(
                "Cannot apply file curation to FW; processed file missing file_info"
            )

        file_entry = self.sdk_client.get_file(file.file_id)

        # collect metadata into a single API call
        updated_info = {}
        for curation_type in ["derived", "resolved"]:
            curated_file_info = file.file_info.get(curation_type)
            if curated_file_info:
                updated_info.update({curation_type: curated_file_info})

        if updated_info:
            file_entry.update_info(updated_info)

        # add curation tag
        if self.curation_tag not in file_entry.tags:
            file_entry.add_tag(self.curation_tag)

        # set affiliate status
        affiliate_tag = FormCurationTags.AFFILIATE
        if affiliate and affiliate_tag not in file_entry.tags:
            file_entry.add_tag(affiliate_tag)
        elif not affiliate and affiliate_tag in file_entry.tags:
            file_entry.delete_tag(affiliate_tag)
