# Cooldown is a core game mechanic in Artifacts MMO, not just rate limiting.
# Every character action returns cooldown data in the response body.
# These helpers make cooldown state readable and reusable across services.

# HTTP status code the API returns when a character is still in cooldown
COOLDOWN_STATUS_CODE = 499


def is_on_cooldown(response) -> bool:
    """
    Return True if the API rejected the action because the character is on cooldown.
    Use this to distinguish cooldown from other failures without hardcoding 499 everywhere.
    """
    return response.status_code == COOLDOWN_STATUS_CODE


def parse_cooldown(response) -> dict | None:
    """
    Extract cooldown data from a successful action response.
    Artifacts includes cooldown info in the 'data.cooldown' field after every action.
    Returns None if the response has no cooldown data (e.g. GET requests, error responses).
    """
    try:
        return response.json().get("data", {}).get("cooldown")
    except Exception:
        return None


def remaining_seconds(response) -> float | None:
    """
    Return remaining cooldown seconds from an action response, or None if not present.
    Useful for logging how long until the character can act again.
    """
    cooldown = parse_cooldown(response)
    if cooldown is None:
        return None
    return cooldown.get("remaining_seconds")
