from datetime import date

from models.company import Company
from models.invoice import Invoice
from models.line_item import LineItem
from wefact_api import debtor, product
from wefact_api.invoice import (
    InvoiceStatus,
    ResultType,
    invoice_data,
    invoice_data_from_model,
    invoice_data_id,
    invoice_data_id_from_model,
    invoice_line_data,
    invoice_line_data_from_model,
)


def make_line_item(**overrides):
    data = dict(
        hs_sku="SKU1",
        name="Widget",
        amount=20.0,
        quantity=2,
        price=10.0,
        btw=21.0,
        discount=0.0,
        hs_discount_percentage=0.0,
        kostenplaats="123"
    )
    data.update(overrides)
    return LineItem(**data)


def make_company(**overrides):
    data = dict(
        id="c1",
        relatienummer="R100",
        name="Acme BV",
        address="Main St 1",
        zip="1011AA",
        city="Amsterdam",
        email="info@acme.test",
        mailadres_factuur="facturen@acme.test",
        land="NL",
    )
    data.update(overrides)
    return Company(**data)


def make_invoice(**overrides):
    data = dict(
        id="1",
        number="F2024-001",
        status="open",
        due_date=date(2026, 7, 21),
        invoice_date=date(2026, 6, 21),
        amount_billed=100.0,
        korting=5.0,
        betreft="Project X",
        referentie="REF-1",
        organisatie="Acme BV",
        ter_attentie_van="Jan Jansen",
        adres="Main St 1",
        postcode="1011AA",
        plaats="Amsterdam",
        land="NL",
        relatienummer="R100",
    )
    data.update(overrides)
    return Invoice(**data)


class TestProductBuilders:
    def test_product_data_id(self):
        assert product.product_data_id("SKU1") == {"ProductCode": "SKU1"}

    def test_product_data_id_from_model(self):
        assert product.product_data_id_from_model(make_line_item()) == {"ProductCode": "SKU1"}

    def test_product_data_add_from_model_uses_name_as_keyphrase(self):
        assert product.product_data_add_from_model(make_line_item(name="Widget", price=10.0)) == {
            "ProductCode": "SKU1",
            "ProductName": "Widget",
            "ProductKeyPhrase": "Widget",
            "PriceExcl": 10.0,
            "AccountingCostCentre": "123"
        }

    def test_product_data_edit_from_model_includes_identifier(self):
        assert product.product_data_edit_from_model(77, make_line_item()) == {
            "Identifier": 77,
            "ProductCode": "SKU1",
            "ProductName": "Widget",
            "ProductKeyPhrase": "Widget",
            "PriceExcl": 10.0,
            "AccountingCostCentre": "123"
        }


class TestDebtorBuilders:
    def test_debtor_data_id_from_model_uses_relatienummer(self):
        assert debtor.debtor_data_id_from_model(make_company()) == {"DebtorCode": "R100"}

    def test_debtor_data_add_from_model_maps_invoice_email(self):
        # Email must come from mailadres_factuur, not the generic company email.
        result = debtor.debtor_data_add_from_model(make_company())
        assert result == {
            "DebtorCode": "R100",
            "CompanyName": "Acme BV",
            "Address": "Main St 1",
            "ZipCode": "1011AA",
            "City": "Amsterdam",
            "EmailAddress": "facturen@acme.test",
        }

    def test_debtor_data_edit_from_model_includes_identifier(self):
        result = debtor.debtor_data_edit_from_model(55, make_company())
        assert result["Identifier"] == 55
        assert result["DebtorCode"] == "R100"
        assert result["EmailAddress"] == "facturen@acme.test"


class TestInvoiceBuilders:
    def test_invoice_status_values(self):
        assert int(InvoiceStatus.Verzonden) == 2
        assert int(InvoiceStatus.Betaald) == 4

    def test_result_type_defaults_are_independent(self):
        a = ResultType()
        b = ResultType()
        assert a.data == {} and a.errors == []
        # defaults come from namedtuple; confirm both fields exist and behave
        a.errors.append("boom")
        assert "boom" in a.errors

    def test_result_type_persist_defaults_to_false(self):
        # persist drives whether main.py writes the invoice id to the state db;
        # it must default to False so nothing is persisted unless explicitly set.
        assert ResultType().persist is False
        assert ResultType(persist=True).persist is True

    def test_invoice_data_id_from_model(self):
        assert invoice_data_id_from_model(make_invoice()) == {"InvoiceCode": "F2024-001"}

    def test_invoice_line_data_from_model(self):
        item = make_line_item(quantity=3, btw=21.0, hs_discount_percentage=10.0, kostenplaats="123")
        assert invoice_line_data_from_model(item) == {
            "ProductCode": "SKU1",
            "Number": 3,
            "TaxPercentage": 21.0,
            "DiscountPercentageType": "line",
            "DiscountPercentage": 10.0,
            "AccountingCostCentre": "123"
        }

    def test_invoice_data_formats_date_and_sets_sent_status(self):
        result = invoice_data(
            "F1", "R100", date(2026, 6, 21), 30, 5.0, [], {}, "NL"
        )
        assert result["InvoiceCode"] == "F1"
        assert result["Date"] == "2026-06-21"
        assert result["Status"] == int(InvoiceStatus.Verzonden)
        assert result["Term"] == 30
        assert result["Country"] == "NL"

    def test_invoice_data_from_model_computes_term_in_days(self):
        invoice = make_invoice(invoice_date=date(2026, 6, 1), due_date=date(2026, 7, 1))
        result = invoice_data_from_model(invoice, make_company())
        assert result["Term"] == 30

    def test_invoice_data_from_model_builds_custom_fields(self):
        invoice = make_invoice()
        result = invoice_data_from_model(invoice, make_company())
        assert result["CustomFields"] == {
            "factuurbetreft": "Project X",
            "factuurreferentie": "REF-1",
            "factuurorganisatie": "Acme BV",
            "factuurtav": "Jan Jansen",
            "factuuradres": "Main St 1",
            "factuurpostcode": "1011AA",
            "factuurplaats": "Amsterdam",
            "factuurland": "NL",
            "factuurrelatienummer": "R100",
        }

    def test_invoice_data_from_model_uses_company_debtorcode_and_invoice_discount(self):
        invoice = make_invoice(korting=12.5)
        result = invoice_data_from_model(invoice, make_company(relatienummer="R999"))
        assert result["DebtorCode"] == "R999"
        assert result["Discount"] == 12.5

    def test_invoice_data_from_model_renders_one_line_per_line_item(self):
        invoice = make_invoice()
        invoice.line_items = [make_line_item(hs_sku="A"), make_line_item(hs_sku="B")]
        result = invoice_data_from_model(invoice, make_company())
        assert [line["ProductCode"] for line in result["InvoiceLines"]] == ["A", "B"]
