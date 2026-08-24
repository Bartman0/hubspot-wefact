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
    """Build the smallest object _determine_action accepts: something with .status."""
    # _determine_action only reads .status off the invoice.
    return SimpleNamespace(status=status)


def test_open_in_db_and_hubspot_is_already_processed():
    """An open invoice we already generated needs its WeFact paid status checked."""
    assert _determine_action(INVOICE_STATUS_OPEN, invoice(INVOICE_STATUS_OPEN)) == ACTION_PROCESSED


def test_paid_in_db_and_hubspot_is_skipped():
    """Once the db records an invoice as paid there is nothing left to query."""
    assert _determine_action(INVOICE_STATUS_PAID, invoice(INVOICE_STATUS_PAID)) == ACTION_SKIP


def test_open_in_db_then_paid_invoice_triggers_paid():
    """An invoice we generated earlier and that is now paid moves to the paid action."""
    assert _determine_action(INVOICE_STATUS_OPEN, invoice(INVOICE_STATUS_PAID)) == ACTION_PAID


def test_unknown_db_with_open_invoice_triggers_open():
    """An unseen open invoice must be generated in WeFact."""
    assert _determine_action(INVOICE_STATUS_UNKNOWN, invoice(INVOICE_STATUS_OPEN)) == ACTION_OPEN


def test_unknown_db_with_paid_invoice_is_treated_as_open():
    """An unseen paid invoice is generated first rather than marked paid."""
    # A paid invoice we have never seen still needs to be generated first.
    assert _determine_action(INVOICE_STATUS_UNKNOWN, invoice(INVOICE_STATUS_PAID)) == ACTION_OPEN


def test_unhandled_invoice_status_is_skipped():
    """HubSpot statuses outside open and paid are not synced."""
    assert _determine_action(INVOICE_STATUS_UNKNOWN, invoice("draft")) == ACTION_SKIP
    assert _determine_action(INVOICE_STATUS_UNKNOWN, invoice("voided")) == ACTION_SKIP


def test_open_invoice_with_paid_db_is_inconsistent_and_raises():
    """Going backwards from paid to open is treated as a data error."""
    # Regressing from paid back to open should never happen; guard it.
    with pytest.raises(ValueError):
        _determine_action(INVOICE_STATUS_PAID, invoice(INVOICE_STATUS_OPEN))
