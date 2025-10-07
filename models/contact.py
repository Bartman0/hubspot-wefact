from pydantic import BaseModel


class Contact(BaseModel):
    hs_object_id: str
    lastname: str | None
    factuur_toelichting: str | None
    createdate: str | None
    lastmodifieddate: str | None
