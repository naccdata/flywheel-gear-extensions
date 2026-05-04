from natsort import natsorted


def natural_ordering(values: list[str], reverse=False) -> list[str]:
    return natsorted(seq=values, reverse=reverse)


def get_min_value(values: list[str]) -> str:
    sorted_values = natural_ordering(values=values)
    return sorted_values[0]


def get_max_value(values: list[str]) -> str:
    sorted_values = natural_ordering(values=values, reverse=True)
    return sorted_values[0]
