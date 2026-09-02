import json
import logging
import os
from abc import ABC

import requests

WEFACT_API_URL: str = "https://api.mijnwefact.nl/v2/"
WEFACT_API_KEY: str = os.environ["WEFACT_API_KEY"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeFactBase(ABC):
    """Thin client for the WeFact v2 API.

    WeFact exposes a single endpoint; the object you address is selected with a
    "controller" field and the operation with an "action" field. Subclasses set
    _controller and inherit the shared list/show/add/edit actions.
    """

    _controller: str | None = None

    def __init__(self):
        """Pin the instance to the WeFact v2 endpoint."""
        self._url = WEFACT_API_URL

    def _build_request(self, action):
        """Return the envelope every request needs: api key, controller and action."""
        return {"api_key": WEFACT_API_KEY, "controller": self._controller, "action": action}

    def request(self, action, data: dict | None = None):
        """POST one action to WeFact and return the decoded JSON response.

        data is merged over the request envelope. Every WeFact response carries
        a "status" field of either "success" or "error"; callers are expected to
        check it, since HTTP errors are not raised here.
        """
        payload = self._build_request(action) | (data or {})
        return requests.post(self._url, data=json.dumps(payload)).json()

    def list(self):
        """List all objects for this controller."""
        return self.request("list", {})

    def show(self, data):
        """Look up a single object; data holds its identifying code.

        A response with status "error" means the object does not exist, which is
        how the sync tests for existence.
        """
        return self.request("show", data)

    def add(self, data):
        """Create a new object from data."""
        return self.request("add", data)

    def edit(self, data):
        """Update an existing object; data must include its Identifier."""
        return self.request("edit", data)


class InvoiceClient(WeFactBase):
    """WeFact invoice controller, plus the invoice-only download and email actions."""

    _controller = "invoice"

    def download(self, invoice):
        """Fetch the invoice PDF; the response carries it base64-encoded."""
        return self.request("download", invoice)

    def sendbyemail(self, invoice):
        """Have WeFact email the invoice to its debtor."""
        return self.request("sendbyemail", invoice)


class DebtorClient(WeFactBase):
    """WeFact debtor controller; debtors mirror HubSpot companies."""

    _controller = "debtor"


class ProductClient(WeFactBase):
    """WeFact product controller; products mirror HubSpot line-item SKUs."""

    _controller = "product"
