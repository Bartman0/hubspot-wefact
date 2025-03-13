import logging

from dotenv import load_dotenv

from hubspot_api.api import get_api_client, get_invoices, get_invoice_details, get_taxes
from state.db import init_db, is_invoice_id_in_db, save_invoice_id_in_db
from wefact.invoice import generate_wefact_invoice

GROOTBOEKREKENING_DEBITEUREN = "1300"

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def main():
    with (init_db() as connection):
        tax_rates = get_taxes()
        api_client = get_api_client()
        next_invoice = None
        while True:
            invoices = get_invoices(api_client, next_invoice)
            for invoice in invoices.results:
                (invoice_number, invoice_status, company_relatienummer, company_name, due_date, invoice_date, amount_billed,
                 line_items_details, next_invoice) = get_invoice_details(api_client, invoices, invoice)

                if invoice_status != "open" or company_relatienummer is None:
                    logger.warning(
                        f"skipping invoice {invoice_number}[{invoice.id}] with status {invoice_status}"
                    )
                    continue
                if is_invoice_id_in_db(connection, invoice.id, invoice_status):
                    logger.info(
                        f"invoice already processed, skipping invoice {invoice_number}[{invoice.id}]"
                    )
                    continue
                logger.debug(f"line items details: {line_items_details}")

                result = generate_wefact_invoice(invoice_number, company_relatienummer, company_name, amount_billed,
                                                 invoice_date, due_date, tax_rates, line_items_details)
                if len(result.errors) > 0:
                    logger.error(f"HubSpot invoice {invoice_number}[{invoice.id}] with status {invoice_status} not saved in state database")
                    continue
                save_invoice_id_in_db(connection, invoice.id, invoice_status)

            if not next_invoice:
                break


if __name__ == "__main__":
    main()
