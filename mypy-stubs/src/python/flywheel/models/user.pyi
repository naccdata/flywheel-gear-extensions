from typing import List, Optional


class User:

    def __init__(
        self,
        id: Optional[str] = None,
        firstname: Optional[str] = None,
        lastname: Optional[str] = None,
        email: Optional[str] = None,
        # avatar: Optional[str],
        # avatars: Optional[Avatars],
        roles: Optional[List[str]] = None,
        root: Optional[bool] = None,
        disabled: Optional[bool] = None,
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

    @property
    def email(self) -> Optional[str]:
        ...

    @property
    def firstlogin(self) -> Optional[str]:
        ...