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
    _controller: str | None = None

    def __init__(self):
        self._url = WEFACT_API_URL

    def _build_request(self, action):
        return {"api_key": WEFACT_API_KEY, "controller": self._controller, "action": action}

    def request(self, action, data: dict | None = None):
        payload = self._build_request(action) | (data or {})
        return requests.post(self._url, data=json.dumps(payload)).json()

    def list(self):
        return self.request("list", {})

    def show(self, data):
        return self.request("show", data)

    def add(self, data):
        return self.request("add", data)

    def edit(self, data):
        return self.request("edit", data)


class InvoiceClient(WeFactBase):
    _controller = "invoice"

    def download(self, invoice):
        return self.request("download", invoice)

    def sendbyemail(self, invoice):
        return self.request("sendbyemail", invoice)


class DebtorClient(WeFactBase):
    _controller = "debtor"


class ProductClient(WeFactBase):
    _controller = "product"
