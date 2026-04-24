from typing import Any, Optional


class ApiException(Exception):
    status: Optional[int]
    reason: Optional[str]
    body: Optional[str]
    detail: Optional[str]
    headers: Optional[Any]

    def __init__(
        self,
        status: Optional[int] = None,
        reason: Optional[str] = None,
        http_resp: Optional[Any] = None,
    ) -> None: ...
