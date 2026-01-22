"""Models representing center information and center mappings."""

from typing import Dict, Iterator, List, Optional, Set, Tuple, Union

from projects.study import StudyCenterModel, StudyVisitor
from pydantic import AliasChoices, BaseModel, Field, RootModel, field_validator


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
        validation_alias=AliasChoices("center_id", "center-id", "group"),
        serialization_alias="center-id",
    )
    active: Optional[bool] = Field(
        validation_alias=AliasChoices("active", "is-active", "is_active"),
        serialization_alias="is-active",
        default=True,
    )
    tags: Optional[Tuple[str, ...]] = None

    def __repr__(self) -> str:
        return (
            f"Center(group={self.group}, "
            f"name={self.name}, "
            f"adcid={self.adcid}, "
            f"active={self.active}, "
            f"tags={self.tags}"
            ")"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CenterInfo):
            return False
        # compare everything except tags
        return (
            self.adcid == other.adcid
            and self.group == other.group
            and self.name == other.name
            and self.active == other.active
        )

    def apply(self, visitor: StudyVisitor):
        """Applies visitor to this Center."""
        assert self.group is not None
        visitor.visit_center(StudyCenterModel(center_id=self.group))

    @field_validator("tags", mode="before")
    @classmethod
    def set_tags(cls, tags: Union[str, Tuple[str], List[str]]) -> Tuple[str, ...]:
        if isinstance(tags, str):
            return tuple(filter(lambda x: x, tags.split(",")))
        if not tags:
            return ()
        return tuple(tags)


class CenterList(RootModel[List[CenterInfo]]):
    root: List[CenterInfo]

    def __bool__(self) -> bool:
        return bool(self.root)

    def __iter__(self) -> Iterator[CenterInfo]:  # type: ignore
        return iter(self.root)

    def __getitem__(self, item: int) -> CenterInfo:
        return self.root[item]

    def __len__(self):
        return len(self.root)

    def append(self, center: CenterInfo) -> None:
        """Appends the center to the list."""
        self.root.append(center)


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

    def get_adcid(self, group_id: str) -> Optional[int]:
        """Returns the ADCID for the center group.

        Args:
          group_id: the ID for the center group
        Returns:
          the ADCID for the center
        """
        for adcid, center_info in self.centers.items():
            if center_info.group == group_id:
                return int(adcid)
        return None

    def get_adcids(self) -> List[int]:
        """Returns the list of ADCIDs for all centers.

        Returns:
          the list of ADCIDs
        """
        return [int(adcid) for adcid in self.centers]

    def group_ids(self, center_ids: Optional[List[str]] = None) -> Set[str]:
        """Returns the set of group IDs for the centers in this center map.

        If center_ids is provided, restricts the result to those with a center
        ID in the list.

        Args:
          center_ids: the list of center IDs
        Returns:
          the set of group IDs
        """
        if center_ids:
            keys = [adcid for adcid in self.centers if adcid in center_ids]
        else:
            keys = list(self.centers.keys())

        return {
            center.group  # type: ignore
            for center in [self.centers.get(key) for key in keys if key in self.centers]
        }

    def active_group_ids(self, center_ids: Optional[List[str]] = None) -> Set[str]:
        """Returns the set of group IDs for active centers in this center map.

        If center_ids is provided, restricts the result to those with an ID in
        the list.

        Args:
          center_ids: the list of center IDs
        Returns:
          the set of group IDs
        """
        if center_ids:
            keys = [adcid for adcid in self.centers if adcid in center_ids]
        else:
            keys = list(self.centers.keys())

        return {
            center.group  # type: ignore
            for center in [self.centers.get(key) for key in keys if key in self.centers]
            if center.active  # type: ignore
        }
