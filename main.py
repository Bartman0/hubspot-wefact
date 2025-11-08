import logging

from dotenv import load_dotenv

from hubspot_api.api import get_api_client, get_invoices, get_invoice_details, create_task, upload_invoice, \
    associate_file_to_company
from state.db import init_db, is_invoice_id_in_db, save_invoice_id_in_db
from wefact_api.invoice import generate_invoice, invoice_update_paid

INVOICE_STATUS_OPEN = "open"
INVOICE_STATUS_PAID = "paid"

GROOTBOEKREKENING_DEBITEUREN = "1300"

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def main():
    with (init_db() as connection):
        api_client = get_api_client()
        next_invoice = None
        while True:
            next_invoice = process_batch_of_invoices(api_client, connection, next_invoice)
            if not next_invoice:
                break


def process_batch_of_invoices(api_client, connection, next_invoice):
    invoices, next_invoice = get_invoices(api_client, next_invoice)
    for invoice in invoices:
        if is_invoice_id_in_db(connection, invoice):
            logger.info(
                f"invoice already processed, skipping invoice {invoice.number}[{invoice.id}]"
            )
            continue
        (company, contact, errors) = get_invoice_details(api_client, invoice)
        if len(errors) > 0:
            logger.error(
                f"invoice contains errors {errors}, skipping invoice {invoice.number}[{invoice.id}]"
            )
            create_task(api_client, company.id, "errors to be fixed", f"invoice details for {invoice.number} contain errors: {errors}")
            continue
        # kopieer toelichting op contact naar invoice
        invoice.toelichting = contact.factuur_toelichting
        # verwerk alleen facturen met PAID of OPEN status
        if invoice.status == INVOICE_STATUS_PAID:
            result = invoice_update_paid(invoice.number)
        elif invoice.status == INVOICE_STATUS_OPEN:
            result = generate_invoice(invoice, company, contact)
        else:
            continue
        if len(result.errors) > 0:
            logger.error(
                f"HubSpot invoice {invoice.number}[{invoice.id}] with status {invoice.status} not saved in state database")
            logger.error(f"error: {result.errors}")
            continue
        pdf_data = result.data["pdf"]
        save_invoice_pdf(api_client, company, invoice, pdf_data)
        save_invoice_id_in_db(connection, invoice)
    return next_invoice


def save_invoice_pdf(api_client, company, invoice, pdf_data):
    filename = f"{invoice.number}.pdf"
    result = upload_invoice(api_client, filename, pdf_data)
    associate_file_to_company(api_client, company.id, f"{filename} {result["url"]}", result["id"])


if __name__ == "__main__":
    main()
