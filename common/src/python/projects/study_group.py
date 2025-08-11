from typing import Optional

from flywheel.models.group import Group
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, GroupAdaptor, ProjectAdaptor

from projects.study import StudyModel


class StudyGroup(GroupAdaptor):
    """Defines a group adaptor to represent a study in Flywheel."""

    def __init__(
        self, *, group: Group, proxy: FlywheelProxy, study: StudyModel
    ) -> None:
        super().__init__(group=group, proxy=proxy)
        self.__study = study

    @classmethod
    def create(cls, study: StudyModel, proxy: FlywheelProxy) -> "StudyGroup":
        """Creates a study group for the study object.

        Args:
          study: the study object
          proxy: the FlywheelProxy object
        Returns:
          the study group for the study
        """
        return StudyGroup(
            group=proxy.get_group(group_label=study.name, group_id=study.study_id),
            proxy=proxy,
            study=study,
        )

    def add_project(self, label: str) -> Optional[ProjectAdaptor]:
        """Adds a project with the label to this study group.

        Args:
          label: the project label
        Returns:
          the created project
        """
        return self.get_project(
            label=label, info_update={"study-id": self.__study.study_id}
        )


class StudyError(Exception):
    """Exception for study group operations."""
