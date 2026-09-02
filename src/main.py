import logging

from dotenv import load_dotenv

from modules.hubspot_client.api import get_api_client, get_invoices, get_invoice_details, create_task, upload_invoice, \
    associate_file_to_company, set_invoice_status
from modules.state.db import init_db, save_invoice_id_in_db, determine_db_status, INVOICE_STATUS_OPEN, INVOICE_STATUS_PAID, \
    INVOICE_STATUS_VOIDED, INVOICE_STATUS_UNKNOWN, ACTION_OPEN, ACTION_PAID, ACTION_PROCESSED, ACTION_SKIP
from modules.wefact_client.invoice import generate_invoice, get_invoice_status, wefact_invoice_status, \
    WEFACT_STATUS_BETAALD, WEFACT_STATUS_VERVALLEN

load_dotenv()

#: How a WeFact status translates to the HubSpot invoice status written back by
#: set_invoice_status. main.py is the only module that knows both vocabularies:
#: hubspot_client does not learn WeFact's numbers and wefact_client does not
#: learn HubSpot's strings. A WeFact status that is absent here is left alone.
WEFACT_STATUS_TO_HUBSPOT = {
    WEFACT_STATUS_BETAALD: INVOICE_STATUS_PAID,
    WEFACT_STATUS_VERVALLEN: INVOICE_STATUS_VOIDED,
}

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
    number (open, paid, voided or unknown); invoice.status is the current HubSpot
    status.

    Returns one of:

    - ACTION_OPEN: never synced, so create the invoice in WeFact.
    - ACTION_PROCESSED: created by an earlier run and still open on both sides,
      so ask WeFact what has happened to it since and carry that back to HubSpot
      through WEFACT_STATUS_TO_HUBSPOT.
    - ACTION_PAID: HubSpot reports paid while the database still has open,
      which happens when someone marks an invoice paid in HubSpot by hand.
      process_batch_of_invoices handles this alongside ACTION_SKIP, so it is a
      no-op; see "The paid/open no-op" in the README.
    - ACTION_SKIP: nothing to do, either because the invoice is settled on both
      sides or because HubSpot reports a status we do not sync (draft, voided).

    Raises ValueError when the two statuses cannot occur together, which means
    an invoice regressed from paid back to open. Nothing catches it, so it ends
    the run.
    """
    invoice_status = invoice.status
    # a voided invoice is final: whatever HubSpot reports now, there is nothing
    # left to sync. Without this the pairwise checks below fall through to the
    # ValueError for an invoice voided here and since reopened or paid in
    # HubSpot, which would end the whole run over one stale invoice.
    if db_status == INVOICE_STATUS_VOIDED:
        return ACTION_SKIP
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

    For every invoice on the page: look up what has already been processed and
    decide the action. An invoice that needs creating has its company, contact
    and line items read from HubSpot first, is then built in WeFact and gets its
    PDF attached back onto the company. An invoice an earlier run already created
    is looked up in WeFact instead, and a status found there is written back onto
    the HubSpot invoice. Successfully handled invoices are recorded in the
    state database so a rerun skips them. Invoices whose HubSpot details are
    incomplete get a HubSpot task instead.

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
            hubspot_status = WEFACT_STATUS_TO_HUBSPOT.get(wefact_invoice_status(result))
            if hubspot_status is not None:
                set_invoice_status(api_client, invoice, hubspot_status)
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
