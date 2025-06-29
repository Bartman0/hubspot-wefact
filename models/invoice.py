from pydantic import BaseModel, condate
from typing import List
from models.line_item import LineItem


class Invoice(BaseModel):
    id: str
    number: str
    status: str
    due_date: condate()
    invoice_date: condate()
    amount_billed: float
    line_items: List[LineItem] = list()
