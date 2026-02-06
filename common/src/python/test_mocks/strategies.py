"""Shared Hypothesis strategies for testing."""

from datetime import datetime
from typing import Any

from hypothesis import strategies as st
from nacc_common.error_models import QCStatus, VisitMetadata


@st.composite
def ptid_strategy(draw) -> str:
    """Generate valid PTID strings matching pattern ^[!-~]{1,10}$.

    PTIDs must match printable non-whitespace ASCII characters, 1-10 chars.
    Pattern: ^[!-~]{1,10}$ (ASCII 33-126, excluding space)
    Also ensure they don't become empty after clean_ptid (strip leading zeros).
    """
    alphabet = "".join(
        chr(i) for i in range(33, 127)
    )  # ASCII 33-126 (printable, no space)

    # Generate a PTID that won't become empty after cleaning
    ptid = draw(st.text(alphabet=alphabet, min_size=1, max_size=10))

    # Ensure it doesn't become empty after clean_ptid processing
    # clean_ptid strips whitespace and leading zeros
    cleaned = ptid.strip().lstrip("0")
    if not cleaned:
        # If it becomes empty, prepend a non-zero character
        ptid = "A" + ptid

    return ptid


@st.composite
def visit_metadata_strategy(draw) -> VisitMetadata:
    """Generate random VisitMetadata for testing.

    PTIDs must not be all zeros or empty after stripping leading zeros.
    """
    # Generate PTID that won't be all zeros
    ptid = draw(
        st.text(
            min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
    )

    # Ensure PTID is not all zeros (would be invalid after lstrip("0"))
    if ptid.strip("0") == "":
        # Replace with a valid PTID containing at least one non-zero character
        ptid = "A" + ptid[1:] if len(ptid) > 1 else "A"

    # Generate dates with 4-digit years to match VisitEvent validation pattern
    date = draw(
        st.dates(
            min_value=datetime(2000, 1, 1).date(),
            max_value=datetime(2030, 12, 31).date(),
        ).map(lambda d: d.strftime("%Y-%m-%d"))
    )
    visitnum = draw(st.text(min_size=1, max_size=3, alphabet="0123456789"))
    module = draw(st.sampled_from(["UDS", "FTLD", "LBD", "MDS"]))
    packet = draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"])))

    return VisitMetadata(
        ptid=ptid,
        date=date,
        visitnum=visitnum,
        module=module,
        packet=packet,
    )


@st.composite
def json_file_strategy(draw) -> dict[str, Any]:
    """Generate random JSON file data for testing.

    PTIDs must not be all zeros or empty after stripping leading zeros.
    """
    # Generate PTID that won't be all zeros
    ptid = draw(
        st.text(
            min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
    )

    # Ensure PTID is not all zeros (would be invalid after lstrip("0"))
    if ptid.strip("0") == "":
        # Replace with a valid PTID containing at least one non-zero character
        ptid = "A" + ptid[1:] if len(ptid) > 1 else "A"

    # Generate dates with 4-digit years to match VisitEvent validation pattern
    visitdate = draw(
        st.dates(
            min_value=datetime(2000, 1, 1).date(),
            max_value=datetime(2030, 12, 31).date(),
        ).map(lambda d: d.strftime("%Y-%m-%d"))
    )
    visitnum = draw(st.text(min_size=1, max_size=3, alphabet="0123456789"))
    module = draw(st.sampled_from(["UDS", "FTLD", "LBD", "MDS"]))
    packet = draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"])))

    forms_json = {
        "ptid": ptid,
        "visitdate": visitdate,
        "visitnum": visitnum,
        "module": module,
    }
    if packet:
        forms_json["packet"] = packet

    return forms_json


@st.composite
def json_file_forms_metadata_strategy(draw) -> dict[str, Any]:
    """Generate JSON file forms metadata for testing."""
    # Generate ptid that won't become empty after lstrip("0")
    ptid_base = draw(
        st.text(
            min_size=1, max_size=8, alphabet=st.characters(whitelist_categories=["Lu"])
        )
    )
    ptid_prefix = draw(st.text(min_size=0, max_size=3, alphabet="0"))
    ptid = ptid_prefix + ptid_base  # Ensures ptid won't be all zeros

    return {
        "ptid": ptid,
        "visitnum": draw(
            st.text(
                min_size=1,
                max_size=3,
                alphabet=st.characters(whitelist_categories=["Nd"]),
            )
        ),
        "visitdate": draw(st.dates().map(lambda d: d.strftime("%Y-%m-%d"))),
        "module": draw(st.sampled_from(["UDS", "LBD", "FTLD", "MDS"])),
        "packet": draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"]))),
        "adcid": draw(st.integers(min_value=1, max_value=999)),
    }


@st.composite
def valid_visit_metadata_strategy(draw) -> dict[str, Any]:
    """Generate valid VisitMetadata with all required fields.

    PTIDs must not be all zeros or empty after stripping leading zeros.
    """
    # Generate PTID that won't be all zeros
    ptid = draw(
        st.text(
            min_size=1,
            max_size=10,
            alphabet=st.characters(whitelist_categories=("Nd", "Lu")),
        )
    )

    # Ensure PTID is not all zeros (would be invalid after lstrip("0"))
    if ptid.strip("0") == "":
        # Replace with a valid PTID containing at least one non-zero character
        ptid = "A" + ptid[1:] if len(ptid) > 1 else "A"

    return {
        "ptid": ptid,
        "date": draw(st.dates().map(lambda d: d.strftime("%Y-%m-%d"))),
        "module": draw(st.sampled_from(["UDS", "LBD", "FTLD", "MDS"])),
        "visitnum": draw(
            st.one_of(
                st.none(),
                st.text(
                    min_size=1,
                    max_size=3,
                    alphabet=st.characters(whitelist_categories=["Nd"]),
                ),
            )
        ),
        "packet": draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"]))),
        "adcid": draw(st.one_of(st.none(), st.integers(min_value=1, max_value=999))),
        "naccid": draw(st.one_of(st.none(), st.text(min_size=1, max_size=10))),
    }


@st.composite
def invalid_visit_metadata_strategy(draw) -> dict[str, Any]:
    """Generate invalid VisitMetadata missing required fields."""
    # Generate metadata with at least one required field missing or None
    base_data = {
        "ptid": draw(st.one_of(st.none(), st.text(min_size=1, max_size=10))),
        "date": draw(
            st.one_of(st.none(), st.dates().map(lambda d: d.strftime("%Y-%m-%d")))
        ),
        "module": draw(
            st.one_of(st.none(), st.sampled_from(["UDS", "LBD", "FTLD", "MDS"]))
        ),
        "visitnum": draw(st.one_of(st.none(), st.text(min_size=1, max_size=3))),
        "packet": draw(st.one_of(st.none(), st.sampled_from(["I", "F", "T"]))),
    }

    # Ensure at least one required field (ptid, date, module) is None or missing
    required_fields = ["ptid", "date", "module"]
    field_to_invalidate = draw(st.sampled_from(required_fields))
    base_data[field_to_invalidate] = None

    return base_data


@st.composite
def csv_row_strategy(draw) -> dict[str, Any]:
    """Generate a valid CSV row for identifier lookup."""
    ptid = draw(ptid_strategy())
    return {
        "adcid": 1,
        "ptid": ptid,
        "visitdate": "2024-01-15",
        "visitnum": "1",
        "packet": "I",
        "formver": "4.0",
        "var1": draw(st.integers(min_value=0, max_value=999)),
    }


@st.composite
def qc_status_strategy(draw) -> QCStatus:
    """Generate QC status (PASS or non-PASS)."""
    return draw(st.sampled_from(["PASS", "FAIL", "IN REVIEW"]))


# Date strategies
date_strategy = st.dates(
    min_value=datetime(2000, 1, 1).date(),
    max_value=datetime(2030, 12, 31).date(),
).map(lambda d: d.strftime("%Y-%m-%d"))

# Module strategies
module_strategy = st.sampled_from(["UDS", "FTLD", "LBD", "MDS"])

# Packet strategies
packet_strategy = st.one_of(st.none(), st.sampled_from(["I", "F", "T"]))

# PTID strategies for different use cases
simple_ptid_strategy = st.text(
    min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)

# Visit number strategies
visitnum_strategy = st.text(min_size=1, max_size=3, alphabet="0123456789")


@st.composite
def user_context_strategy(draw):
    """Generate random UserContext for testing."""
    from users.event_models import UserContext
    from users.user_entry import PersonName

    email = draw(st.emails())
    name = draw(
        st.one_of(
            st.none(),
            st.builds(
                PersonName,
                first_name=st.text(
                    min_size=1,
                    max_size=20,
                    alphabet=st.characters(whitelist_categories=["Lu", "Ll"]),
                ),
                last_name=st.text(
                    min_size=1,
                    max_size=20,
                    alphabet=st.characters(whitelist_categories=["Lu", "Ll"]),
                ),
            ),
        )
    )
    center_id = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=999)))
    registry_id = draw(st.one_of(st.none(), st.text(min_size=1, max_size=20)))
    auth_email = draw(st.one_of(st.none(), st.emails()))

    return UserContext(
        email=email,
        name=name,
        center_id=center_id,
        registry_id=registry_id,
        auth_email=auth_email,
    )


@st.composite
def error_details_strategy(draw):
    """Generate random error details dictionary for testing."""
    message = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))
    action_needed = draw(st.one_of(st.none(), st.text(min_size=1, max_size=50)))

    details = {}
    if message is not None:
        details["message"] = message
    if action_needed is not None:
        details["action_needed"] = action_needed

    # Add some additional random fields
    additional_fields = draw(
        st.dictionaries(
            keys=st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(whitelist_categories=["Lu", "Ll", "Nd"]),
            ),
            values=st.one_of(
                st.text(min_size=1, max_size=50), st.integers(), st.booleans()
            ),
            min_size=0,
            max_size=3,
        )
    )
    details.update(additional_fields)

    return details


@st.composite
def error_event_strategy(draw):
    """Generate random UserProcessEvent for testing."""
    from users.event_models import EventCategory, EventType, UserProcessEvent

    category = draw(st.sampled_from(list(EventCategory)))
    user_context = draw(user_context_strategy())
    message = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))

    return UserProcessEvent(
        event_type=EventType.ERROR,
        category=category,
        user_context=user_context,
        message=message or "",
    )
