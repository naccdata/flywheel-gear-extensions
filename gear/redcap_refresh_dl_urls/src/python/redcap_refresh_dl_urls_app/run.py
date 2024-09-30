"""Entry script for Refresh REDCap Download URLs."""

import logging

from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (ClientWrapper, ContextClient,
                                           GearEngine,
                                           GearExecutionEnvironment)
from redcap_refresh_dl_urls_app.main import run
from inputs.parameter_store import ParameterStore

log = logging.getLogger(__name__)

class REDCapRefreshDownloadURLs(GearExecutionEnvironment):
    """Visitor for the templating gear."""

    def __init__(self, client: ClientWrapper):
        super().__init__(client=client)

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'REDCapRefreshDownloadURLs':
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = ContextClient.create(context=context)

        return REDCapRefreshDownloadURLs(client=client)

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy)
        
def main():
    """Main method for Refresh REDCap Download URLs."""

    GearEngine().run(gear_type=REDCapRefreshDownloadURLs)

if __name__ == "__main__":
    main()
