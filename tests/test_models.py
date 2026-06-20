from datetime import date

import pytest
from pydantic import ValidationError

from models.company import Company
from models.contact import Contact
from models.invoice import Invoice
from models.line_item import LineItem


class TestInvoice:
    def _minimal(self, **overrides):
        data = dict(
            id="1",
            number="F2024-001",
            status="open",
            due_date=date(2026, 7, 21),
            invoice_date=date(2026, 6, 21),
            amount_billed=100.0,
        )
        data.update(overrides)
        return Invoice(**data)

    def test_minimal_construction_uses_defaults(self):
        invoice = self._minimal()
        assert invoice.korting == 0.0
        assert invoice.line_items == []
        assert invoice.betreft is None
        assert invoice.relatienummer is None

    def test_line_items_default_is_not_shared_between_instances(self):
        first = self._minimal()
        second = self._minimal()
        first.line_items.append(
            LineItem(hs_sku="X", name="n", amount=1.0, quantity=1, price=1.0, btw=21.0)
        )
        assert first.line_items != second.line_items
        assert second.line_items == []

    def test_dates_coerced_from_iso_string(self):
        invoice = self._minimal(invoice_date="2026-06-21", due_date="2026-07-21")
        assert invoice.invoice_date == date(2026, 6, 21)
        assert invoice.due_date == date(2026, 7, 21)

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Invoice(id="1", number="F1", status="open")


class TestLineItem:
    def test_defaults_for_optional_numeric_and_string_fields(self):
        item = LineItem(hs_sku="SKU1", name="Widget", amount=10.0, quantity=2, price=5.0, btw=21.0)
        assert item.discount == 0.0
        assert item.hs_discount_percentage == 0.0
        assert item.voorraadnummer is None
        assert item.kostenplaats is None

    def test_quantity_coerced_to_int(self):
        item = LineItem(hs_sku="SKU1", name="Widget", amount=10.0, quantity="2", price=5.0, btw=21.0)
        assert item.quantity == 2
        assert isinstance(item.quantity, int)

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            LineItem(hs_sku="SKU1", name="Widget")


class TestCompany:
    def test_only_id_required(self):
        company = Company(id="42")
        assert company.id == "42"
        assert company.relatienummer is None
        assert company.name is None

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            Company(name="Acme")

    def test_unknown_hubspot_property_is_ignored(self):
        # api.py passes the raw HubSpot property dict, which can include keys
        # that are not model fields (e.g. "relatie_nummer").
        company = Company(id="42", relatie_nummer="R1", name="Acme")
        assert not hasattr(company, "relatie_nummer")
        assert company.name == "Acme"


class TestContact:
    def test_only_object_id_required(self):
        contact = Contact(hs_object_id="9")
        assert contact.hs_object_id == "9"
        assert contact.lastname is None

    def test_missing_object_id_raises(self):
        with pytest.raises(ValidationError):
            Contact(lastname="Jansen")
