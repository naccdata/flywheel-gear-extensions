class Manifest:

    def __init__(self, manifest=None) -> None:
        ...

    @property
    def schema(self):
        ...

    @property
    def gear_spec_schema(self):
        ...

    @property
    def author(self):
        ...

    @property
    def config(self):
        ...

    @property
    def description(self):
        ...

    @property
    def inputs(self):
        ...

    @property
    def label(self):
        ...

    @property
    def license(self):
        ...

    @property
    def name(self):
        ...

    @property
    def source(self):
        ...

    @property
    def url(self):
        ...

    @property
    def version(self):
        ...

    @property
    def environment(self):
        ...

    def __getitem__(self, dotty_key):
        ...

    @staticmethod
    def get_manifest_from_file(path=None):
        ...

    def get_value(self, dotty_key):
        ...

    def to_json(
        self, path, validate: bool = True, ensure_ascii: bool = True
    ) -> None:
        ...

    def get_docker_image_name_tag(self):
        ...

    def validate(self, validate_classification: bool = False) -> None:
        ...

    def is_valid(self):
        ...

    def derive_config_schema(self, full: bool = True):
        ...
