"""Methods to query identifiers repository."""

import logging
from typing import Optional

from identifiers.identifiers_repository import (
    IdentifierRepository,
    IdentifierRepositoryError,
)
from identifiers.model import IdentifierObject, clean_ptid

log = logging.getLogger(__name__)


def find_naccid(
    repo: IdentifierRepository,
    adcid: int,
    ptid: str,
    active_only: Optional[bool] = False,
) -> Optional[str]:
    """Find the NACCID for a given ADCID, PTID.

    Args:
        repo: Identifiers database repository
        adcid: Center's ADCID
        ptid: Participant ID
        active_only: If True, return the NACCID only if the participant is active

    Returns:
        NACCID if found, else None
    """

    identifier = find_identifier(repo=repo, adcid=adcid, ptid=ptid)

    if not identifier:
        return None

    if active_only and not identifier.active:
        log.warning(
            f"ADCID {adcid}, PTID {ptid} - NACCID {identifier.naccid} is not active"
        )
        return None

    return identifier.naccid


def find_identifier(
    repo: IdentifierRepository,
    adcid: int,
    ptid: str,
) -> Optional[IdentifierObject]:
    """Find the identifier for a given ADCID, PTID.

    Args:
        repo: Identifiers database repository
        adcid: Center's ADCID
        ptid: Participant ID

    Returns:
        IdentifierObject if found, else None
    """

    try:
        identifier = repo.get(adcid=adcid, ptid=clean_ptid(ptid))
    except (IdentifierRepositoryError, TypeError) as error:
        log.error(
            f"Error in looking up identifier for ADCID {adcid}, PTID {ptid}: {error}"
        )
        return None

    if not identifier:
        log.warning(f"Identifier does not exist for ADCID {adcid}, PTID {ptid}")
        return None

    return identifier
