import logging

import os
import json
import requests
from abc import ABC

WEFACT_API_URL: str = "https://api.mijnwefact.nl/v2/"
WEFACT_API_KEY: str = os.environ["WEFACT_API_KEY"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


class WeFactBase(ABC):
    def __init__(self):
        self._url = WEFACT_API_URL
        self._controller = None

    def _build_request(self, action):
        return {
            "api_key": WEFACT_API_KEY,
            "controller": self._controller,
            "action": action,
        }

    def request(self, action, data: dict):
        return requests.post(self._url, data=json.dumps(self._build_request(action) | data)).json()


class InvoiceClient(WeFactBase):
    def __init__(self):
        super().__init__()
        self._controller = "invoice"

    def list(self):
        return self.request("list", {})

    def show(self, invoice):
        return self.request("show", data=invoice)

    def add(self, invoice):
        return self.request("add", data=invoice)

    def download(self, invoice):
        return self.request("download", data=invoice)

    def sendbyemail(self, invoice):
        return self.request("sendbyemail", data=invoice)


class DebtorClient(WeFactBase):
    def __init__(self):
        super().__init__()
        self._controller = "debtor"

    def list(self):
        return self.request("list", {})

    def show(self, debtor):
        return self.request("show", data=debtor)

    def add(self, debtor):
        return self.request("add", data=debtor)


class ProductClient(WeFactBase):
    def __init__(self):
        super().__init__()
        self._controller = "product"

    def list(self):
        return self.request("list", {})

    def show(self, product):
        return self.request("show", data=product)

    def add(self, product):
        return self.request("add", data=product)
