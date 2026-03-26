# Centralized API error handling for Artifacts MMO.
# Artifacts returns domain-specific HTTP codes — we map them to readable errors
# so tests and services don't manually inspect status codes everywhere.

# Documented Artifacts API error codes
AUTH_INVALID = 452
AUTH_EXPIRED = 453
AUTH_MISSING = 454
UNPROCESSABLE = 422
RATE_LIMITED = 429
ALREADY_AT_DESTINATION = 490
INVENTORY_FULL = 497
CHARACTER_NOT_FOUND = 498
ON_COOLDOWN = 499
MISSING_ITEM = 478     # action requires items the character does not have (e.g. task cancel costs task coin)
CHARACTER_LOCKED = 486
NO_TASK = 487          # character has no task assigned
TASK_NOT_COMPLETE = 488  # task is active but objective not yet met
INSUFFICIENT_GOLD = 492
SKILL_LEVEL_TOO_LOW = 493

# Human-readable labels for known error codes
_ERROR_LABELS = {
    AUTH_INVALID: "invalid token",
    AUTH_EXPIRED: "token expired",
    AUTH_MISSING: "token missing",
    UNPROCESSABLE: "invalid payload",
    RATE_LIMITED: "rate limit exceeded",
    ALREADY_AT_DESTINATION: "character already at destination",
    INVENTORY_FULL: "character inventory full",
    CHARACTER_NOT_FOUND: "character not found",
    ON_COOLDOWN: "character is on cooldown",
    CHARACTER_LOCKED: "character is locked",
    MISSING_ITEM: "missing required item(s) for this action",
    NO_TASK: "no task assigned",
    TASK_NOT_COMPLETE: "task objective not yet met",
    INSUFFICIENT_GOLD: "not enough gold",
    SKILL_LEVEL_TOO_LOW: "skill level too low for this craft",
}


class ArtifactsApiError(Exception):
    """Raised when the API returns a recognized error response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"[{status_code}] {message}")


def describe_status(status_code: int) -> str:
    """Return a human-readable description for a known Artifacts error code."""
    return _ERROR_LABELS.get(status_code, f"unexpected status {status_code}")


def parse_api_error(response) -> ArtifactsApiError:
    """
    Build an ArtifactsApiError from a failed response.
    Tries to extract the API error message from the response body first,
    falls back to the known label for the status code.
    """
    label = describe_status(response.status_code)
    try:
        body = response.json()
        # Artifacts wraps errors in {"error": {"message": "..."}}
        api_message = body.get("error", {}).get("message", label)
    except Exception:
        api_message = label

    return ArtifactsApiError(status_code=response.status_code, message=api_message)
