import sqlite3
from models.invoice import Invoice


def init_db():
    connection = sqlite3.connect("/tmp/hubspot-wefact.db")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS invoice_ids(invoice_id text, status text, PRIMARY KEY(invoice_id, status))"
    )
    return connection


def is_invoice_id_in_db(connection, invoice: Invoice):
    cursor = connection.cursor()
    cursor.execute(
        "SELECT invoice_id, status FROM invoice_ids WHERE invoice_id=? AND status=?", (invoice.number, invoice.status)
    )
    return cursor.fetchone() is not None


def save_invoice_id_in_db(connection, invoice: Invoice):
    connection.execute("INSERT INTO invoice_ids(invoice_id, status) VALUES(?,?)", (invoice.number, invoice.status))
    connection.commit()
