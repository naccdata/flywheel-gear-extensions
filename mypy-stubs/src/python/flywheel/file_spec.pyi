from typing import Optional


class FileSpec:

    def __init__(self,
                 name: str,
                 contents: str,
                 content_type: str,
                 size: Optional[int] = None) -> None:
        ...

    @property
    def name(self) -> str:
        ...
