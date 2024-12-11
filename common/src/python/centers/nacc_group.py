"""Singleton class representing NACC with a FW group."""
import logging
from typing import List, Optional

from flywheel.models.group import Group
from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from pydantic import ValidationError
from redcap.redcap_repository import REDCapParametersRepository

from centers.center_adaptor import CenterAdaptor
from centers.center_group import CenterGroup
from centers.center_info import CenterInfo, CenterMapInfo

log = logging.getLogger(__name__)


class NACCGroup(CenterAdaptor):
    """Manages group for NACC."""

    def __init__(self, *, group: Group, proxy: FlywheelProxy) -> None:
        super().__init__(group=group, proxy=proxy)
        self.__admin_project: Optional[ProjectAdaptor] = None
        self.__redcap_param_repo: Optional[REDCapParametersRepository] = None

    @classmethod
    def create(cls,
               *,
               proxy: FlywheelProxy,
               group_id: str = 'nacc') -> 'NACCGroup':
        """Creates a NACCGroup object for the group on the flywheel instance.

        Args:
          proxy: the flywheel instance proxy object
          group_id: the label for NACC group (optional)
        Returns:
          the NACCGroup object
        """
        group = proxy.get_group(group_label="NACC", group_id=group_id)
        admin_group = NACCGroup(group=group, proxy=proxy)
        metadata_project = admin_group.get_metadata()
        metadata_project.add_admin_users(admin_group.get_user_access())

        return admin_group

    @property
    def redcap_param_repo(self) -> Optional[REDCapParametersRepository]:
        return self.__redcap_param_repo

    def set_redcap_param_repo(self,
                              redcap_param_repo: REDCapParametersRepository):
        self.__redcap_param_repo = redcap_param_repo

    def add_center(self, center_group: CenterGroup) -> None:
        """Adds the metadata for the center.

        Args:
          center_group: the CenterGroup object for the center
        """
        self.add_adcid(adcid=center_group.adcid,
                       group_label=center_group.label,
                       group_id=center_group.id,
                       active=center_group.is_active())

    def add_adcid(self, adcid: int, group_label: str, group_id: str,
                  active: bool) -> None:
        """Adds the adcid-group correspondence.

        Args:
          adcid: the ADC ID
          group_label: the label for the center group
          group_id: the ID for the center group
          active: active or inactive status for the center.
        """
        metadata = self.get_metadata()
        center_map = self.get_center_map()
        center_map.add(
            adcid,
            CenterInfo(adcid=adcid,
                       name=group_label,
                       group=group_id,
                       active=active))
        exclude = {'centers': {'__all__': {'tags'}}}
        metadata.update_info(center_map.model_dump(exclude=exclude))

    def get_center_map(self,
                       center_filter: Optional[List[str]] = None) -> CenterMapInfo:
        """Returns the adcid-group map.

        Args:
            center_filter: Optional list of ADCIDs to filter on for a mapping subset
        Returns:
          dictionary mapping adcid to adcid-group label correspondence
        """
        project = self.get_metadata()
        info = project.get_info()

        if not info:
            return CenterMapInfo(centers={})

        if center_filter:
            log.info(f"Filtering mapping to the following centers: {center_filter}")
            if 'centers' not in info:
                log.error("Expected 'centers' attribute in metadata info")
                return CenterMapInfo(centers={})

            info['centers'] = {adcid: data for adcid, data in info['centers'].items()
                               if adcid in center_filter}
        try:
            center_map = CenterMapInfo.model_validate(info)
        except ValidationError as error:
            log.error('unable to parse center table: %s', str(error))
            center_map = CenterMapInfo(centers={})

        return center_map

    def get_adcid(self, group_id: str) -> Optional[int]:
        """Returns the ADCID for the center group.

        Args:
          group_id: the ID for the center group
        Returns:
          the ADCID for the center
        """
        center_map = self.get_center_map()
        for adcid, center_info in center_map.centers.items():
            if center_info.group == group_id:
                return adcid
        return None

    def get_center(self, adcid: int) -> Optional[CenterGroup]:
        """Returns the center group for the given ADCID.

        Args:
            adcid: The ADCID of the center group to retrieve.

        Returns:
            The CenterGroup for the center. None if no group is found.

        Raises:
            AssertionError: If no center is found for the given ADCID.
        """
        center_map = self.get_center_map()
        center_info = center_map.get(adcid)
        if not center_info:
            return None

        group_id = center_info.group
        group = self._fw.find_group(group_id=str(group_id))
        if not group:
            return None

        center_group = CenterGroup.create_from_group_adaptor(adaptor=group)
        if self.redcap_param_repo:
            center_group.set_redcap_param_repo(self.redcap_param_repo)

        return center_group

    def get_centers(self) -> List[CenterGroup]:
        """Returns the center groups for all centers.

        Returns:
            The list of center groups.
        """
        centers = []
        center_map = self.get_center_map()
        for center_info in center_map.centers.values():
            group_id = center_info.group
            group = self._fw.find_group(group_id=(group_id))
            if group:
                center = CenterGroup.create_from_group_adaptor(adaptor=group)
                centers.append(center)

        return centers

    def add_center_user(self, user: User) -> None:
        """Authorizes a user to access the metadata project of nacc group.

        Args:
          user: the user object
        """
        assert user.id, "User must have user ID"

        metadata_project = self.get_metadata()
        read_only_role = self._fw.get_role('read-only')
        assert read_only_role, "Expecting read-only role to exist"

        metadata_project.add_user_role(user=user, role=read_only_role)

    def get_admin_project(self) -> ProjectAdaptor:
        """Returns the admin project.

        Returns:
         the admin project object
        """
        if not self.__admin_project:
            self.__admin_project = self.get_project('project-admin')
            assert self.__admin_project, ("Expecting project-admin project. "
                                          "Check user has permissions.")

        return self.__admin_project
