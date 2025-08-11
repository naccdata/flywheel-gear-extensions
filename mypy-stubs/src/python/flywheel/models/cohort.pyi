import enum


class Cohort(str, enum.Enum):
    CONTROL = "Control"
    STUDY = "Study"