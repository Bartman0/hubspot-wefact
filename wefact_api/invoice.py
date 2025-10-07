import base64
import datetime
from collections import namedtuple
from enum import IntEnum

from models.company import Company
from models.contact import Contact
from models.invoice import Invoice
from models.line_item import LineItem
from wefact_api.api import InvoiceClient, DebtorClient, ProductClient
from wefact_api.debtor import debtor_data_id_from_model, debtor_data_add_from_model
from wefact_api.product import product_data_add_from_model, product_data_id_from_model

WEFACT_INVOICE_STATUS_SUCCESS = "success"
WEFACT_INVOICE_STATUS_ERROR = "error"
WEFACT_PRODUCT_STATUS_SUCCESS = "product"

ResultType = namedtuple("result", ["data", "errors"], defaults=[{}, []])


class InvoiceStatus(IntEnum):
    Concept = 0
    Verzonden = 2
    Deels_betaald = 3
    Betaald = 4
    Creditfactuur = 8
    Vervallen = 9


def invoice_data_id(code):
    return {"InvoiceCode": code}


def invoice_data_id_from_model(invoice: Invoice):
    return invoice_data_id(invoice.number)


def invoice_data(code, debtor, invoice_date, term, invoice_lines, custom_fields):
    return {"InvoiceCode": code, "Status": int(InvoiceStatus.Verzonden), "DebtorCode": debtor,
            "Date": invoice_date.strftime("%Y-%m-%d"), "Term": term, "InvoiceLines": invoice_lines, "CustomFields": custom_fields}


def invoice_data_from_model(invoice: Invoice, company: Company, contact: Contact):
    invoice_lines = [invoice_line_data_from_model(line_item) for line_item in invoice.line_items]
    term = (invoice.due_date - invoice.invoice_date).days
    custom_fields = [
        {"key": "veld_betreft", "value": invoice.betreft},
        {"key": "veld_referentie", "value": invoice.referentie},
        {"key": "veld_organisatie", "value": invoice.organisatie},
        {"key": "veld_ter_attentie_van", "value": invoice.ter_attentie_van},
    ]
    return invoice_data(invoice.number, company.relatienummer, invoice.invoice_date, term, invoice_lines, custom_fields)


def invoice_line_data(code, number, tax_percentage):
    return {"ProductCode": code, "Number": number, "TaxPercentage": tax_percentage}


def invoice_line_data_from_model(line_item: LineItem):
    return invoice_line_data(line_item.hs_sku, line_item.quantity, line_item.btw)


def invoice_update_paid(code):
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    result = ResultType(data={}, errors=[])
    result.data["InvoiceCode"] = code
    result.data["Status"] = int(InvoiceStatus.Betaald)
    api_client_invoice = InvoiceClient()
    invoice_number = f"test_{current_date}_{code}"
    invoice = api_client_invoice.show(invoice_data_id(invoice_number))
    download_result = api_client_invoice.download(invoice_data_id(invoice_number))
    if invoice["status"] == "success":
        pdf = base64.b64decode(download_result["invoice"]["Base64"])
        result.data["pdf"] = pdf
    else:
        result.errors.extend(invoice['errors'])
    return result


def update_invoice(invoice):
    result = ResultType(data={}, errors=[])
    api_client_invoice = InvoiceClient()
    invoice_number = f"testA_{invoice.number}"
    invoice = api_client_invoice.edit(invoice_data_id(invoice_number))
    if invoice["status"] != "error":
        result.errors.append("invoice already exists")
        return result
    return result


def generate_invoice(invoice_object: Invoice, company_object: Company, contact_object: Contact):
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    result = ResultType(data={}, errors=[])
    api_client_invoice = InvoiceClient()
    invoice_number = f"test_{current_date}_{invoice_object.number}"
    invoice_object.number = invoice_number
    invoice = api_client_invoice.show(invoice_data_id(invoice_number))
    if invoice["status"] != WEFACT_INVOICE_STATUS_ERROR:
        result.errors.append("invoice already exists")
        return result
    api_client_debtor = DebtorClient()
    company = api_client_debtor.show(debtor_data_id_from_model(company_object))
    if company["status"] == WEFACT_INVOICE_STATUS_ERROR:
        api_client_debtor.add(debtor_data_add_from_model(company_object))
    api_client_product = ProductClient()
    for line_item in invoice_object.line_items:
        product = api_client_product.show(product_data_id_from_model(line_item))
        if product["status"] == WEFACT_INVOICE_STATUS_ERROR:
            response = api_client_product.add(product_data_add_from_model(line_item))
        elif product["status"] == WEFACT_PRODUCT_STATUS_SUCCESS:
            response = api_client_product.edit(product_data_add_from_model(line_item))
    # now build the invoice line items
    invoice = api_client_invoice.add(invoice_data_from_model(invoice_object, company_object, contact_object))
    if invoice["status"] == WEFACT_INVOICE_STATUS_ERROR:
        result.errors.append("error processing invoice:")
        result.errors.extend(invoice['errors'])
        return result
    download_result = api_client_invoice.download(invoice_data_id(invoice_number))
    if invoice["status"] == WEFACT_INVOICE_STATUS_SUCCESS:
        pdf = base64.b64decode(download_result["invoice"]["Base64"])
        result.data["pdf"] = pdf
    return result
