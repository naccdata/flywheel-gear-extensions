"""Defines common ancestor for groups representing an organization."""

from typing import Optional

from flywheel.models.group import Group
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, GroupAdaptor, ProjectAdaptor


class CenterAdaptor(GroupAdaptor):
    """Defines an adaptor for a group representing an organization."""

    def __init__(self, *, group: Group, proxy: FlywheelProxy) -> None:
        super().__init__(group=group, proxy=proxy)
        self.__metadata: Optional[ProjectAdaptor] = None

    def get_metadata(self) -> ProjectAdaptor:
        """Returns the metadata project.

        Returns:
          the metadata project object
        """
        if not self.__metadata:
            self.__metadata = self.get_project("metadata")
            assert self.__metadata, (
                "Expecting metadata project. " "Check user has permissions."
            )

        return self.__metadata
