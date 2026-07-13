from datetime import date

from pydantic import BaseModel, Field

from models.line_item import LineItem


class Invoice(BaseModel):
    id: str
    number: str
    status: str
    due_date: date
    invoice_date: date
    amount_billed: float
    korting: float = 0.0
    line_items: list[LineItem] = Field(default_factory=list)
    betreft: str | None = None
    referentie: str | None = None
    organisatie: str | None = None
    ter_attentie_van: str | None = None
    adres: str | None = None
    postcode: str | None = None
    plaats: str | None = None
    land: str | None = None
    relatienummer: str | None = None
