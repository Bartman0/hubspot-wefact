import json
import logging
import os
from datetime import datetime, timedelta

import requests
from hubspot import HubSpot
from hubspot.crm.associations import BatchInputPublicObjectId
from hubspot.crm.objects.notes import SimplePublicObjectInputForCreate as notes_spoifc
from hubspot.crm.objects.tasks import SimplePublicObjectInputForCreate as tasks_spoifc
from urllib3 import Retry

from models.company import Company
from models.contact import Contact
from models.invoice import Invoice
from models.line_item import LineItem

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
    api_client = HubSpot(access_token=get_access_token_hubspot(), retry=retry)
    return api_client


def get_taxes(api_client):
    endpoint = "https://api.hubapi.com/tax-rates/v1/tax-rates"
    headers = {"Authorization": "Bearer " + str(os.environ["HUBSPOT_ACCESS_TOKEN"])}
    response = requests.get(endpoint, headers=headers)
    return {tax["id"]: {"name": tax["name"], "percentageRate": tax["percentageRate"], "id": tax["id"],
                        "label": tax["label"]}
            for tax in response.json()["results"]}


def upload_invoice(api_client, filename, data):
    with open(filename, "wb") as file:
        file.write(data)
    options = json.dumps({"access": "PUBLIC_INDEXABLE", "overwrite": True})
    response = api_client.files.files_api.upload(
        file=filename,
        file_name=filename,
        folder_path="/invoices",
        options=options
    )
    if response is None:
        return {"id": None, "url": None}
    return {"id": response.id, "url": response.url}


def associate_file_to_company(api_client, company_id, title, file_id):
    return create_note(api_client, company_id, title, file_id)


def get_invoices(api_client: HubSpot, after):
    api_invoices = api_client.crm.commerce.invoices.basic_api
    properties = [
        "hs_invoice_status",
        "hs_amount_billed",
        "hs_balance_due",
        "hs_invoice_date",
        "hs_due_date",
        "hs_number",
        "betreft_factuurniveau",
        "referentie_wefact__factuur_",
        "organisatie__factuur_",
        "ter_attentie_van__factuur_",
        "adres__factuur_",
        "postcode__factuur_",
        "plaats__factuur_",
        "land__factuur_",
        "hs_total_discount"
        "hs_discount_percentage"
    ]

    invoices_hubspot = api_invoices.get_page(after=after, properties=properties)
    for invoice in invoices_hubspot.results:
        logger.info(
            f"invoice {invoice.properties['hs_number']}[{invoice.id}] was retrieved"
        )
    invoices = [Invoice(id=invoice.id,
                        number=invoice.properties["hs_number"],
                        status=invoice.properties["hs_invoice_status"],
                        amount_billed=invoice.properties["hs_amount_billed"],
                        invoice_date=datetime.fromisoformat(
                            str(invoice.properties["hs_invoice_date"])
                        ).date(),
                        due_date=datetime.fromisoformat(
                            str(invoice.properties["hs_due_date"])
                        ).date(),
                        betreft = invoice.properties.get("betreft_factuurniveau"),
                        referentie = invoice.properties.get("referentie_wefact__factuur_"),
                        organisatie = invoice.properties.get("organisatie__factuur_"),
                        ter_attentie_van = invoice.properties.get("ter_attentie_van__factuur_"),
                        adres = invoice.properties.get("adres__factuur_"),
                        postcode = invoice.properties.get("postcode__factuur_"),
                        plaats = invoice.properties.get("plaats__factuur_"),
                        land = invoice.properties.get("land__factuur_"),
                        korting = invoice.properties.get("hs_total_discount", 0.0),
                    )
        for invoice in invoices_hubspot.results]

    after = invoices_hubspot.paging.next.after if invoices_hubspot.paging else None

    return invoices, after


def get_invoice_details(api_client, invoice: Invoice):
    errors = []
    api_companies = api_client.crm.companies.basic_api
    api_contacts = api_client.crm.contacts.basic_api
    api_line_items = api_client.crm.line_items.basic_api

    batch_ids = BatchInputPublicObjectId([{"id": invoice.id}])
    invoice_companies = api_client.crm.associations.batch_api.read(
        from_object_type="invoice",
        to_object_type="companies",
        batch_input_public_object_id=batch_ids,
    )
    invoice_companies_dict = invoice_companies.to_dict()
    if invoice_companies_dict.get("num_errors", -1) > 0:
        error_messages = [error['message'] for error in invoice_companies_dict['errors']]
        logger.error(f"{' - \n'.join(error_messages)}")
        company = None
    else:
        company_id = invoice_companies.results[0].to[0].id
        company_hubspot = api_companies.get_by_id(
            company_id=company_id, properties=["relatie_nummer", "name", "address", "zip", "city", "email"]
        )
        logger.info(
            f"company {company_hubspot.properties['name']}[{company_hubspot.id}] was retrieved"
        )
        company_args = {key: company_hubspot.properties[key] for key in company_hubspot.properties.keys()}
        # voeg id toe
        company_args["id"] = company_id
        # overschrijf relatienummer: gebruik het company_id als het relatie_nummer niet gevonden kan worden of leeg is
        company_args["relatienummer"] = company_hubspot.properties.get("relatie_nummer", company_id) or company_id
        company = Company(**company_args)

    invoice_contacts = api_client.crm.associations.batch_api.read(
        from_object_type="invoice",
        to_object_type="contacts",
        batch_input_public_object_id=batch_ids,
    )
    invoice_contacts_dict = invoice_contacts.to_dict()
    if invoice_contacts_dict.get("num_errors", -1) > 0:
        error_messages = [error['message'] for error in invoice_contacts_dict['errors']]
        logger.error(f"{' - \n'.join(error_messages)}")
        contact = None
    else:
        contact_id = invoice_contacts.results[0].to[0].id
        contact_hubspot = api_contacts.get_by_id(
            contact_id=contact_id, properties=["lastname", "factuur_toelichting"]
        )
        logger.info(
            f"contact {contact_hubspot.properties['lastname']}[{contact_hubspot.id}] was retrieved"
        )
        contact_args = {key: contact_hubspot.properties[key] for key in contact_hubspot.properties.keys()}
        # voeg id toe
        contact = Contact(**contact_args)

    invoice_line_items = api_client.crm.associations.batch_api.read(
        from_object_type="invoice",
        to_object_type="line_items",
        batch_input_public_object_id=batch_ids,
    )

    if len(invoice_line_items.results) > 0:
        for line_item in invoice_line_items.results[0].to:
            line_item = api_line_items.get_by_id(
                line_item_id=line_item.id,
                properties=[
                    "hs_sku",
                    "amount",
                    "quantity",
                    "price",
                    "voorraadnummer",
                    "name",
                    "kostenplaats",
                    "grootboek",
                    "gewicht",
                    "artikelsoort",
                    "artikelgroep",
                    "hs_tax_rate_group_id",
                    "btw",
                    "discount",
                    "hs_discount_percentage"
                ],
            )
            line_item_args = {key: line_item.properties[key] for key in line_item.properties.keys()}
            # fix types
            quantity = int(line_item_args["quantity"])
            line_item_args["quantity"] = quantity
            amount = float(line_item_args["amount"])
            line_item_args["amount"] = amount
            price = float(line_item_args["price"])
            line_item_args["price"] = price
            line_item_args["btw"] = float((line_item_args.get("btw", 0)) or 0) * 100
            discount_amount = float(line_item_args.get("discount", 0) or 0)
            line_item_args["discount"] = discount_amount
            line_item_args["hs_discount_percentage"] = float(line_item_args.get("hs_discount_percentage", 0) or 0)
            # if discount amount is not 0, calculate the line item percentage ourselves
            if discount_amount != 0:
                discount_percentage = round(discount_amount/(quantity*price)*100, 2)
                line_item_args["hs_discount_percentage"] = discount_percentage
            if "hs_sku" in line_item_args and line_item_args["hs_sku"] is not None:
                invoice.line_items.append(LineItem(**line_item_args))
            else:
                message = "SKU is NOT set, skipping invoice line item"
                logger.error(message)
                errors.append(message)
    return company, contact, errors


def create_task(api_client, company_id, title, description):
    api_tasks = api_client.crm.objects.tasks.basic_api
    task = tasks_spoifc(properties={
        "hs_task_subject": title,
        "hs_task_body": description,
        "hs_task_status": "WAITING",
        "hs_task_priority": "HIGH",
        "hs_timestamp": int((datetime.now() + timedelta(days=1)).timestamp() * 1000)
    }, associations=[
        {"types": [
            {
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 192
            }
        ],
            "to": {"id": company_id}}
    ])
    response = api_tasks.create(task)
    return response


def create_note(api_client, company_id, title, file_id):
    api_notes = api_client.crm.objects.notes.basic_api
    note = notes_spoifc(properties={
        "hs_attachment_ids": f"{file_id}",
        "hs_note_body": title,
        "hs_timestamp": int(datetime.now().timestamp() * 1000)
    }, associations=[
        {"types": [
            {
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": 190
            }
        ],
            "to": {"id": company_id}}
    ])
    response = api_notes.create(note)
    return response
