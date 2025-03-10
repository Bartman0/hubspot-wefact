import datetime
import logging
import os
import sqlite3
from queue import Queue

from dotenv import load_dotenv
from hubspot import HubSpot
from hubspot.crm.associations import BatchInputPublicObjectId
from urllib3.util.retry import Retry

GROOTBOEKREKENING_DEBITEUREN = "1300"

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

queue = Queue()


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


def get_access_token_hubspot():
    return os.environ["ACCESS_TOKEN"]


def generate_wefact_invoice(
        invoice_number, company_relatienummer, company_name, amount_billed,
        invoice_date, due_date, period, line_items_details
):
    return None


def main():
    with init_db() as connection:
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=(500, 502, 504),
        )
        api_client = HubSpot(retry=retry)
        api_client.access_token = get_access_token_hubspot()

        api_invoices = api_client.crm.invoices.basic_api

        api_line_items = api_client.crm.line_items.basic_api
        api_companies = api_client.crm.companies.basic_api

        after = None
        while True:
            invoices_details = api_invoices.get_crm_v3_objects_invoices(
                limit=5,
                after=after,
                properties=[
                    "hs_invoice_status",
                    "hs_amount_billed",
                    "hs_balance_due",
                    "hs_invoice_date",
                    "hs_due_date",
                    "hs_number",
                ]
            )


            for invoice in invoices_details.results:
                invoice_status = invoice.properties["hs_invoice_status"]
                invoice_number = invoice.properties["hs_number"]
                logger.info(
                    f"retrieved invoice {invoice_number}[{invoice.id}] with status {invoice_status}"
                )
                if invoice_status != "open":
                    logger.warning(
                        f"skipping invoice {invoice_number}[{invoice.id}] with status {invoice_status}"
                    )
                    continue

                if is_invoice_id_in_db(connection, invoice.id):
                    logger.info(
                        f"invoice already processed, skipping invoice {invoice_number}[{invoice.id}]"
                    )
                    continue

                amount_billed = invoice.properties["hs_amount_billed"]
                invoice_date = datetime.datetime.fromisoformat(
                    str(invoice.properties["hs_invoice_date"])
                ).strftime("%Y-%m-%d")
                due_date = datetime.datetime.fromisoformat(
                    str(invoice.properties["hs_due_date"])
                ).strftime("%Y-%m-%d")
                period = datetime.datetime.fromisoformat(
                    str(invoice.properties["hs_invoice_date"])
                ).strftime("%Y/%m")

                batch_ids = BatchInputPublicObjectId([{"id": invoice.id}])
                invoice_companies = api_client.crm.associations.batch_api.read(
                    from_object_type="invoice",
                    to_object_type="companies",
                    batch_input_public_object_id=batch_ids,
                )
                invoice_companies_dict = invoice_companies.to_dict()
                if invoice_companies_dict.get("num_errors", -1) > 0:
                    logger.error(f"{invoice_companies_dict['errors'][0]['message']}")
                    continue
                company_id = invoice_companies.results[0].to[0].id
                company = api_companies.get_by_id(
                    company_id=company_id, properties=["relatie_nummer", "name"]
                )
                logger.info(
                    f"company {company.properties['name']}[{company.id}] was retrieved"
                )
                if "relatie_nummer" not in company.properties:
                    logging.error(f"{company.name} does not have a relation number")
                    continue
                company_relatienummer = company.properties["relatie_nummer"]
                company_name = company.properties["name"]

                invoice_line_items = api_client.crm.associations.batch_api.read(
                    from_object_type="invoice",
                    to_object_type="line_items",
                    batch_input_public_object_id=batch_ids,
                )

                line_items_details=[]
                for line_item in invoice_line_items.results[0].to:
                    line_item = api_line_items.get_by_id(
                        line_item_id=line_item.id,
                        properties=[
                            "hs_sku",
                            "amount",
                            "quantity",
                            "voorraadnummer",
                            "name",
                            "kostenplaats",
                            "grootboek",
                            "gewicht",
                            "artikelsoort",
                            "artikelgroep",
                        ],
                    )
                    line_items_details.append({key: line_item.properties[key] for key in line_item.properties.keys()})
                logger.debug(f"line items details: {line_items_details}")

                result = generate_wefact_invoice(invoice_number, company_relatienummer, company_name, amount_billed,
                                                 invoice_date, due_date, period, line_items_details)
                if result.errors > 0:
                    logger.error("HubSpot invoice not saved in progress database")
                    continue
                else:
                    save_invoice_id_in_db(connection, invoice.id)

            after = invoices_details.paging.next.after if invoices_details.paging else None
            if not after:
                break

if __name__ == "__main__":
    main()
