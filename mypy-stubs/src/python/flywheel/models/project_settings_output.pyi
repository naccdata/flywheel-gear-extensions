from typing import List

from .viewer_app import ViewerApp


class ProjectSettingsOutput:

    @property
    def viewer_apps(self) -> List[ViewerApp]:
        ...
