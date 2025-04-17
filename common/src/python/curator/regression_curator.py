"""
Regression curator. Similar to the form curator,
but runs a regression test against the files instead
of curating them. Assumes files have already been curated.
"""
from typing import Any, Dict
from nacc_attribute_deriver.attribute_deriver import ScopeLiterals
from nacc_attribute_deriver.symbol_table import SymbolTable

from .curator import Curator, determine_scope


class RegressionCurator(Curator):
    """Runs regression testing against curation."""

    def __init__(self, sdk_client: Client, baseline: Dict[str, Any]) -> None:
        super().__init__(sdk_client)
        self.__baseline = SymbolTable(baseline)

    def curate_file(self,
                    subject: Subject,
                    file_id: str,
                    max_retries: int = 3) -> None:
        """Runs regression testing on the given file.

        Args:
            subject: Subject the file belongs to
            file_id: File ID curate
            retries: Max number of times to retry before giving up
        """
        retries = 0
        while retries <= max_retries:
            try:
                log.info('looking up file %s', file_id)
                file_entry = self.__sdk_client.get_file(file_id)
                table = self.get_table(subject, file_entry)

                scope = determine_scope(file_entry.name)
                if not scope:
                    log.warning("ignoring unexpected file %s", file_entry.name)
                    return

                log.info("curating file %s", file_entry.name)
                self.__deriver.curate(table, scope)
                self.apply_curation(subject, file_entry, table)
                break
            except ApiException as e:
                retries += 1
                if retries <= max_retries:
                    log.warning(
                        f"Encountered API error, retrying {retries}/{max_retries}"
                    )
                else:
                    raise e

                    
