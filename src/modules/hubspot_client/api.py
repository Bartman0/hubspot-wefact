import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from hubspot import HubSpot
from hubspot.crm.associations import BatchInputPublicObjectId
from hubspot.crm.commerce.invoices import SimplePublicObjectInput as invoices_spoi
from hubspot.crm.objects.notes import SimplePublicObjectInputForCreate as notes_spoifc
from hubspot.crm.objects.tasks import SimplePublicObjectInputForCreate as tasks_spoifc
from urllib3 import Retry

from modules.models.company import Company
from modules.models.contact import Contact
from modules.models.invoice import Invoice
from modules.models.line_item import LineItem
from modules.state.db import INVOICE_STATUS_PAID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


INVOICES_BASE_PATH = Path(os.getenv("APPDATA", os.getenv("HOME", "/tmp"))) / "WeFactInvoices"
os.makedirs(INVOICES_BASE_PATH, exist_ok = True)


def get_access_token_hubspot():
    """Return the HubSpot private-app access token from the environment.

    Raises KeyError when HUBSPOT_ACCESS_TOKEN is not set.
    """
    return os.environ["HUBSPOT_ACCESS_TOKEN"]


def get_api_client():
    """Build a HubSpot client that retries server errors up to three times.

    Retries use an exponential backoff and only fire on 500, 502 and 504, so
    transient HubSpot outages do not abort a sync run.
    """
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(500, 502, 504),
    )
    api_client = HubSpot(access_token=get_access_token_hubspot(), retry=retry)
    return api_client


def upload_invoice(api_client, filename, data):
    """Write the PDF bytes to disk and upload them to the HubSpot /invoices folder.

    The file is first written to INVOICES_BASE_PATH because the HubSpot files
    API uploads from a path, not from memory. Existing files with the same name
    are overwritten and the upload is publicly indexable.

    Returns {"id": ..., "url": ...} for the uploaded file, both None when
    HubSpot returns an empty response.
    """
    file_path = INVOICES_BASE_PATH / filename
    with open(file_path, "wb") as file:
        file.write(data)
    options = json.dumps({"access": "PUBLIC_INDEXABLE", "overwrite": True})
    response = api_client.files.files_api.upload(
        file=file_path,
        file_name=filename,
        folder_path="/invoices",
        options=options
    )
    if response is None:
        return {"id": None, "url": None}
    return {"id": response.id, "url": response.url}


def associate_file_to_company(api_client, company_id, title, file_id):
    """Link an uploaded file to a company by creating a note that attaches it.

    HubSpot has no direct file-to-company association, so a note carrying the
    attachment id is used as the carrier.
    """
    return create_note(api_client, company_id, title, file_id)


def get_invoices(api_client: HubSpot, after):
    """Read one page of HubSpot invoices and map them onto Invoice models.

    after is the paging cursor from a previous call, or None for the first page.
    Only the properties the sync needs are requested, including the Dutch
    custom invoice fields (betreft, referentie, adres, ...). Line items are not
    loaded here; get_invoice_details does that.

    Returns (list of Invoice, next cursor) where the cursor is None on the last
    page.
    """
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
        "hs_total_discount",
        "hs_discount_percentage",
        "relatienummer_factuur"
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
                        relatienummer = invoice.properties.get("relatienummer_factuur")
                    )
        for invoice in invoices_hubspot.results]

    after = invoices_hubspot.paging.next.after if invoices_hubspot.paging else None

    return invoices, after


LINE_ITEM_PROPERTIES = [
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
    "hs_discount_percentage",
]


def _read_first_association_id(api_client, invoice_id, to_object_type):
    """Return the id of the first object associated with the invoice, or None on error."""
    batch_ids = BatchInputPublicObjectId([{"id": invoice_id}])
    associations = api_client.crm.associations.batch_api.read(
        from_object_type="invoice",
        to_object_type=to_object_type,
        batch_input_public_object_id=batch_ids,
    )
    associations_dict = associations.to_dict()
    if associations_dict.get("num_errors", -1) > 0:
        error_messages = [error['message'] for error in associations_dict['errors']]
        logger.error(f"{' - \n'.join(error_messages)}")
        return None
    return associations.results[0].to[0].id


def _fetch_company(api_companies, company_id):
    """Load one HubSpot company and map it onto a Company model.

    The raw HubSpot property dict is passed straight into the model, so keys
    that are not model fields are silently dropped. relatienummer is derived
    from relatie_nummer and falls back to the company id when that property is
    missing or empty, because WeFact needs a non-empty debtor code.
    """
    company_hubspot = api_companies.get_by_id(
        company_id=company_id, properties=["relatie_nummer", "name", "address", "zip", "city", "email", "mailadres_factuur", "land"]
    )
    logger.info(
        f"company {company_hubspot.properties['name']}[{company_hubspot.id}] was retrieved"
    )
    company_args = {key: company_hubspot.properties[key] for key in company_hubspot.properties.keys()}
    # voeg id toe
    company_args["id"] = company_id
    # overschrijf relatienummer: gebruik het company_id als het relatie_nummer niet gevonden kan worden of leeg is
    company_args["relatienummer"] = company_hubspot.properties.get("relatie_nummer", company_id) or company_id
    return Company(**company_args)


def _fetch_contact(api_contacts, contact_id):
    """Load one HubSpot contact and map it onto a Contact model.

    Only lastname and factuur_toelichting are requested; the contact is
    informational and is not sent to WeFact.
    """
    contact_hubspot = api_contacts.get_by_id(
        contact_id=contact_id, properties=["lastname", "factuur_toelichting"]
    )
    logger.info(
        f"contact {contact_hubspot.properties['lastname']}[{contact_hubspot.id}] was retrieved"
    )
    contact_args = {key: contact_hubspot.properties[key] for key in contact_hubspot.properties.keys()}
    return Contact(**contact_args)


def _build_line_item(line_item_args):
    """Coerce a raw HubSpot line-item property dict into a LineItem model.

    HubSpot returns every property as a string, so quantity, amount, price,
    btw and the discount fields are converted to numbers first. btw arrives as
    a fraction (0.21) and is scaled to a percentage (21.0), because WeFact
    expects TaxPercentage. When HubSpot supplies a discount amount rather than
    a percentage, the line percentage is computed from quantity * price and
    rounded to two decimals.
    """
    # fix types
    quantity = int(line_item_args["quantity"])
    line_item_args["quantity"] = quantity
    line_item_args["amount"] = float(line_item_args["amount"])
    price = float(line_item_args["price"])
    line_item_args["price"] = price
    line_item_args["btw"] = float((line_item_args.get("btw", 0)) or 0) * 100
    discount_amount = float(line_item_args.get("discount", 0) or 0)
    line_item_args["discount"] = discount_amount
    line_item_args["hs_discount_percentage"] = float(line_item_args.get("hs_discount_percentage", 0) or 0)
    # if discount amount is not 0, calculate the line item percentage ourselves
    if discount_amount != 0 and (quantity * price) != 0:
        line_item_args["hs_discount_percentage"] = round(discount_amount / (quantity * price) * 100, 2)
    return LineItem(**line_item_args)


def _fetch_line_items(api_client, api_line_items, invoice_id):
    """Load every line item associated with an invoice.

    Line items without an hs_sku are dropped, because the SKU is the product
    code WeFact keys its products on. Returns (line items, error messages);
    both are empty when the invoice has no associated line items.
    """
    line_items, errors = [], []
    batch_ids = BatchInputPublicObjectId([{"id": invoice_id}])
    invoice_line_items = api_client.crm.associations.batch_api.read(
        from_object_type="invoice",
        to_object_type="line_items",
        batch_input_public_object_id=batch_ids,
    )
    if len(invoice_line_items.results) == 0:
        return line_items, errors
    for line_item_ref in invoice_line_items.results[0].to:
        line_item = api_line_items.get_by_id(
            line_item_id=line_item_ref.id, properties=LINE_ITEM_PROPERTIES
        )
        line_item_args = {key: line_item.properties[key] for key in line_item.properties.keys()}
        if line_item_args.get("hs_sku") is not None:
            line_items.append(_build_line_item(line_item_args))
        else:
            message = "SKU is NOT set, skipping invoice line item"
            logger.error(message)
            errors.append(message)
    return line_items, errors


def get_invoice_details(api_client, invoice: Invoice):
    """Enrich an invoice with its associated company, contact and line items.

    The line items are appended to invoice.line_items in place; the company and
    contact are returned instead, and are None when the invoice has no such
    association or when HubSpot reported an association error.

    Returns (company, contact, errors), where a non-empty errors list means the
    invoice is not fit to be sent to WeFact.
    """
    api_companies = api_client.crm.companies.basic_api
    api_contacts = api_client.crm.contacts.basic_api
    api_line_items = api_client.crm.line_items.basic_api

    company_id = _read_first_association_id(api_client, invoice.id, "companies")
    company = _fetch_company(api_companies, company_id) if company_id is not None else None

    contact_id = _read_first_association_id(api_client, invoice.id, "contacts")
    contact = _fetch_contact(api_contacts, contact_id) if contact_id is not None else None

    line_items, errors = _fetch_line_items(api_client, api_line_items, invoice.id)
    invoice.line_items.extend(line_items)

    return company, contact, errors


def create_task(api_client, company_id, title, description):
    """Create a high-priority HubSpot task on a company so a human can fix data.

    Used when an invoice cannot be synced, for example because a line item has
    no SKU. The task is due one day from now and is associated to the company
    through the HubSpot-defined task-to-company association (type 192).
    """
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
    """Create a HubSpot note on a company with a file attached to it.

    title becomes the note body; file_id is the id returned by upload_invoice.
    The note is associated to the company through the HubSpot-defined
    note-to-company association (type 190).
    """
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



def set_invoice_to_paid(api_client, invoice):
    """Push a paid status from WeFact back onto the HubSpot invoice.

    Called for invoices this sync already created in WeFact, to carry the
    payment the other way: WeFact owns whether an invoice was settled, HubSpot
    needs to reflect it.

    Whether the invoice really is paid is decided by the caller: main.py looks
    the invoice up with get_invoice_status and only lands here once
    modules.wefact_client.invoice.invoice_is_paid confirmed it. This unconditionally sets
    hs_invoice_status to paid, updates invoice.status to match and returns the
    updated HubSpot object.
    """
    api_invoices = api_client.crm.commerce.invoices.basic_api
    update = invoices_spoi(properties={"hs_invoice_status": INVOICE_STATUS_PAID})
    response = api_invoices.update(invoice_id=invoice.id, simple_public_object_input=update)
    # also update the status of the invoice object
    invoice.status = INVOICE_STATUS_PAID
    logger.info(
        f"invoice {invoice.number}[{invoice.id}] was set to {INVOICE_STATUS_PAID} in HubSpot"
    )
    return response