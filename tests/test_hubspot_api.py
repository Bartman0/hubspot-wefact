from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from hubspot_api import api
from hubspot_api.api import _read_first_association_id, set_invoice_to_paid
from models.invoice import Invoice


def make_page(results, after=None):
    """Fake HubSpot get_page response."""
    paging = SimpleNamespace(next=SimpleNamespace(after=after)) if after else None
    return SimpleNamespace(results=results, paging=paging)


def make_invoice_result(invoice_id, **props):
    """Fake one HubSpot invoice result, with the required properties filled in."""
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
    """Fake a HubSpot batch association read pointing at to_ids, or reporting errors."""
    refs = [SimpleNamespace(id=i) for i in to_ids]
    results = [SimpleNamespace(to=refs)] if to_ids else []
    obj = SimpleNamespace(results=results)
    obj.to_dict = lambda: {"num_errors": num_errors, "errors": errors or []}
    return obj


class TestGetInvoices:
    """Property mapping and paging behaviour of get_invoices."""

    def test_maps_required_and_optional_properties(self):
        """HubSpot properties land on the matching Invoice fields, with types coerced."""
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
        """Absent custom properties do not fail the mapping."""
        api_client = MagicMock()
        api_client.crm.commerce.invoices.basic_api.get_page.return_value = make_page(
            [make_invoice_result("inv-2")]
        )

        invoices, _ = api.get_invoices(api_client, after=None)

        inv = invoices[0]
        assert inv.betreft is None
        assert inv.korting == 0.0  # falls back to .get(..., 0.0)

    def test_paging_token_is_returned_when_present(self):
        """The incoming cursor is forwarded to HubSpot and the next one is returned."""
        api_client = MagicMock()
        api_client.crm.commerce.invoices.basic_api.get_page.return_value = make_page(
            [make_invoice_result("inv-3")], after="next-token"
        )

        _, after = api.get_invoices(api_client, after="prev-token")

        assert after == "next-token"
        api_client.crm.commerce.invoices.basic_api.get_page.assert_called_once()
        assert api_client.crm.commerce.invoices.basic_api.get_page.call_args.kwargs["after"] == "prev-token"

    def test_empty_page(self):
        """A page with no results yields no invoices and no next cursor."""
        api_client = MagicMock()
        api_client.crm.commerce.invoices.basic_api.get_page.return_value = make_page([])

        invoices, after = api.get_invoices(api_client, after=None)

        assert invoices == []
        assert after is None


class TestReadFirstAssociationId:
    """How _read_first_association_id picks an id and handles errors."""

    def test_returns_first_associated_id(self):
        """With several associated objects, the first one is used."""
        api_client = MagicMock()
        api_client.crm.associations.batch_api.read.return_value = make_association(["c1", "c2"])

        assert _read_first_association_id(api_client, "inv-1", "companies") == "c1"

    def test_returns_none_on_association_errors(self):
        """A HubSpot association error yields None instead of raising."""
        api_client = MagicMock()
        api_client.crm.associations.batch_api.read.return_value = make_association(
            [], num_errors=1, errors=[{"message": "boom"}]
        )

        assert _read_first_association_id(api_client, "inv-1", "companies") is None


def _invoice():
    """Build a minimal Invoice for the get_invoice_details tests."""
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
    """How get_invoice_details resolves associations and reports bad data."""

    def test_builds_company_contact_and_line_items(self):
        """A fully associated invoice yields a company, a contact and its line items."""
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
        """Without relatie_nummer the company id is used as the WeFact debtor code."""
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
        """A failed company association leaves company None and skips the lookup."""
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
        """A line item lacking a SKU is dropped and reported, the rest still map."""
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


def _updated_properties(api_client):
    """Return the properties passed to the HubSpot invoice update, or None."""
    update = api_client.crm.commerce.invoices.basic_api.update
    if not update.called:
        return None
    return update.call_args.kwargs["simple_public_object_input"].properties


class TestSetInvoiceToPaid:
    """Pushing a paid status from WeFact back onto the HubSpot invoice.

    Whether the invoice is actually paid is decided upstream by
    wefact_api.invoice.invoice_is_paid (see TestInvoiceIsPaid in
    test_wefact_builders.py); main.py only calls this once that returned True,
    so these tests cover the update itself.
    """

    def test_invoice_is_set_to_paid_in_hubspot(self):
        """The HubSpot invoice named by its id gets hs_invoice_status paid."""
        api_client = MagicMock()

        set_invoice_to_paid(api_client, _invoice())

        assert _updated_properties(api_client) == {"hs_invoice_status": "paid"}
        assert api_client.crm.commerce.invoices.basic_api.update.call_args.kwargs["invoice_id"] == "inv-1"

    def test_local_invoice_status_is_updated_too(self):
        """The in-memory Invoice reflects the new status without a HubSpot reread."""
        invoice = _invoice()

        set_invoice_to_paid(MagicMock(), invoice)

        assert invoice.status == "paid"

    def test_hubspot_response_is_returned(self):
        """The caller gets the updated HubSpot object back."""
        api_client = MagicMock()

        response = set_invoice_to_paid(api_client, _invoice())

        assert response is api_client.crm.commerce.invoices.basic_api.update.return_value
