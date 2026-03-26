import logging
import os

import requests

# Rate-limit groups documented by Artifacts MMO API:
#   account endpoints  — 10 req/s,  500 req/h
#   data endpoints     — 20 req/s,  500 req/min, 10 000 req/h
#   action endpoints   — 20 req/2s, 500 req/min, 10 000 req/h
# Keep this in mind when building multi-character automation loops.

BASE_URL = os.getenv("ARTIFACTS_BASE_URL", "https://api.artifactsmmo.com")

logger = logging.getLogger(__name__)


class ArtifactsClient:
    """
    Thin HTTP wrapper around requests.Session for the Artifacts MMO API.
    Handles auth headers and logs every request/response for easy debugging.
    Domain logic lives in services/, not here.
    """

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def get(self, path: str, **kwargs):
        """Send an authenticated GET request to the given API path."""
        url = f"{BASE_URL}{path}"
        logger.debug("GET %s", url)
        response = self.session.get(url, **kwargs)
        logger.debug("→ %s", response.status_code)
        return response

    def post(self, path: str, json=None, **kwargs):
        """
        Send an authenticated POST request to the given API path.
        Most character actions use POST and return both a result and cooldown data.
        """
        url = f"{BASE_URL}{path}"
        logger.debug("POST %s | payload: %s", url, json)
        response = self.session.post(url, json=json, **kwargs)
        logger.debug("→ %s", response.status_code)
        return response
