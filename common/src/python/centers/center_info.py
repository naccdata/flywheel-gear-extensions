"""Models representing center information and center mappings."""
from typing import Dict, List, Optional, Set, Tuple

from projects.study import StudyVisitor
from pydantic import AliasChoices, BaseModel, Field, field_validator


class CenterInfo(BaseModel):
    """Represents a center with data managed at NACC.

    Attributes:
        adcid (int): The ADC ID of the center.
        name (str): The name of the center.
        group (str): The symbolic ID for the center

        active (bool): Optional, active or inactive status. Defaults to True.
        tags (Tuple[str]): Optional, list of tags for the center
    """
    adcid: int
    name: str
    group: str = Field(
        validation_alias=AliasChoices('center_id', 'center-id', 'group'))
    active: Optional[bool] = Field(validation_alias=AliasChoices(
        'active', 'is-active', 'is_active'),
                                   default=True)
    tags: Optional[Tuple[str, ...]] = ()

    def __repr__(self) -> str:
        return (f"Center(group={self.group}, "
                f"name={self.name}, "
                f"adcid={self.adcid}, "
                f"active={self.active}, "
                f"tags={self.tags}")

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, CenterInfo):
            return False
        # compare everything except tags
        return (self.adcid == __o.adcid and self.group == __o.group
                and self.name == __o.name and self.active == __o.active)

    @field_validator("tags")
    def set_tags(cls, tags: Tuple[Tuple[str], List[str]]) -> Tuple[str]:
        if not tags:
            return ()
        return tuple(tags)  # type: ignore

    def apply(self, visitor: StudyVisitor):
        """Applies visitor to this Center."""
        visitor.visit_center(self.group)


class CenterMapInfo(BaseModel):
    """Represents the center map in nacc/metadata project."""
    centers: Dict[str, CenterInfo]

    def add(self, adcid: int, center_info: CenterInfo) -> None:
        """Adds the center info to the map.

        Args:
            adcid: The ADC ID of the center.
            center_info: The center info object.
        """
        self.centers[str(adcid)] = center_info

    def get(self, adcid: int) -> Optional[CenterInfo]:
        """Gets the center info for the given ADCID.

        Args:
            adcid: The ADC ID of the center.
        Returns:
            The center info for the center. None if no info is found.
        """
        return self.centers.get(str(adcid), None)

    def group_ids(self, center_ids: Optional[List[int]] = None) -> Set[str]:
        """Returns the set of group IDs for the centers in this center map.

        If center_ids is provided, restricts the result to those with a center
        ID in the list.

        Args:
          center_ids: the list of center IDs
        Returns:
          the set of group IDs
        """
        if center_ids:
            keys = [str(adcid) for adcid in self.centers]
        else:
            keys = list(self.centers.keys())

        return {
            center.group  # type: ignore
            for center in
            [self.centers.get(key) for key in keys if key in self.centers]
        }

    def active_group_ids(self,
                         center_ids: Optional[List[int]] = None) -> Set[str]:
        """Returns the set of group IDs for active centers in this center map.

        If center_ids is provided, restricts the result to those with an ID in
        the list.

        Args:
          center_ids: the list of center IDs
        Returns:
          the set of group IDs
        """
        if center_ids:
            keys = [str(adcid) for adcid in self.centers]
        else:
            keys = list(self.centers.keys())

        return {
            center.group  # type: ignore
            for center in
            [self.centers.get(key) for key in keys if key in self.centers]
            if center.active  # type: ignore
        }
