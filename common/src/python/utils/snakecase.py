import re


def snakecase_ordinal(match: re.Match) -> str:
    r"""Returns the snakecase expression for a match of the pattern "([a-z\d])([A-Z]+)".

    Inserts an underscore except when the match is an ordinal such as 1ST, 2ND,
    3RD, 4TH, etc.

    Args:
      match: the match object to the pattern "([a-z\d])([A-Z]+)"
    Returns:
      the string corresponding to the match
    """
    prefix = match.group(1)
    suffix = match.group(2)
    if prefix.isalpha():
        return f"{prefix}_{suffix}"

    if re.search(r"^(ST|ND|RD|TH)$", suffix):
        return f"{prefix}{suffix}"

    return f"{prefix}_{suffix}"


def snakecase(word: str) -> str:
    """Returns the transformation of the word into snakecase.

    Inserts underscores and converts to lowercase.

    All of these strings
      - 'ALPHABeta'
      - 'AlphaBeta'
      - 'alphaBeta'
      - 'alpha beta'
      - 'alpha-beta'
    are converted to 'alpha_beta'.

    Based on `inflection.underscore` but fixes issues with ordinals
    such as `1ST` which is converted to `1_st` by `underscore`.

    Args:
      word: the word to be transformed

    Returns:
      transformed string
    """
    word = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", word)
    word = re.sub(r"([a-z\d])([A-Z]+)", snakecase_ordinal, word)
    word = re.sub(r"[ \t]+", "_", word)
    word = word.replace("-", "_")
    return word.lower()
