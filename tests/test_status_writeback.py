from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import main
from modules.models.invoice import Invoice
from modules.state.db import INVOICE_STATUS_OPEN, INVOICE_STATUS_PAID, INVOICE_STATUS_VOIDED
from modules.wefact_client.invoice import (
    WEFACT_STATUS_BETAALD,
    WEFACT_STATUS_VERVALLEN,
    ResultType,
)


def make_invoice(status=INVOICE_STATUS_OPEN):
    """Build a HubSpot invoice the sync has already processed."""
    return Invoice(
        id="inv-1",
        number="F2024-001",
        status=status,
        due_date=date(2026, 7, 21),
        invoice_date=date(2026, 6, 21),
        amount_billed=100.0,
    )


def wefact_result(status):
    """A WeFact lookup reporting the given raw Status, the way WeFact sends it."""
    return ResultType(persist=False, data={"invoice": {"Status": status}}, errors=[])


def failed_result():
    """A WeFact lookup that could not find the invoice."""
    return ResultType(persist=False, data={}, errors=["invoice not found"])


class TestWefactStatusToHubspot:
    """The table main.py translates a WeFact status through.

    Only statuses listed here are written back to HubSpot. Anything else,
    including the None wefact_invoice_status returns for a status it could not
    read, has to miss the table and leave HubSpot alone.
    """

    def test_paid_maps_to_paid(self):
        """WeFact Betaald becomes the HubSpot paid status."""
        assert main.WEFACT_STATUS_TO_HUBSPOT[WEFACT_STATUS_BETAALD] == INVOICE_STATUS_PAID

    def test_expired_maps_to_voided(self):
        """WeFact Vervallen becomes the HubSpot voided status."""
        assert main.WEFACT_STATUS_TO_HUBSPOT[WEFACT_STATUS_VERVALLEN] == INVOICE_STATUS_VOIDED

    def test_unmapped_statuses_are_absent(self):
        """Concept, sent, partly paid and credited have no HubSpot counterpart."""
        for status in (0, 2, 3, 8):
            assert status not in main.WEFACT_STATUS_TO_HUBSPOT

    def test_unreadable_status_is_absent(self):
        """wefact_invoice_status returns None, which must not map to anything."""
        assert None not in main.WEFACT_STATUS_TO_HUBSPOT


@pytest.fixture
def drive():
    """Run one already-processed invoice through process_batch_of_invoices.

    Everything main.py collaborates with is patched, so the test only exercises
    the ACTION_PROCESSED branch that carries a WeFact status back to HubSpot.
    Yields a callable returning the patched WeFact lookup, status writer and
    state-database writer.
    """

    def run(wefact_lookup):
        invoice = make_invoice()
        with patch.object(main, "get_invoices", return_value=([invoice], None)), patch.object(
            main, "determine_db_status", return_value=INVOICE_STATUS_OPEN
        ), patch.object(
            main, "get_invoice_status", return_value=wefact_lookup
        ) as get_status, patch.object(
            main, "set_invoice_status"
        ) as set_status, patch.object(main, "save_invoice_id_in_db") as save:
            main.process_batch_of_invoices(MagicMock(), MagicMock(), None)
        return get_status, set_status, save

    return run


def test_wefact_is_queried_with_the_invoice_number(drive):
    """The WeFact lookup takes the invoice number, not the Invoice model.

    Passing the model would send the whole repr as the WeFact InvoiceCode.
    """
    get_status, _, _ = drive(wefact_result("4"))

    get_status.assert_called_once_with("F2024-001")


def test_paid_invoice_is_pushed_to_hubspot(drive):
    """A Betaald lookup writes the paid status onto the HubSpot invoice."""
    _, set_status, save = drive(wefact_result("4"))

    assert set_status.call_args.args[1].number == "F2024-001"
    assert set_status.call_args.args[2] == INVOICE_STATUS_PAID
    assert save.called


def test_expired_invoice_is_voided_in_hubspot(drive):
    """A Vervallen lookup writes the voided status onto the HubSpot invoice."""
    _, set_status, save = drive(wefact_result("9"))

    assert set_status.call_args.args[1].number == "F2024-001"
    assert set_status.call_args.args[2] == INVOICE_STATUS_VOIDED
    assert save.called


@pytest.mark.parametrize("status", ["0", "2", "3", "8"])
def test_unmapped_wefact_status_leaves_hubspot_alone(drive, status):
    """Concept, sent, partly paid and credited are never written back."""
    _, set_status, save = drive(wefact_result(status))

    set_status.assert_not_called()
    save.assert_not_called()


def test_unreadable_wefact_status_leaves_hubspot_alone(drive):
    """A Status that will not parse must not reach HubSpot as a real status."""
    _, set_status, save = drive(wefact_result("onbekend"))

    set_status.assert_not_called()
    save.assert_not_called()


def test_failed_wefact_lookup_does_not_touch_hubspot(drive):
    """WeFact errors are logged and the branch stops before updating HubSpot.

    This also guards the error check itself: reading an undefined `errors` here
    used to raise NameError before HubSpot was ever reached.
    """
    _, set_status, save = drive(failed_result())

    set_status.assert_not_called()
    save.assert_not_called()
