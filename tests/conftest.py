import os

# Several modules read credentials from the environment at import time
# (e.g. wefact_api.api). Set dummy values so the pure-logic functions can be
# imported and tested without any real secrets or network access.
os.environ.setdefault("WEFACT_API_KEY", "test-wefact-key")
os.environ.setdefault("HUBSPOT_ACCESS_TOKEN", "test-hubspot-token")
os.environ.setdefault("API_KEY", "test-api-key")
