from typing import List, Optional


class User:

    def __init__(
        self,
        id: Optional[str],
        firstname: Optional[str],
        lastname: Optional[str],
        email: Optional[str],
        # avatar: Optional[str],
        # avatars: Optional[Avatars],
        roles: Optional[List[str]],
        root: Optional[bool],
        disabled: Optional[bool],
        # preferences: Optional[preferences],
        # wechat: Optional[wechat],
        # firstlogin: Optional[firstlogin],
        # lastlogin: Optional[lastlogin],
        # created: Optional[created],
        # modified: Optional[modified],
        # deleted: Optional[deleted],
        # api_key: Optional[api_key],
        # api_keys: Optional[api_keys]
    ) -> None:
        ...

    @property
    def id(self) -> Optional[str]:
        ...
