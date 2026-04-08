import logging
from typing import Optional

from configs.ingest_configs import ModuleConfigs
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from submissions.models import DeleteRequest

log = logging.getLogger(__name__)


class FormDeletionProcessor:
    """Class to handle the form data delete request."""

    def __init__(
        self,
        *,
        project: ProjectAdaptor,
        adcid: int,
        delete_request: DeleteRequest,
        module_configs: ModuleConfigs,
        naccid: Optional[str] = None,
    ):
        """_summary_

        Args:
            project (ProjectAdaptor): _description_
            adcid (int): _description_
            delete_request (DeleteRequest): _description_
            module_configs (ModuleConfigs): _description_
            naccid:
        """
        self.__project = project
        self.__adcid = adcid
        self.__module_configs = module_configs
        self.__delete_request = delete_request
        self.__naccid = naccid

    def process_request(self) -> bool:
        return True
