import base64
from collections import namedtuple
from enum import IntEnum

from modules.hubspot_client.api import logger
from modules.models.company import Company
from modules.models.invoice import Invoice
from modules.models.line_item import LineItem
from modules.wefact_client.api import InvoiceClient, DebtorClient, ProductClient
from modules.wefact_client.debtor import debtor_data_id_from_model, debtor_data_add_from_model, debtor_data_edit_from_model
from modules.wefact_client.product import product_data_add_from_model, product_data_edit_from_model, product_data_id_from_model

WEFACT_STATUS_SUCCESS = "success"
WEFACT_STATUS_ERROR = "error"

WEFACT_STATUS_BETAALD = 4
WEFACT_STATUS_VERVALLEN = 9

#: Outcome of a WeFact operation. persist tells main.py whether to record the
#: invoice in the state database, data carries results such as the PDF bytes,
#: and errors holds messages that block the sync.
ResultType = namedtuple("result", ["persist", "data", "errors"], defaults=[False, {}, []])


class InvoiceStatus(IntEnum):
    """WeFact's numeric invoice statuses, as used in the Status field."""

    Concept = 0
    Verzonden = 2
    Deels_betaald = 3
    Betaald = 4
    Creditfactuur = 8
    Vervallen = 9


def invoice_data_id(code):
    """Return the WeFact payload that identifies an invoice by its invoice code."""
    return {"InvoiceCode": code}


def invoice_data_id_from_model(invoice: Invoice):
    """Identify the WeFact invoice for an Invoice; the HubSpot number is the invoice code."""
    return invoice_data_id(invoice.number)


def invoice_data(code, debtor, invoice_date, term, discount, invoice_lines, custom_fields, country):
    """Return the WeFact payload for creating an invoice.

    The invoice is created as Verzonden (sent) rather than as a concept. term is
    the payment term in days and invoice_date is formatted as YYYY-MM-DD.
    """
    return {"InvoiceCode": code, "Status": int(InvoiceStatus.Verzonden), "DebtorCode": debtor,
            "Date": invoice_date.strftime("%Y-%m-%d"), "Term": term, "Discount": discount,
            "InvoiceLines": invoice_lines, "CustomFields": custom_fields, "Country": country}


def invoice_data_from_model(invoice: Invoice, company: Company):
    """Build the create-invoice payload from an Invoice and its Company.

    The payment term is derived as the number of days between invoice date and
    due date, the debtor code comes from the company's relatienummer, and the
    Dutch invoice-level HubSpot fields are passed through as WeFact custom
    fields (factuurbetreft, factuurreferentie, ...).
    """
    invoice_lines = [invoice_line_data_from_model(line_item) for line_item in invoice.line_items]
    term = (invoice.due_date - invoice.invoice_date).days
    custom_fields = {
        "factuurbetreft": invoice.betreft,
        "factuurreferentie": invoice.referentie,
        "factuurorganisatie": invoice.organisatie,
        "factuurtav": invoice.ter_attentie_van,
        "factuuradres": invoice.adres,
        "factuurpostcode": invoice.postcode,
        "factuurplaats": invoice.plaats,
        "factuurland": invoice.land,
        "factuurrelatienummer": invoice.relatienummer
    }
    return invoice_data(invoice.number, company.relatienummer, invoice.invoice_date, term, invoice.korting, invoice_lines, custom_fields, invoice.land)


def invoice_line_data(code, number, tax_percentage, discount_percentage, cost_center):
    """Return one WeFact invoice line.

    Discounts are always expressed per line ("line" type), never over the whole
    invoice; the invoice-level Discount field is separate.
    """
    return {"ProductCode": code, "Number": number, "TaxPercentage": tax_percentage, "DiscountPercentageType": "line",
            "DiscountPercentage": discount_percentage, "AccountingCostCentre": cost_center}


def invoice_line_data_from_model(line_item: LineItem):
    """Build one WeFact invoice line from a LineItem.

    Price and description are not repeated here; WeFact takes those from the
    product identified by the SKU, which generate_invoice creates or updates
    first.
    """
    return invoice_line_data(line_item.hs_sku, line_item.quantity, line_item.btw, line_item.hs_discount_percentage, line_item.kostenplaats)


def get_invoice_status(code):
    """Look up one invoice in WeFact by its invoice code.

    Called for every invoice this sync already created, so main.py can see what
    WeFact has done with it since; wefact_invoice_status reads the status off
    the payload. When the invoice cannot be found, the WeFact errors are
    returned instead and nothing is persisted.

    Returns a ResultType whose data holds InvoiceCode and, on success, the
    WeFact "show" payload under "invoice".
    """
    result = ResultType(persist=False, data={}, errors=[])
    result.data["InvoiceCode"] = code
    result.data["Status"] = int(InvoiceStatus.Betaald)
    api_client_invoice = InvoiceClient()
    invoice_number = f"{code}"
    invoice = api_client_invoice.show(invoice_data_id(invoice_number))
    if invoice["status"] == "success":
        result.data["invoice"] = invoice["invoice"]
    else:
        result.errors.extend(invoice['errors'])
    return result


def generate_invoice(invoice_object: Invoice, company_object: Company):
    """Create a HubSpot invoice in WeFact, including its debtor and products.

    The steps, in order:

    1. Bail out if WeFact already has an invoice with this code. The result is
       marked persist=True so the sync stops retrying it.
    2. Create the debtor for the company, or update it when it already exists.
    3. For every line item, create the product for its SKU or update it.
    4. Add the invoice itself, then download its PDF.

    Returns a ResultType; on success data["pdf"] holds the invoice PDF bytes,
    otherwise errors holds the WeFact error messages.
    """
    result = ResultType(persist=False, data={}, errors=[])
    api_client_invoice = InvoiceClient()
    invoice_number = f"{invoice_object.number}"
    invoice_object.number = invoice_number
    invoice = api_client_invoice.show(invoice_data_id(invoice_number))
    if invoice["status"] != WEFACT_STATUS_ERROR:
        # invoice was found (= no error)
        result = ResultType(persist=True, data={}, errors=[])
        result.errors.append("invoice already exists")
        return result
    # make sure the debtor exists which is used on the invoice
    api_client_debtor = DebtorClient()
    company = api_client_debtor.show(debtor_data_id_from_model(company_object))
    if company["status"] == WEFACT_STATUS_ERROR:
        # debtor not found
        api_client_debtor.add(debtor_data_add_from_model(company_object))
    else:
        api_client_debtor.edit(debtor_data_edit_from_model(company["debtor"]["Identifier"], company_object))
    # make sure the products exist that are used on the invoice
    api_client_product = ProductClient()
    for line_item in invoice_object.line_items:
        product = api_client_product.show(product_data_id_from_model(line_item))
        if product["status"] == WEFACT_STATUS_ERROR:
            # product not found
            api_client_product.add(product_data_add_from_model(line_item))
        elif product["status"] == WEFACT_STATUS_SUCCESS:
            api_client_product.edit(product_data_edit_from_model(product["product"]["Identifier"], line_item))
    # now build the invoice line items
    invoice = api_client_invoice.add(invoice_data_from_model(invoice_object, company_object))
    if invoice["status"] == WEFACT_STATUS_ERROR:
        result.errors.append("error processing invoice:")
        result.errors.extend(invoice['errors'])
        return result
    download_result = api_client_invoice.download(invoice_data_id(invoice_number))
    if invoice["status"] == WEFACT_STATUS_SUCCESS:
        pdf = base64.b64decode(download_result["invoice"]["Base64"])
        result.data["pdf"] = pdf
    return result


def wefact_invoice_status(result):
    """Return the WeFact invoice status as an int, or None when it cannot be read.

    result is the ResultType from get_invoice_status, which unwraps the WeFact
    "show" response, so the invoice fields sit directly under
    result.data["invoice"]. WeFact returns its fields as strings, so the status
    is coerced to an int; compare the result against WEFACT_STATUS_BETAALD,
    WEFACT_STATUS_VERVALLEN or another InvoiceStatus member.

    Anything unexpected - no payload, no Status field, an unparseable value -
    returns None and is logged, so the caller cannot mistake it for a real
    status. Writing the wrong status back corrupts the bookkeeping in HubSpot,
    so the check fails closed.
    """
    wefact_invoice = result.data.get("invoice") or {}
    raw_status = wefact_invoice.get("Status")
    if raw_status is None:
        logger.error("WeFact response holds no invoice status, leaving HubSpot untouched")
        return None
    try:
        status = int(raw_status)
    except (TypeError, ValueError):
        logger.error(
            f"WeFact returned an unreadable invoice Status {raw_status!r}, leaving HubSpot untouched"
        )
        return None
    return status
