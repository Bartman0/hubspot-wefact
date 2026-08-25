from pydantic import BaseModel


class Company(BaseModel):
    """A HubSpot company, which becomes a WeFact debtor.

    relatienummer is the WeFact debtor code and falls back to the HubSpot
    company id; mailadres_factuur (not email) is the address invoices go to.
    """

    id: str
    relatienummer: str | None = None
    name: str | None = None
    address: str | None = None
    zip: str | None = None
    city: str | None = None
    email: str | None = None
    mailadres_factuur: str | None = None
    land: str | None = None
