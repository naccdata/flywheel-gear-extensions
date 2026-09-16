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
    curator.prepare_table(_uds_file(), table, FormScope.UDS)

    assert table.get("_prev_record.info") == {"resolved": {"genman": 1}}


def test_prev_record_not_leaked_across_subjects(curator: FormCurator) -> None:
    """The next subject's first file does not see the prior record."""
    _seed_prev_uds_visit(curator, genman=1)

    # start the next subject
    curator.pre_curate(SimpleNamespace(label="NACC977299"), SymbolTable(), [])

    table = _resolvable_table()
    curator.prepare_table(_uds_file(), table, FormScope.UDS)

    assert table.get("_prev_record.info") is None
