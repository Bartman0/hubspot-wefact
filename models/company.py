from pydantic import BaseModel


class Company(BaseModel):
    id: str
    relatienummer: str | None
    name: str | None
    address: str | None
    zip: str | None
    city: str | None
    email: str | None
