import sqlite3


def init_db():
    connection = sqlite3.connect("/tmp/hubspot-wefact.db")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS invoice_ids(invoice_id text PRIMARY KEY)"
    )
    return connection


def is_invoice_id_in_db(connection, invoice_id):
    cursor = connection.cursor()
    cursor.execute(
        "SELECT invoice_id FROM invoice_ids WHERE invoice_id=?", (invoice_id,)
    )
    return cursor.fetchone() is not None


def save_invoice_id_in_db(connection, invoice_id):
    connection.execute("INSERT INTO invoice_ids(invoice_id) VALUES(?)", (invoice_id,))
    connection.commit()
