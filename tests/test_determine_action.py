from types import SimpleNamespace

import pytest

from main import _determine_action
from state.db import (
    ACTION_OPEN,
    ACTION_PAID,
    ACTION_PROCESSED,
    ACTION_SKIP,
    INVOICE_STATUS_OPEN,
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_UNKNOWN,
)


def invoice(status):
    # _determine_action only reads .status off the invoice.
    return SimpleNamespace(status=status)


def test_already_processed_when_statuses_match():
    assert _determine_action(INVOICE_STATUS_OPEN, invoice(INVOICE_STATUS_OPEN)) == ACTION_PROCESSED
    assert _determine_action(INVOICE_STATUS_PAID, invoice(INVOICE_STATUS_PAID)) == ACTION_PROCESSED


def test_open_in_db_then_paid_invoice_triggers_paid():
    assert _determine_action(INVOICE_STATUS_OPEN, invoice(INVOICE_STATUS_PAID)) == ACTION_PAID


def test_unknown_db_with_open_invoice_triggers_open():
    assert _determine_action(INVOICE_STATUS_UNKNOWN, invoice(INVOICE_STATUS_OPEN)) == ACTION_OPEN


def test_unknown_db_with_paid_invoice_is_treated_as_open():
    # A paid invoice we have never seen still needs to be generated first.
    assert _determine_action(INVOICE_STATUS_UNKNOWN, invoice(INVOICE_STATUS_PAID)) == ACTION_OPEN


def test_unhandled_invoice_status_is_skipped():
    assert _determine_action(INVOICE_STATUS_UNKNOWN, invoice("draft")) == ACTION_SKIP
    assert _determine_action(INVOICE_STATUS_UNKNOWN, invoice("voided")) == ACTION_SKIP


def test_open_invoice_with_paid_db_is_inconsistent_and_raises():
    # Regressing from paid back to open should never happen; guard it.
    with pytest.raises(ValueError):
        _determine_action(INVOICE_STATUS_PAID, invoice(INVOICE_STATUS_OPEN))
