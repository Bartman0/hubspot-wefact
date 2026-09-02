from pydantic import BaseModel


class Contact(BaseModel):
    """A HubSpot contact associated with an invoice.

    Fetched for context and logging only; nothing here is sent to WeFact.
    """

    hs_object_id: str
    lastname: str | None = None
    factuur_toelichting: str | None = None
    createdate: str | None = None
    lastmodifieddate: str | None = None
