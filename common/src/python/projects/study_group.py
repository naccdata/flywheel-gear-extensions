from flywheel.models.group import Group
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, GroupAdaptor, ProjectAdaptor

from projects.study import Study


class StudyGroup(GroupAdaptor):
    def __init__(self, *, group: Group, proxy: FlywheelProxy, study: Study) -> None:
        super().__init__(group=group, proxy=proxy)
        self.__study = study

    @classmethod
    def create(cls, study: Study, proxy: FlywheelProxy) -> "StudyGroup":
        return StudyGroup(
            group=proxy.get_group(group_label=study.name, group_id=study.study_id),
            proxy=proxy,
            study=study,
        )

    def add_project(self, label: str) -> ProjectAdaptor:
        project = self.get_project(label)
        if not project:
            raise StudyError(f"failed to create project {self.label}/{label}")

        project.add_tags(self.get_tags())
        project.add_admin_users(self.get_user_access())
        return project


class StudyError(Exception):
    """Exception for study group operations."""
