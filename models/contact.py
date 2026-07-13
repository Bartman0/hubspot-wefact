from pydantic import BaseModel


class Contact(BaseModel):
    hs_object_id: str
    lastname: str | None = None
    factuur_toelichting: str | None = None
    createdate: str | None = None
    lastmodifieddate: str | None = None
