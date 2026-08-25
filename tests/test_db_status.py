import sqlite3

import pytest

from state.db import (
    INVOICE_STATUS_OPEN,
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_UNKNOWN,
    determine_db_status,
    save_invoice_id_in_db,
)


def make_invoice(number="F2024-001", status=INVOICE_STATUS_OPEN):
    """Build a minimal stand-in for an Invoice with just a number and a status."""
    # determine_db_status / save_invoice_id_in_db only read .number and .status,
    # so a lightweight stand-in keeps these tests off the pydantic model.
    class _Inv:
        pass

    inv = _Inv()
    inv.number = number
    inv.status = status
    return inv


@pytest.fixture
def connection():
    """Yield an in-memory database with the same schema init_db creates."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS invoice_ids(invoice_id text, status text, "
        "PRIMARY KEY(invoice_id, status))"
    )
    yield conn
    conn.close()


def test_unknown_when_invoice_not_in_db(connection):
    """An invoice that was never synced has status unknown."""
    assert determine_db_status(connection, make_invoice()) == INVOICE_STATUS_UNKNOWN


def test_open_when_only_open_row_present(connection):
    """A single open row reports open."""
    save_invoice_id_in_db(connection, make_invoice(status=INVOICE_STATUS_OPEN))
    assert determine_db_status(connection, make_invoice()) == INVOICE_STATUS_OPEN


def test_paid_when_only_paid_row_present(connection):
    """A single paid row reports paid."""
    save_invoice_id_in_db(connection, make_invoice(status=INVOICE_STATUS_PAID))
    assert determine_db_status(connection, make_invoice()) == INVOICE_STATUS_PAID


def test_paid_takes_precedence_over_open(connection):
    """With both rows recorded, the most advanced status wins."""
    # An invoice that went open -> paid has both rows; paid must win.
    save_invoice_id_in_db(connection, make_invoice(status=INVOICE_STATUS_OPEN))
    save_invoice_id_in_db(connection, make_invoice(status=INVOICE_STATUS_PAID))
    assert determine_db_status(connection, make_invoice()) == INVOICE_STATUS_PAID


def test_status_is_scoped_to_the_requested_invoice(connection):
    """Rows for another invoice number do not leak into this invoice's status."""
    save_invoice_id_in_db(connection, make_invoice(number="OTHER", status=INVOICE_STATUS_PAID))
    assert determine_db_status(connection, make_invoice(number="F2024-001")) == INVOICE_STATUS_UNKNOWN
