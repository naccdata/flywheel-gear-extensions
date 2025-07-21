class Job:

    @property
    def id(self) -> str:
        ...

    @property
    def state(self) -> str:
        ...

    @property
    def retried(self) -> str:
        ...

    def reload(self) -> Job:
        ...
