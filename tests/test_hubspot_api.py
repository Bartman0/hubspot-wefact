from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from hubspot_api import api
from hubspot_api.api import _read_first_association_id
from models.invoice import Invoice


def make_page(results, after=None):
    """Fake HubSpot get_page response."""
    paging = SimpleNamespace(next=SimpleNamespace(after=after)) if after else None
    return SimpleNamespace(results=results, paging=paging)


def make_invoice_result(invoice_id, **props):
    defaults = {
        "hs_number": "F1",
        "hs_invoice_status": "open",
        "hs_amount_billed": "100.0",
        "hs_invoice_date": "2026-06-21",
        "hs_due_date": "2026-07-21",
    }
    defaults.update(props)
    return SimpleNamespace(id=invoice_id, properties=defaults)


def make_association(to_ids, num_errors=0, errors=None):
    refs = [SimpleNamespace(id=i) for i in to_ids]
    results = [SimpleNamespace(to=refs)] if to_ids else []
    obj = SimpleNamespace(results=results)
    obj.to_dict = lambda: {"num_errors": num_errors, "errors": errors or []}
    return obj


class TestGetInvoices:
    def test_maps_required_and_optional_properties(self):
        result = make_invoice_result(
            "inv-1",
            hs_number="F2024-009",
            hs_amount_billed="250.5",
            betreft_factuurniveau="Project X",
            relatienummer_factuur="R100",
        )
        api_client = MagicMock()
        api_client.crm.commerce.invoices.basic_api.get_page.return_value = make_page([result])

        invoices, after = api.get_invoices(api_client, after=None)

        assert after is None
        assert len(invoices) == 1
        inv = invoices[0]
        assert inv.id == "inv-1"
        assert inv.number == "F2024-009"
        assert inv.amount_billed == 250.5
        assert inv.invoice_date == date(2026, 6, 21)
        assert inv.due_date == date(2026, 7, 21)
        assert inv.betreft == "Project X"
        assert inv.relatienummer == "R100"

    def test_missing_optional_properties_default_to_none_and_zero(self):
        api_client = MagicMock()
        api_client.crm.commerce.invoices.basic_api.get_page.return_value = make_page(
            [make_invoice_result("inv-2")]
        )

        invoices, _ = api.get_invoices(api_client, after=None)

        inv = invoices[0]
        assert inv.betreft is None
        assert inv.korting == 0.0  # falls back to .get(..., 0.0)

    def test_paging_token_is_returned_when_present(self):
        api_client = MagicMock()
        api_client.crm.commerce.invoices.basic_api.get_page.return_value = make_page(
            [make_invoice_result("inv-3")], after="next-token"
        )

        _, after = api.get_invoices(api_client, after="prev-token")

        assert after == "next-token"
        api_client.crm.commerce.invoices.basic_api.get_page.assert_called_once()
        assert api_client.crm.commerce.invoices.basic_api.get_page.call_args.kwargs["after"] == "prev-token"

    def test_empty_page(self):
        api_client = MagicMock()
        api_client.crm.commerce.invoices.basic_api.get_page.return_value = make_page([])

        invoices, after = api.get_invoices(api_client, after=None)

        assert invoices == []
        assert after is None


class TestReadFirstAssociationId:
    def test_returns_first_associated_id(self):
        api_client = MagicMock()
        api_client.crm.associations.batch_api.read.return_value = make_association(["c1", "c2"])

        assert _read_first_association_id(api_client, "inv-1", "companies") == "c1"

    def test_returns_none_on_association_errors(self):
        api_client = MagicMock()
        api_client.crm.associations.batch_api.read.return_value = make_association(
            [], num_errors=1, errors=[{"message": "boom"}]
        )

        assert _read_first_association_id(api_client, "inv-1", "companies") is None


def _invoice():
    return Invoice(
        id="inv-1",
        number="F1",
        status="open",
        due_date=date(2026, 7, 21),
        invoice_date=date(2026, 6, 21),
        amount_billed=100.0,
    )


def _build_client(*, companies, contacts, line_items, line_item_props):
    """Wire a fake HubSpot client for get_invoice_details."""
    associations = {
        "companies": companies,
        "contacts": contacts,
        "line_items": line_items,
    }

    api_client = MagicMock()
    api_client.crm.associations.batch_api.read.side_effect = (
        lambda **kwargs: associations[kwargs["to_object_type"]]
    )
    api_client.crm.companies.basic_api.get_by_id.return_value = SimpleNamespace(
        id="comp-1",
        properties={"relatie_nummer": "R1", "name": "Acme", "address": "Main St 1"},
    )
    api_client.crm.contacts.basic_api.get_by_id.return_value = SimpleNamespace(
        id="cont-1",
        properties={"hs_object_id": "cont-1", "lastname": "Jansen", "factuur_toelichting": "x"},
    )
    api_client.crm.line_items.basic_api.get_by_id.side_effect = [
        SimpleNamespace(properties=props) for props in line_item_props
    ]
    return api_client


class TestGetInvoiceDetails:
    def test_builds_company_contact_and_line_items(self):
        api_client = _build_client(
            companies=make_association(["comp-1"]),
            contacts=make_association(["cont-1"]),
            line_items=make_association(["li-1"]),
            line_item_props=[
                {
                    "hs_sku": "SKU1",
                    "name": "Widget",
                    "quantity": "2",
                    "amount": "20",
                    "price": "10",
                    "btw": "0.21",
                    "discount": "0",
                    "hs_discount_percentage": "0",
                }
            ],
        )
        invoice = _invoice()

        company, contact, errors = api.get_invoice_details(api_client, invoice)

        assert errors == []
        assert company.id == "comp-1"
        assert company.relatienummer == "R1"
        assert company.name == "Acme"
        assert contact.hs_object_id == "cont-1"
        assert contact.lastname == "Jansen"
        assert len(invoice.line_items) == 1
        assert invoice.line_items[0].hs_sku == "SKU1"
        assert invoice.line_items[0].btw == 21.0

    def test_relatienummer_falls_back_to_company_id_when_missing(self):
        api_client = _build_client(
            companies=make_association(["comp-1"]),
            contacts=make_association(["cont-1"]),
            line_items=make_association([]),
            line_item_props=[],
        )
        # company has no relatie_nummer property
        api_client.crm.companies.basic_api.get_by_id.return_value = SimpleNamespace(
            id="comp-1", properties={"name": "Acme"}
        )

        company, _, _ = api.get_invoice_details(api_client, _invoice())

        assert company.relatienummer == "comp-1"

    def test_company_is_none_on_association_error(self):
        api_client = _build_client(
            companies=make_association([], num_errors=1, errors=[{"message": "no company"}]),
            contacts=make_association(["cont-1"]),
            line_items=make_association([]),
            line_item_props=[],
        )

        company, contact, errors = api.get_invoice_details(api_client, _invoice())

        assert company is None
        assert contact is not None
        api_client.crm.companies.basic_api.get_by_id.assert_not_called()

    def test_line_item_without_sku_is_skipped_with_error(self):
        api_client = _build_client(
            companies=make_association(["comp-1"]),
            contacts=make_association(["cont-1"]),
            line_items=make_association(["li-1", "li-2"]),
            line_item_props=[
                {
                    "hs_sku": "SKU1",
                    "name": "Widget",
                    "quantity": "1",
                    "amount": "10",
                    "price": "10",
                    "btw": "0.21",
                    "discount": "0",
                    "hs_discount_percentage": "0",
                },
                {
                    "hs_sku": None,
                    "name": "Mystery",
                    "quantity": "1",
                    "amount": "5",
                    "price": "5",
                    "btw": "0.21",
                    "discount": "0",
                    "hs_discount_percentage": "0",
                },
            ],
        )
        invoice = _invoice()

        _, _, errors = api.get_invoice_details(api_client, invoice)

        assert len(invoice.line_items) == 1
        assert invoice.line_items[0].hs_sku == "SKU1"
        assert len(errors) == 1
        assert "SKU is NOT set" in errors[0]
