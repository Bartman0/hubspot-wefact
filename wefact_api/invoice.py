import base64
import datetime
from collections import namedtuple
from enum import IntEnum

from models.company import Company
from models.invoice import Invoice
from wefact_api.api import InvoiceClient, DebtorClient, ProductClient
from wefact_api.debtor import debtor_data_id, debtor_data_add
from wefact_api.product import product_data_id, product_data_add

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


def invoice_data(code, debtor, invoice_date, term, invoice_lines):
    return {"InvoiceCode": code, "Status": int(InvoiceStatus.Verzonden), "DebtorCode": debtor,
            "Date": invoice_date.strftime("%Y-%m-%d"), "Term": term, "InvoiceLines": invoice_lines}


def invoice_update_paid(code):
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    result = ResultType(data={}, errors=[])
    result.data["InvoiceCode"] = code
    result.data["Status"]= int(InvoiceStatus.Betaald)
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


def invoice_line_data(code, number, tax_percentage):
    return {"ProductCode": code, "Number": number, "TaxPercentage": tax_percentage}


def update_invoice(invoice):
    result = ResultType(data={}, errors=[])
    api_client_invoice = InvoiceClient()
    invoice_number = f"testA_{invoice.number}"
    invoice = api_client_invoice.edit(invoice_data_id(invoice_number))
    if invoice["status"] != "error":
        result.errors.append("invoice already exists")
        return result
    return result


def generate_invoice(invoice_object: Invoice, company_object: Company):
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    result = ResultType(data={}, errors=[])
    api_client_invoice = InvoiceClient()
    invoice_number = f"test_{current_date}_{invoice_object.number}"
    invoice = api_client_invoice.show(invoice_data_id(invoice_number))
    if invoice["status"] != WEFACT_INVOICE_STATUS_ERROR:
        result.errors.append("invoice already exists")
        return result
    api_client_debtor = DebtorClient()
    company = api_client_debtor.show(debtor_data_id(company_object.relatienummer))
    if company["status"] == WEFACT_INVOICE_STATUS_ERROR:
        api_client_debtor.add(
            debtor_data_add(company_object.id, company_object.name, company_object.address, company_object.zip, company_object.city, company_object.email))
    api_client_product = ProductClient()
    for line_item in invoice_object.line_items:
        product = api_client_product.show(product_data_id(line_item.hs_sku))
        if product["status"] == WEFACT_INVOICE_STATUS_ERROR:
            response = api_client_product.add(
                product_data_add(line_item.hs_sku, line_item.name, line_item.name, line_item.price))
        elif product["status"] == WEFACT_PRODUCT_STATUS_SUCCESS:
            response = api_client_product.edit(
                product_data_add(line_item.hs_sku, line_item.name, line_item.name, line_item.price))
    # now build the invoice line items
    invoice_lines = [invoice_line_data(line_item.hs_sku, line_item.quantity, line_item.btw) for line_item in invoice_object.line_items]
    term = (invoice_object.due_date - invoice_object.invoice_date).days
    invoice = api_client_invoice.add(
        invoice_data(invoice_number, company_object.relatienummer, invoice_object.invoice_date, term, invoice_lines))
    if invoice["status"] == WEFACT_INVOICE_STATUS_ERROR:
        result.errors.append("error processing invoice:")
        result.errors.extend(invoice['errors'])
        return result
    download_result = api_client_invoice.download(invoice_data_id(invoice_number))
    if invoice["status"] == WEFACT_INVOICE_STATUS_SUCCESS:
        pdf = base64.b64decode(download_result["invoice"]["Base64"])
        result.data["pdf"] = pdf
    return result
