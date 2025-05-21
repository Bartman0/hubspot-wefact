import base64
from collections import namedtuple
import datetime

from wefact.api import InvoiceClient, DebtorClient, ProductClient
from wefact.debtor import debtor_data_id, debtor_data_add
from wefact.product import product_data_id, product_data_add

from enum import IntEnum


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
    return {"InvoiceCode": code, "Status": int(InvoiceStatus.Verzonden), "DebtorCode": debtor, "Date": invoice_date.strftime("%Y-%m-%d"), "Term": term, "InvoiceLines": invoice_lines}

def invoice_update_paid(code):
    result = ResultType(data=[], errors=[])
    result.data.append({"InvoiceCode": code, "Status": int(InvoiceStatus.Betaald)})
    return result

def invoice_line_data(code, number, amount, description, tax_rate_percentage):
    return {"ProductCode": code, "Number": number, "TaxPercentage": tax_rate_percentage}

def update_invoice(invoice_number, invoice_status):
    result = ResultType(data={}, errors=[])
    api_client_invoice = InvoiceClient()
    invoice_number = f"testA_{invoice_number}"
    invoice = api_client_invoice.edit(invoice_data_id(invoice_number))
    if invoice["status"] != "error":
        result.errors.append("invoice already exists")
        return result
    return result

def generate_invoice(invoice_number, amount_billed, invoice_date, due_date,
                     company_relatienummer, company_name, company_address, company_zipcode, company_city, company_email,
                     tax_rates, line_items_details):
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    result = ResultType(data={}, errors=[])
    api_client_invoice = InvoiceClient()
    invoice_number = f"test_{current_date}_{invoice_number}"
    invoice = api_client_invoice.show(invoice_data_id(invoice_number))
    if invoice["status"] != "error":
        result.errors.append("invoice already exists")
        return result
    api_client_debtor = DebtorClient()
    company = api_client_debtor.show(debtor_data_id(company_relatienummer))
    if company["status"] == "error":
        api_client_debtor.add(debtor_data_add(company_relatienummer, company_name, company_address, company_zipcode, company_city, company_email))
    api_client_product = ProductClient()
    for line_item in line_items_details:
        # TODO handle price changes for already registered SKU's
        product = api_client_product.show(product_data_id(line_item['hs_sku']))
        if product["status"] == "error":
            api_client_product.add(product_data_add(line_item["hs_sku"], line_item["name"], line_item["name"], line_item["price"]))
    # now build the invoice line items
    invoice_lines = []
    for line_item in line_items_details:
        tax_rate_percentage = tax_rates[line_item["hs_tax_rate_group_id"]]["percentageRate"] if line_item["hs_tax_rate_group_id"] else 0
        invoice_lines.append(invoice_line_data(line_item["hs_sku"], line_item["quantity"], line_item["price"], line_item["name"], tax_rate_percentage))
    term = (due_date - invoice_date).days
    invoice = api_client_invoice.add(invoice_data(invoice_number, company_relatienummer, invoice_date, term, invoice_lines))
    if invoice["status"] == "error":
        result.errors.append("error processing invoice")
        return result
    download_result = api_client_invoice.download(invoice_data_id(invoice_number))
    if invoice["status"] == "success":
        pdf = base64.b64decode(download_result["invoice"]["Base64"])
        result.data["pdf"] = pdf
    return result
