"""Tests for FormCurator previous-record state across subjects."""

from types import SimpleNamespace
from typing import Any

import pytest
from attribute_curator_app.form_curator import FormCurator
from nacc_attribute_deriver.symbol_table import SymbolTable
from nacc_attribute_deriver.utils.scope import FormScope


@pytest.fixture
def curator() -> FormCurator:
    """Bare FormCurator holding only the private state the tests touch."""
    instance = object.__new__(FormCurator)
    instance._Curator__force_curate = False  # type: ignore[attr-defined]  # noqa: SLF001
    instance._FormCurator__rxclass = {}  # type: ignore[attr-defined]  # noqa: SLF001
    instance._FormCurator__prev_record = None  # type: ignore[attr-defined]  # noqa: SLF001
    instance._FormCurator__prev_scope = None  # type: ignore[attr-defined]  # noqa: SLF001
    return instance


def _uds_file(filename: str = "sub_UDS.json") -> SimpleNamespace:
    return SimpleNamespace(filename=filename, uds_visitdate=None)


def _seed_prev_uds_visit(curator: FormCurator, genman: int) -> None:
    """Set previous-record state to a finished UDS visit."""
    curator._FormCurator__prev_scope = FormScope.UDS  # type: ignore[attr-defined]  # noqa: SLF001
    curator._FormCurator__prev_record = {  # type: ignore[attr-defined]  # noqa: SLF001
        "resolved": {"genman": genman}
    }


def _resolvable_table(genman: Any = None) -> SymbolTable:
    return SymbolTable({"file.info.forms.json": {"genman": genman}})


def test_pre_curate_resets_prev_record(curator: FormCurator) -> None:
    _seed_prev_uds_visit(curator, genman=1)

    curator.pre_curate(SimpleNamespace(label="NACC000002"), SymbolTable(), [])

    assert curator._FormCurator__prev_record is None  # type: ignore[attr-defined]  # noqa: SLF001
    assert curator._FormCurator__prev_scope is None  # type: ignore[attr-defined]  # noqa: SLF001


def test_prev_record_carried_within_subject(curator: FormCurator) -> None:
    """A later visit sees the earlier visit's record."""
    _seed_prev_uds_visit(curator, genman=1)

    table = _resolvable_table()
    curator.prepare_table(_uds_file(), table, FormScope.UDS)  # type: ignore[arg-type]

    assert table.get("_prev_record.info") == {"resolved": {"genman": 1}}


def test_prev_record_not_leaked_across_subjects(curator: FormCurator) -> None:
    """The next subject's first file does not see the prior record."""
    _seed_prev_uds_visit(curator, genman=1)

    # start the next subject
    curator.pre_curate(SimpleNamespace(label="NACC977299"), SymbolTable(), [])

    table = _resolvable_table()
    curator.prepare_table(_uds_file(), table, FormScope.UDS)  # type: ignore[arg-type]

    assert table.get("_prev_record.info") is None


@pytest.fixture
def backprop_curator() -> FormCurator:
    """Bare FormCurator holding only the scope references back-prop reads."""
    instance = object.__new__(FormCurator)
    scoped = {FormScope.UDS: {"naccnihr", "naccedulvl", "naccsex"}}
    era_scoped = {FormScope.UDS: {"naccnihr", "naccedulvl"}}
    instance._FormCurator__scope_reference = scoped  # type: ignore[attr-defined]  # noqa: SLF001
    instance._FormCurator__era_scope_reference = era_scoped  # type: ignore[attr-defined]  # noqa: SLF001
    return instance


def _uds_form(formver: Any, filename: str) -> SimpleNamespace:
    return SimpleNamespace(
        filename=filename,
        file_info={"forms": {"json": {"formver": formver}}, "derived": {}},
    )


def test_v1v3_values_applied_only_to_pre_v4_files(
    backprop_curator: FormCurator,
) -> None:
    """A participant holds one value for V1-3 rows and another for V4 rows."""
    v3 = _uds_form("3.0", "v3_I.json")
    i4 = _uds_form(4.0, "I4.json")

    backprop_curator.back_propagate_scopes(
        SimpleNamespace(label="NACC000002"),
        {FormScope.UDS: [v3, i4]},
        "derived",
        {"naccnihr": 7, "naccedulvl": 3, "naccsex": 1},
        {"naccnihr": 1, "naccedulvl": 6},
    )

    assert v3.file_info["derived"]["naccnihr"] == 1
    assert v3.file_info["derived"]["naccedulvl"] == 6
    # not quasi-cross-sectional, so the subject-level value still applies
    assert v3.file_info["derived"]["naccsex"] == 1

    assert i4.file_info["derived"]["naccnihr"] == 7
    assert i4.file_info["derived"]["naccedulvl"] == 3


def test_backprop_unchanged_without_v1v3_values(
    backprop_curator: FormCurator,
) -> None:
    """Participants with no V1-3 value behave exactly as before."""
    v3 = _uds_form("3.0", "v3_I.json")
    i4 = _uds_form(4.0, "I4.json")

    backprop_curator.back_propagate_scopes(
        SimpleNamespace(label="NACC000003"),
        {FormScope.UDS: [v3, i4]},
        "derived",
        {"naccnihr": 2, "naccedulvl": 4},
        None,
    )

    assert v3.file_info["derived"]["naccnihr"] == 2
    assert i4.file_info["derived"]["naccnihr"] == 2


def test_missing_formver_keeps_subject_level_value(
    backprop_curator: FormCurator,
) -> None:
    """Files with no readable formver are not treated as V1-3."""
    no_formver = _uds_form(None, "imaging.json")
    unreadable = _uds_form("not-a-number", "odd.json")

    backprop_curator.back_propagate_scopes(
        SimpleNamespace(label="NACC000004"),
        {FormScope.UDS: [no_formver, unreadable]},
        "derived",
        {"naccnihr": 7},
        {"naccnihr": 1},
    )

    assert no_formver.file_info["derived"]["naccnihr"] == 7
    assert unreadable.file_info["derived"]["naccnihr"] == 7
