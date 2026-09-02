from types import SimpleNamespace

import pytest

from main import _determine_action
from modules.state.db import (
    ACTION_OPEN,
    ACTION_PAID,
    ACTION_PROCESSED,
    ACTION_SKIP,
    INVOICE_STATUS_OPEN,
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_UNKNOWN,
    INVOICE_STATUS_VOIDED,
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


class TestVoidedInDb:
    """Once the state database records an invoice as voided, it is final.

    determine_db_status reports voided in preference to paid and open, so this
    db status reaches _determine_action for any HubSpot status the invoice may
    have picked up since. Every one of them has to skip: falling through to the
    ValueError would end the whole sync run over a single stale invoice, taking
    the rest of the page and every later page with it.
    """

    @pytest.mark.parametrize(
        "hubspot_status",
        [INVOICE_STATUS_OPEN, INVOICE_STATUS_PAID, INVOICE_STATUS_VOIDED, "draft"],
    )
    def test_voided_db_status_always_skips(self, hubspot_status):
        """No HubSpot status can pull a voided invoice back into the sync."""
        assert _determine_action(INVOICE_STATUS_VOIDED, invoice(hubspot_status)) == ACTION_SKIP

    def test_reopened_invoice_does_not_end_the_run(self):
        """The regression that motivated the guard: voided here, open again in HubSpot.

        Reached when WeFact reported Vervallen, main wrote voided to HubSpot and
        recorded it, and someone then reopened the invoice in HubSpot.
        """
        assert _determine_action(INVOICE_STATUS_VOIDED, invoice(INVOICE_STATUS_OPEN)) == ACTION_SKIP

    def test_late_payment_does_not_end_the_run(self):
        """An overdue invoice paid after it was voided must not raise either.

        WeFact Vervallen means the payment term expired, not that the invoice
        was cancelled, so it can still be settled afterwards.
        """
        assert _determine_action(INVOICE_STATUS_VOIDED, invoice(INVOICE_STATUS_PAID)) == ACTION_SKIP
