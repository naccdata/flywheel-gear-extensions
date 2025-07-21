from flywheel.models.group import Group
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, GroupAdaptor, ProjectAdaptor

from projects.study import StudyModel


class StudyGroup(GroupAdaptor):
    """Defines a group adaptor to represent a study in Flywheel."""

    def __init__(self, *, group: Group, proxy: FlywheelProxy, study: StudyModel) -> None:
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

    def add_project(self, label: str) -> ProjectAdaptor:
        """Adds a project with the label to this study group.

        Args:
          label: the project label
        Returns:
          the created project
        """
        project = self.get_project(label)
        if not project:
            raise StudyError(f"failed to create project {self.label}/{label}")

        project.add_tags(self.get_tags())
        project.add_admin_users(self.get_user_access())
        return project


class StudyError(Exception):
    """Exception for study group operations."""
