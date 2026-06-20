import base64
import datetime
from collections import namedtuple
from enum import IntEnum

from models.company import Company
from models.contact import Contact
from models.invoice import Invoice
from models.line_item import LineItem
from wefact_api.api import InvoiceClient, DebtorClient, ProductClient
from wefact_api.debtor import debtor_data_id_from_model, debtor_data_add_from_model, debtor_data_edit_from_model
from wefact_api.product import product_data_add_from_model, product_data_id_from_model

WEFACT_INVOICE_STATUS_SUCCESS = "success"
WEFACT_INVOICE_STATUS_ERROR = "error"
WEFACT_PRODUCT_STATUS_SUCCESS = "success"
WEFACT_PRODUCT_STATUS_ERROR = "error"

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


def invoice_data(code, debtor, invoice_date, term, discount, invoice_lines, custom_fields, country):
    return {"InvoiceCode": code, "Status": int(InvoiceStatus.Verzonden), "DebtorCode": debtor,
            "Date": invoice_date.strftime("%Y-%m-%d"), "Term": term, "Discount": discount,
            "InvoiceLines": invoice_lines, "CustomFields": custom_fields, "Country": country}


def invoice_data_from_model(invoice: Invoice, company: Company):
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


def invoice_line_data(code, number, tax_percentage, discount_percentage):
    return {"ProductCode": code, "Number": number, "TaxPercentage": tax_percentage, "DiscountPercentageType": "line",
            "DiscountPercentage": discount_percentage}


def invoice_line_data_from_model(line_item: LineItem):
    return invoice_line_data(line_item.hs_sku, line_item.quantity, line_item.btw, line_item.hs_discount_percentage)


def invoice_update_paid(code):
    result = ResultType(data={}, errors=[])
    result.data["InvoiceCode"] = code
    result.data["Status"] = int(InvoiceStatus.Betaald)
    api_client_invoice = InvoiceClient()
    invoice_number = f"{code}"
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
    invoice_number = f"{invoice.number}"
    invoice = api_client_invoice.edit(invoice_data_id(invoice_number))
    if invoice["status"] != "error":
        result.errors.append("invoice already exists")
        return result
    return result


def generate_invoice(invoice_object: Invoice, company_object: Company):
    result = ResultType(data={}, errors=[])
    api_client_invoice = InvoiceClient()
    invoice_number = f"{invoice_object.number}"
    invoice_object.number = invoice_number
    invoice = api_client_invoice.show(invoice_data_id(invoice_number))
    if invoice["status"] != WEFACT_INVOICE_STATUS_ERROR:
        # invoice was found (= no error)
        result.errors.append("invoice already exists")
        return result
    # make sure the debtor exists which is used on the invoice
    api_client_debtor = DebtorClient()
    company = api_client_debtor.show(debtor_data_id_from_model(company_object))
    if company["status"] == WEFACT_INVOICE_STATUS_ERROR:
        # debtor not found
        api_client_debtor.add(debtor_data_add_from_model(company_object))
    else:
        api_client_debtor.edit(debtor_data_edit_from_model(company["debtor"]["Identifier"], company_object))
    # make sure the products exist that are used on the invoice
    api_client_product = ProductClient()
    for line_item in invoice_object.line_items:
        product = api_client_product.show(product_data_id_from_model(line_item))
        if product["status"] == WEFACT_PRODUCT_STATUS_ERROR:
            # product not found
            response = api_client_product.add(product_data_add_from_model(line_item))
        elif product["status"] == WEFACT_PRODUCT_STATUS_SUCCESS:
            response = api_client_product.edit(product_data_add_from_model(line_item))
    # now build the invoice line items
    invoice = api_client_invoice.add(invoice_data_from_model(invoice_object, company_object))
    if invoice["status"] == WEFACT_INVOICE_STATUS_ERROR:
        result.errors.append("error processing invoice:")
        result.errors.extend(invoice['errors'])
        return result
    download_result = api_client_invoice.download(invoice_data_id(invoice_number))
    if invoice["status"] == WEFACT_INVOICE_STATUS_SUCCESS:
        pdf = base64.b64decode(download_result["invoice"]["Base64"])
        result.data["pdf"] = pdf
    return result
