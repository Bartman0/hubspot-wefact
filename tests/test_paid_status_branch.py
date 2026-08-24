from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import main
from models.invoice import Invoice
from state.db import INVOICE_STATUS_OPEN
from wefact_api.invoice import ResultType


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


def paid_result():
    """A WeFact lookup that reports the invoice as fully paid."""
    return ResultType(persist=False, data={"invoice": {"Status": "4"}}, errors=[])


def failed_result():
    """A WeFact lookup that could not find the invoice."""
    return ResultType(persist=False, data={}, errors=["invoice not found"])


@pytest.fixture
def drive():
    """Run one already-processed invoice through process_batch_of_invoices.

    Everything main.py collaborates with is patched, so the test only exercises
    the ACTION_PROCESSED branch that carries a paid status back to HubSpot.
    Yields a callable returning the two patched WeFact/HubSpot mocks.
    """

    def run(wefact_result):
        invoice = make_invoice()
        with patch.object(main, "get_invoices", return_value=([invoice], None)), patch.object(
            main, "determine_db_status", return_value=INVOICE_STATUS_OPEN
        ), patch.object(
            main, "get_invoice_status", return_value=wefact_result
        ) as get_status, patch.object(main, "set_invoice_to_paid") as set_to_paid:
            main.process_batch_of_invoices(MagicMock(), MagicMock(), None)
        return get_status, set_to_paid

    return run


def test_wefact_is_queried_with_the_invoice_number(drive):
    """The WeFact lookup takes the invoice number, not the Invoice model.

    Passing the model would send the whole repr as the WeFact InvoiceCode.
    """
    get_status, _ = drive(paid_result())

    get_status.assert_called_once_with("F2024-001")


def test_paid_invoice_is_pushed_to_hubspot(drive):
    """A paid WeFact lookup hands the invoice to set_invoice_to_paid."""
    _, set_to_paid = drive(paid_result())

    assert set_to_paid.called
    assert set_to_paid.call_args.args[1].number == "F2024-001"


def test_failed_wefact_lookup_does_not_touch_hubspot(drive):
    """WeFact errors are logged and the branch stops before updating HubSpot.

    This also guards the error check itself: reading an undefined `errors` here
    used to raise NameError before HubSpot was ever reached.
    """
    _, set_to_paid = drive(failed_result())

    set_to_paid.assert_not_called()
