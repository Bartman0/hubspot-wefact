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
            invoices, next_invoice = get_invoices(api_client, next_invoice)
            for invoice in invoices:
                (invoice, company) = get_invoice_details(api_client, invoice)

                if is_invoice_id_in_db(connection, invoice):
                    logger.info(
                        f"invoice already processed, skipping invoice {invoice.number}[{invoice.id}]"
                    )
                    continue
                if invoice.status == INVOICE_STATUS_PAID:
                    result = invoice_update_paid(invoice.number)
                else:
                    if invoice.status != INVOICE_STATUS_OPEN or company.relatienummer is None:
                        logger.warning(
                            f"skipping invoice {invoice.number}[{invoice.id}] with status {invoice.status}, company relation nr {company.relatienummer}"
                        )
                        create_task(api_client, company_id,
                                    f"company relatienummer {company.relatienummer} voor factuur {invoice.number} is niet gevuld",
                                    f"het relatienummer voor de company op factuur {invoice.number}[{invoice.id}] moet nog gezet worden.")
                        continue
                    result = generate_invoice(invoice, company)
                if len(result.errors) > 0:
                    logger.error(f"HubSpot invoice {invoice.number}[{invoice.id}] with status {invoice.status} not saved in state database")
                    logger.error(f"error: {result.errors}")
                    continue
                filename = f"{invoice.number}.pdf"
                result = upload_invoice(api_client, filename, result.data["pdf"])
                associate_file_to_company(api_client, company.id, f"{filename} {result["url"]}", result["id"])
                save_invoice_id_in_db(connection, invoice)

            if not next_invoice:
                break


if __name__ == "__main__":
    main()
