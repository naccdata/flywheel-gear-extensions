"""Main function for running template push process."""
import logging
from typing import Optional

from flywheel_gear_toolkit import GearToolkitContext
from fw_client import FWClient
from gear_execution.gear_execution import (
    ClientWrapper,
    ContextClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.context_parser import get_api_key
from inputs.parameter_store import ParameterStore

from projects.template_project import TemplateProject
from template_app.main import run

log = logging.getLogger(__name__)


class TemplatingVisitor(GearExecutionEnvironment):
    """Visitor for the templating gear."""

    # pylint: disable=(too-many-arguments)
    def __init__(self, admin_id: str, client: ClientWrapper,
                 template_group: str, template_label: str, new_only: bool):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__new_only = new_only
        self.__template_group = template_group
        self.__template_label = template_label

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'TemplatingVisitor':
        """Creates a templating execution visitor.

        Args:
            context: The gear context.
        Returns:
          the templating visitor
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = ContextClient.create(context=context)

        # Need fw-client because the SDK doesn't properly implement
        # ViewerApp type used for copying viewer apps from template projects.
        api_key = get_api_key(context)
        client.set_fw_client(
            FWClient(api_key=api_key, client_name="push-template"))
        group_id = context.config.get("template_group")
        if not group_id:
            raise GearExecutionError("Expected \"template_group\"")
        template_label = context.config.get("template_project")
        if not template_label:
            raise GearExecutionError("Expected \"template_label\"")

        return TemplatingVisitor(
            admin_id=context.config.get("admin_group", "nacc"),
            client=client,
            template_group=group_id,
            template_label=template_label,
            new_only=context.config.get("new_only", False))

    def run(self, context: GearToolkitContext) -> None:

        projects = self.proxy.find_projects(
            group_id=self.__template_group,
            project_label=self.__template_label)
        if not projects:
            raise GearExecutionError(
                "Template project "
                f"{self.__template_group}/{self.__template_label}"
                " does not exist")

        run(admin_group=self.admin_group(admin_id=self.__admin_id),
            new_only=self.__new_only,
            template=TemplateProject(project=projects[0], proxy=self.proxy))


def main():
    """Main method to run template copy gear."""

    GearEngine().run(gear_type=TemplatingVisitor)


if __name__ == "__main__":
    main()
