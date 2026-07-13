from pydantic import BaseModel


class LineItem(BaseModel):
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
