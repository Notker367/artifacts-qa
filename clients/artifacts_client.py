import os
import requests


BASE_URL = os.getenv("ARTIFACTS_BASE_URL", "https://api.artifactsmmo.com")


class ArtifactsClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def get(self, path: str, **kwargs):
        return self.session.get(f"{BASE_URL}{path}", **kwargs)

    def post(self, path: str, json=None, **kwargs):
        return self.session.post(f"{BASE_URL}{path}", json=json, **kwargs)
