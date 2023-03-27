"""Classes for representing NACC projects."""
import re
from abc import ABC, abstractmethod
from typing import Any, Iterable, List, Mapping, Optional


def convert_to_slug(name: str) -> str:
    """Converts center name to a slug for use as a human-readable ID.

    Removes non-word, non-whitespace characters, replaces runs of
    whitespace with a single hyphen, and returns in lower case.

    Args:
      name: the name of the center

    Returns:
      The transformed name.
    """
    name = re.sub(r"[/]", ' ', name)
    name = re.sub(r"[^\w\s]", '', name)
    name = re.sub(r"\s+", '-', name)
    return name.lower()


class ProjectVisitor(ABC):
    """Abstract class for a visitor object for projects."""

    @abstractmethod
    def visit_project(self, project: "Project") -> None:
        """Method to visit the given project.

        Args:
          project: the project to visit.
        """

    @abstractmethod
    def visit_center(self, center: "Center") -> None:
        """Method to visit the given center within a project.

        Args:
          center: the center to visit
        """

    @abstractmethod
    def visit_datatype(self, datatype: str):
        """Method to visit the given datatype within a project.

        Args:
          datatype: the name of the datatype within a project.
        """


class Center:
    """Represents a center with data managed at NACC."""

    def __init__(self,
                 *,
                 name: str,
                 center_id: str,
                 active: bool = True,
                 tags: Optional[List[str]] = None) -> None:
        self.__name = name
        self.__active = active
        self.__center_id = center_id
        if tags is None:
            tags = []
        self.__tags = tags

    def __repr__(self) -> str:
        return (f"Center(center_id={self.center_id}, "
                f"name={self.name}, "
                f"active={self.is_active()}, "
                f"tags={self.tags}")

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, Center):
            return False
        return (self.__center_id == __o.center_id
                and self.__active == __o.is_active() and self.name == __o.name)

    @property
    def name(self) -> str:
        """Center name property."""
        return self.__name

    def is_active(self) -> bool:
        """Indicates whether the center is active."""
        return self.__active

    @property
    def center_id(self):
        """Center text ID property."""
        return self.__center_id

    @property
    def tags(self) -> Iterable[str]:
        """Center tags property."""
        return tuple(self.__tags)

    def apply(self, visitor):
        """Applies visitor to this Center."""
        visitor.visit_center(self)

    @classmethod
    def create(cls, center: dict) -> "Center":
        """Creates a Center from the given dictionary."""
        return Center(name=center['name'],
                      center_id=center['center-id'],
                      active=center['is-active'],
                      tags=center['tags'])


class Project:
    """Represents a Project with data managed at NACC."""

    def __init__(self,
                 *,
                 name: str,
                 project_id: str,
                 centers: List[Center],
                 datatypes: List[str],
                 published: bool = False,
                 primary: bool = False) -> None:
        self.__name = name
        self.__centers = centers
        self.__datatypes = datatypes
        self.__published = published
        self.__primary = primary
        self.__project_id = project_id

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, Project):
            return False
        return (__o.name == self.__name and __o.centers == self.centers
                and __o.datatypes == self.datatypes
                and __o.is_published() == self.is_published()
                and __o.is_primary() == self.is_primary())

    def __repr__(self) -> str:
        return ("Project("
                f"name={self.__name},"
                f"project_id={self.__project_id},"
                f"centers={self.__centers},"
                f"datatypes={self.__datatypes},"
                f"published={self.__published},"
                f"primary={self.__primary}"
                ")")

    @property
    def project_id(self) -> str:
        """Project ID property."""
        return self.__project_id

    @property
    def name(self) -> str:
        """Project Name property."""
        return self.__name

    @property
    def centers(self) -> List[Center]:
        """Project centers property."""
        return self.__centers

    @property
    def datatypes(self) -> List[str]:
        """Project datatypes property."""
        return self.__datatypes

    def is_published(self) -> bool:
        """Project published predicate."""
        return self.__published

    def is_primary(self) -> bool:
        """Predicate to indicate whether is the main project of coordinating
        center."""
        return self.__primary

    def apply(self, visitor) -> None:
        """Apply visitor to this Project."""
        visitor.visit_project(self)

    @classmethod
    def create(cls, project: Mapping[str, Any]) -> "Project":
        """Create Project from given mapping."""
        primary_project = False
        if 'primary' in project:
            primary_project = project['primary']

        return Project(
            name=project['project'],
            project_id=project['project-id'],
            centers=[Center.create(center) for center in project['centers']],
            datatypes=project['datatypes'],
            published=project['published'],
            primary=primary_project)
