import logging

from dotenv import load_dotenv

from modules.hubspot_client.api import get_api_client, get_invoices, get_invoice_details, create_task, upload_invoice, \
    associate_file_to_company, set_invoice_to_paid
from modules.state.db import init_db, save_invoice_id_in_db, determine_db_status, INVOICE_STATUS_OPEN, INVOICE_STATUS_PAID, \
    INVOICE_STATUS_UNKNOWN, ACTION_OPEN, ACTION_PAID, ACTION_PROCESSED, ACTION_SKIP
from modules.wefact_client.invoice import generate_invoice, get_invoice_status, invoice_is_paid

load_dotenv()

logging.basicConfig(level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S", force=True
)
logger = logging.getLogger(__name__)


def main():
    """Entry point: walk every page of HubSpot invoices and sync them to WeFact.

    Opens (and creates, if needed) the local state database, builds a HubSpot
    API client and then keeps calling process_batch_of_invoices until HubSpot
    stops handing back a paging cursor.
    """
    with (init_db() as connection):
        api_client = get_api_client()
        next_invoice = None
        while True:
            next_invoice = process_batch_of_invoices(api_client, connection, next_invoice)
            if not next_invoice:
                break


def _determine_action(db_status, invoice):
    """Decide what to do with one invoice by comparing HubSpot and state db status.

    db_status is what the state database has already recorded for this invoice
    number (open, paid or unknown); invoice.status is the current HubSpot status.
    Returns one of ACTION_PROCESSED (nothing left to do), ACTION_PAID (mark the
    existing WeFact invoice as paid), ACTION_OPEN (create the invoice in WeFact)
    or ACTION_SKIP (a HubSpot status we do not sync, e.g. draft or voided).

    Raises ValueError when the two statuses cannot occur together, which means
    an invoice regressed from paid back to open.
    """
    invoice_status = invoice.status
    # if the status of the invoice equals the db status, we already processed this phase
    if invoice_status == INVOICE_STATUS_OPEN and db_status == INVOICE_STATUS_OPEN:
        return ACTION_PROCESSED
    if invoice_status == INVOICE_STATUS_PAID and db_status == INVOICE_STATUS_OPEN:
        return ACTION_PAID
    if invoice_status == INVOICE_STATUS_PAID and db_status == INVOICE_STATUS_PAID:
        return ACTION_SKIP
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
    """Sync one HubSpot page of invoices to WeFact and return the next paging cursor.

    For every invoice on the page: look up what has already been processed,
    decide the action, fetch the associated company, contact and line items,
    and then either create the invoice in WeFact or mark it paid. Successfully
    handled invoices are recorded in the state database so a rerun skips them.
    Invoices whose HubSpot details are incomplete get a HubSpot task instead.

    next_invoice is the "after" cursor from the previous call (None for the
    first page); the return value is the cursor for the following page, or None
    when this was the last page.
    """
    invoices, next_invoice = get_invoices(api_client, next_invoice)
    for invoice in invoices:
        # verwerk alleen facturen met PAID of OPEN status
        db_status = determine_db_status(connection, invoice)
        action = _determine_action(db_status, invoice)
        if action == ACTION_SKIP or action == ACTION_PAID:
            logger.debug(f"skipping invoice {invoice.number}[{invoice.id}], status '{invoice.status}'")
            continue
        if action == ACTION_PROCESSED:
            logger.info(f"invoice already processed, getting paid status for invoice {invoice.number}[{invoice.id}]")
            result = get_invoice_status(invoice.number)
            if len(result.errors) > 0:
                logger.error(
                    f"invoice {invoice.number}[{invoice.id}] with status {invoice.status} could not be retrieved from WeFact")
                logger.error(f"error: {result.errors}")
                continue
            if invoice_is_paid(result):
                set_invoice_to_paid(api_client, invoice)
                save_invoice_id_in_db(connection, invoice)
            continue
        # from here on only invoices that need to be created remain
        # first we get the invoice details, which are saved in the invoice object
        (company, contact, errors) = get_invoice_details(api_client, invoice)
        if len(errors) > 0:
            logger.error(f"invoice contains errors {errors}, skipping invoice {invoice.number}[{invoice.id}]")
            if company is None:
                logger.error("creating a task linked to a company can not be done: the company is not known")
            else:
                create_task(api_client, company.id, "errors to be fixed", f"invoice details for {invoice.number} contain errors: {errors}")
            continue
        # verwerk alleen facturen met OPEN status
        # we kunnen dit pas doen nadat de details van de invoice zijn opgehaald met get_invoice_details()
        if action == ACTION_OPEN:
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
    """Upload the WeFact invoice PDF to HubSpot and attach it to the company.

    The file is stored in the HubSpot /invoices folder as "<invoice number>.pdf"
    and then linked to the company through a note carrying the attachment.
    """
    filename = f"{invoice.number}.pdf"
    result = upload_invoice(api_client, filename, pdf_data)
    associate_file_to_company(api_client, company.id, f"{filename} {result['url']}", result["id"])


if __name__ == "__main__":
    main()
