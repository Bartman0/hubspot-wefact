import os
import sqlite3
from pathlib import Path

from models.invoice import Invoice


INVOICE_STATUS_OPEN = "open"
INVOICE_STATUS_PAID = "paid"
INVOICE_STATUS_UNKNOWN = "unknown"

ACTION_OPEN = INVOICE_STATUS_OPEN
ACTION_PAID = INVOICE_STATUS_PAID
ACTION_PROCESSED = "processed"
ACTION_SKIP = "skip"
ACTION_ERROR = "error"


def init_db():
    data_path = os.getenv("APPDATA", "data")

    db_path = Path(data_path) / "hubspot-wefact.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS invoice_ids(invoice_id text, status text, PRIMARY KEY(invoice_id, status))"
    )
    return connection


def is_invoice_id_in_db(connection, invoice: Invoice):
    cursor = connection.cursor()
    cursor.execute(
        "SELECT invoice_id, status FROM invoice_ids WHERE invoice_id=? AND status=?",
        (invoice.number, invoice.status),
    )
    return cursor.fetchone() is not None


def determine_db_status(connection, invoice):
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
    connection.execute(
        "INSERT INTO invoice_ids(invoice_id, status) VALUES(?,?)",
        (invoice.number, invoice.status),
    )
    connection.commit()
