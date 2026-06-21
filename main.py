import logging

from dotenv import load_dotenv

from hubspot_api.api import get_api_client, get_invoices, get_invoice_details, create_task, upload_invoice, \
    associate_file_to_company
from state.db import init_db, save_invoice_id_in_db, determine_db_status, INVOICE_STATUS_OPEN, INVOICE_STATUS_PAID, \
    INVOICE_STATUS_UNKNOWN, ACTION_OPEN, ACTION_PAID, ACTION_PROCESSED, ACTION_SKIP
from wefact_api.invoice import generate_invoice, invoice_update_paid

GROOTBOEKREKENING_DEBITEUREN = "1300"

load_dotenv()

logging.basicConfig(level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S", force=True
)
logger = logging.getLogger(__name__)


def main():
    with (init_db() as connection):
        api_client = get_api_client()
        next_invoice = None
        while True:
            next_invoice = process_batch_of_invoices(api_client, connection, next_invoice)
            if not next_invoice:
                break


def _determine_action(db_status, invoice):
    invoice_status = invoice.status
    # if the status of the invoice equals the db status, we already processed this phase
    if invoice_status == db_status:
        return ACTION_PROCESSED
    if invoice_status == INVOICE_STATUS_PAID and db_status == INVOICE_STATUS_OPEN:
        return ACTION_PAID
    if invoice_status == INVOICE_STATUS_OPEN and db_status == INVOICE_STATUS_UNKNOWN:
        return ACTION_OPEN
    # if the status of the invoice is PAID and the db status is unknown, treat is as an OPEN invoice
    if invoice_status == INVOICE_STATUS_PAID and db_status == INVOICE_STATUS_UNKNOWN:
        return ACTION_OPEN
    if invoice_status not in [INVOICE_STATUS_OPEN, INVOICE_STATUS_PAID]:
        # some status in the invoice we won't process anyway
        return ACTION_SKIP
    raise ValueError("error in processing invoice and db statuses")


def process_batch_of_invoices(api_client, connection, next_invoice):
    invoices, next_invoice = get_invoices(api_client, next_invoice)
    for invoice in invoices:
        # verwerk alleen facturen met PAID of OPEN status
        db_status = determine_db_status(connection, invoice)
        action = _determine_action(db_status, invoice)
        if action == ACTION_SKIP:
            logger.debug(f"skipping invoice {invoice.number}[{invoice.id}]")
            continue
        if action == ACTION_PROCESSED:
            logger.info(f"invoice already processed, skipping invoice {invoice.number}[{invoice.id}]")
            continue
        (company, contact, errors) = get_invoice_details(api_client, invoice)
        if len(errors) > 0:
            logger.error(f"invoice contains errors {errors}, skipping invoice {invoice.number}[{invoice.id}]")
            create_task(api_client, company.id, "errors to be fixed", f"invoice details for {invoice.number} contain errors: {errors}")
            continue
        # verwerk alleen facturen met PAID of OPEN status
        if action == INVOICE_STATUS_PAID:
            result = invoice_update_paid(invoice.number)
        elif action == INVOICE_STATUS_OPEN:
            result = generate_invoice(invoice, company)
        else:
            # continue with any other status
            logger.info(
                f"invoice has a status we do not know about, skipping invoice {invoice.number}[{invoice.id}]"
            )
            continue
        if result.persist:
            save_invoice_id_in_db(connection, invoice)
            logger.info(f"HubSpot invoice {invoice.number}[{invoice.id}] with status {invoice.status} just saved in state database")
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
    associate_file_to_company(api_client, company.id, f"{filename} {result['url']}", result["id"])


if __name__ == "__main__":
    main()
