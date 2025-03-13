import logging

import os
import datetime
import requests

from hubspot.crm.associations import BatchInputPublicObjectId
from urllib3 import Retry
from hubspot import HubSpot


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def get_access_token_hubspot():
    return os.environ["HUBSPOT_ACCESS_TOKEN"]


def get_api_client():
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(500, 502, 504),
    )
    api_client = HubSpot(retry=retry)
    api_client.access_token = get_access_token_hubspot()
    return api_client


def get_taxes():
    endpoint = "https://api.hubapi.com/tax-rates/v1/tax-rates"
    headers = {"Authorization": "Bearer " +str(os.environ["HUBSPOT_ACCESS_TOKEN"])}
    response = requests.get(endpoint, headers=headers)
    return {tax["id"]: {"name": tax["name"], "percentageRate": tax["percentageRate"], "id": tax["id"], "label": tax["label"]}
            for tax in response.json()["results"]}


def get_invoices(api_client, after):
    api_invoices = api_client.crm.invoices.basic_api
    invoices = api_invoices.get_crm_v3_objects_invoices(
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
    return invoices


def get_invoice_details(api_client, invoices, invoice):
    api_companies = api_client.crm.companies.basic_api
    api_line_items = api_client.crm.line_items.basic_api

    invoice_status = invoice.properties["hs_invoice_status"]
    invoice_number = invoice.properties["hs_number"]
    logger.info(
        f"retrieved invoice {invoice_number}[{invoice.id}] with status {invoice_status}"
    )

    amount_billed = invoice.properties["hs_amount_billed"]
    invoice_date = datetime.datetime.fromisoformat(
        str(invoice.properties["hs_invoice_date"])
    )
    due_date = datetime.datetime.fromisoformat(
        str(invoice.properties["hs_due_date"])
    )

    batch_ids = BatchInputPublicObjectId([{"id": invoice.id}])
    invoice_companies = api_client.crm.associations.batch_api.read(
        from_object_type="invoice",
        to_object_type="companies",
        batch_input_public_object_id=batch_ids,
    )
    invoice_companies_dict = invoice_companies.to_dict()
    if invoice_companies_dict.get("num_errors", -1) > 0:
        logger.error(f"{invoice_companies_dict['errors'][0]['message']}")
        company_relatienummer = None
        company_name = None
    else:
        company_id = invoice_companies.results[0].to[0].id
        company = api_companies.get_by_id(
            company_id=company_id, properties=["relatie_nummer", "name"]
        )
        logger.info(
            f"company {company.properties['name']}[{company.id}] was retrieved"
        )
        company_relatienummer = company.properties["relatie_nummer"] if "relatie_nummer" in company.properties else None
        company_name = company.properties["name"]

    invoice_line_items = api_client.crm.associations.batch_api.read(
        from_object_type="invoice",
        to_object_type="line_items",
        batch_input_public_object_id=batch_ids,
    )

    line_items_details = []
    if len(invoice_line_items.results) > 0:
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
                    "hs_tax_rate_group_id"
                ],
            )
            details = {key: line_item.properties[key] for key in line_item.properties.keys()}
            details["quantity"] = int(details["quantity"])
            details["amount"] = float(details["amount"])
            line_items_details.append(details)

    after = invoices.paging.next.after if invoices.paging else None

    return (invoice_number, invoice_status, company_relatienummer, company_name, due_date, invoice_date, amount_billed,
                 line_items_details, after)
