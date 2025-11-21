from flywheel.models.container_parents import ContainerParents


class ContainerOutput:
    @property
    def id(self) -> str: ...

    @property
    def label(self) -> str: ...

    @property
    def parents(self) -> ContainerParents: ...
