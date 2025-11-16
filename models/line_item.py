from pydantic import BaseModel


class LineItem(BaseModel):
    hs_sku: str
    amount: float
    quantity: int
    price: float
    voorraadnummer: str | None
    name: str
    kostenplaats: str | None
    grootboek: str | None
    gewicht: str | None
    artikelsoort: str | None
    artikelgroep: str | None
    hs_tax_rate_group_id: str | None
    btw: float
    discount: float
    hs_discount_percentage: float