import os
import sqlite3
from pathlib import Path

from modules.models.invoice import Invoice


INVOICE_STATUS_OPEN = "open"
INVOICE_STATUS_PAID = "paid"
INVOICE_STATUS_UNKNOWN = "unknown"

ACTION_OPEN = INVOICE_STATUS_OPEN
ACTION_PAID = INVOICE_STATUS_PAID
ACTION_PROCESSED = "processed"
ACTION_SKIP = "skip"
ACTION_ERROR = "error"


def init_db():
    """Open the local state database, creating the file and table when absent.

    The database lives at <APPDATA>/hubspot-wefact.db, falling back to the
    "data" directory relative to the working directory (which is what the
    Docker image mounts). It stores one row per (invoice number, status) pair,
    which is what makes a sync run idempotent.

    Returns the open sqlite3 connection.
    """
    data_path = os.getenv("APPDATA", "data")

    db_path = Path(data_path) / "hubspot-wefact.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS invoice_ids(invoice_id text, status text, PRIMARY KEY(invoice_id, status))"
    )
    return connection


def determine_db_status(connection, invoice):
    """Return how far this invoice has already been processed.

    An invoice accumulates one row per status it passed through, so the most
    advanced one wins: paid before open before unknown. unknown means the
    invoice has never been synced.
    """
    cursor = connection.cursor()
    cursor.execute("SELECT invoice_id, status FROM invoice_ids WHERE invoice_id=?", (invoice.number,))
    statuses = [row[1] for row in cursor.fetchall()]
    status = INVOICE_STATUS_UNKNOWN
    # status PAID goes before OPEN before UNKNOWN
    if INVOICE_STATUS_OPEN in statuses:
        status = INVOICE_STATUS_OPEN
    if INVOICE_STATUS_PAID in statuses:
        status = INVOICE_STATUS_PAID
    return status


def save_invoice_id_in_db(connection, invoice: Invoice):
    """Record that this invoice was processed in its current status, and commit.

    Inserting the same (number, status) pair twice violates the primary key and
    raises sqlite3.IntegrityError.
    """
    connection.execute(
        "INSERT INTO invoice_ids(invoice_id, status) VALUES(?,?)",
        (invoice.number, invoice.status),
    )
    connection.commit()
