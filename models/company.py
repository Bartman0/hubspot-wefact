from pydantic import BaseModel


class Company(BaseModel):
    id: str
    relatienummer: str | None = None
    name: str | None = None
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    email: str | None = None
    mailadres_factuur: str | None = None
    land: str | None = None
