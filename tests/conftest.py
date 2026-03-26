import os
import pytest
from dotenv import load_dotenv
from clients.artifacts_client import ArtifactsClient

load_dotenv()


@pytest.fixture(scope="session")
def client():
    token = os.getenv("ARTIFACTS_TOKEN")
    assert token, "ARTIFACTS_TOKEN not set in .env"
    return ArtifactsClient(token)


@pytest.fixture(scope="session")
def character_name():
    name = os.getenv("ARTIFACTS_CHARACTER")
    assert name, "ARTIFACTS_CHARACTER not set in .env"
    return name
