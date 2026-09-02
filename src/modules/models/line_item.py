from pydantic import BaseModel


class LineItem(BaseModel):
    """One HubSpot invoice line item, which becomes a WeFact product plus invoice line.

    hs_sku is the WeFact ProductCode, so a line item without one cannot be
    synced. btw is stored as a percentage (21.0), not as the fraction HubSpot
    returns. Both a discount amount and a discount percentage are kept because
    HubSpot may supply either.
    """

    hs_sku: str
    name: str
    amount: float
    quantity: int
    price: float
    btw: float
    discount: float = 0.0
    hs_discount_percentage: float = 0.0
    voorraadnummer: str | None = None
    kostenplaats: str | None = None  # WeFact expects strings for cost centers
    grootboek: str | None = None
    gewicht: str | None = None
    artikelsoort: str | None = None
    artikelgroep: str | None = None
    hs_tax_rate_group_id: str | None = None

