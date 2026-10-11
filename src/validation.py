"""Validation for incoming playtest reports and list queries.

No AWS imports here: these are plain functions that turn untrusted client
input into clean values, or raise ValidationError with messages that are safe
to send back to the client.
"""

import json
import math
import re
from decimal import Decimal

CATEGORIES = ("bug", "crash", "feedback")
BUILD_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_SCENE_LENGTH = 256
MAX_MESSAGE_LENGTH = 2000
MAX_GAME_STATE_LENGTH = 8192
MAX_GAME_STATE_DEPTH = 32
MAX_COORDINATE = 1_000_000
MAX_FPS = 1000
DEFAULT_LIMIT = 25
MAX_LIMIT = 100


class ValidationError(Exception):
    """Client input was invalid. Each message names the offending field."""

    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def check_build(value, name="build"):
    if not isinstance(value, str) or not BUILD_PATTERN.fullmatch(value):
        raise ValidationError(
            f"{name} must be 1-64 characters of letters, digits, '.', '_' or '-'"
        )
    return value


def check_text(name, value, max_length):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    if len(value) > max_length:
        raise ValidationError(f"{name} must be at most {max_length} characters")
    return value


def check_number(name, value, minimum, maximum):
    # bool is a subclass of int in Python, so true/false would otherwise pass.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a number")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValidationError(f"{name} must be between {minimum} and {maximum}")
    # boto3 rejects Python floats for DynamoDB, so store a Decimal. Going via
    # str() keeps 0.1 as 0.1 instead of its binary approximation.
    return Decimal(str(round(value, 3)))


def check_scene(value):
    return check_text("scene", value, MAX_SCENE_LENGTH)


def check_message(value):
    return check_text("message", value, MAX_MESSAGE_LENGTH)


def check_fps(value):
    return check_number("fps", value, 0, MAX_FPS)


def check_category(value):
    if value not in CATEGORIES:
        raise ValidationError(f"category must be one of: {', '.join(CATEGORIES)}")
    return value


def check_position(value):
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise ValidationError("position must be an object with exactly x, y and z")
    errors = []
    clean = {}
    for axis in ("x", "y", "z"):
        try:
            clean[axis] = check_number(
                f"position.{axis}", value[axis], -MAX_COORDINATE, MAX_COORDINATE
            )
        except ValidationError as err:
            errors.extend(err.errors)
    if errors:
        raise ValidationError(errors)
    return clean


def nesting_depth(value):
    """How many objects/arrays deep a parsed JSON value goes.

    Uses a loop rather than recursion, so very deep input can't make this
    check itself fail.
    """
    deepest = 0
    pending = [(value, 1)]
    while pending:
        node, depth = pending.pop()
        if isinstance(node, (dict, list)):
            deepest = max(deepest, depth)
            children = node.values() if isinstance(node, dict) else node
            pending.extend((child, depth + 1) for child in children)
    return deepest


def check_json_object(name, value, max_length, max_depth):
    # Free-form game data is stored as a JSON string rather than as typed
    # DynamoDB attributes, so it is only checked for shape, depth and size.
    if not isinstance(value, dict):
        raise ValidationError(f"{name} must be an object")
    # Without a depth limit, data nested just under Python's JSON recursion
    # limit is accepted here but can't be re-encoded inside a GET response,
    # which would break listing for that build.
    if nesting_depth(value) > max_depth:
        raise ValidationError(f"{name} must be nested at most {max_depth} levels deep")
    encoded = json.dumps(value, separators=(",", ":"))
    if len(encoded) > max_length:
        raise ValidationError(f"{name} must be at most {max_length} characters as JSON")
    return encoded


def check_game_state(value):
    # The game's state machines when the report key was pressed (including
    # the weapon's loadout and action), plus their recent changes. State names
    # change with the game, so they are not checked here: build says which
    # version of the game sent them.
    return check_json_object("gameState", value, MAX_GAME_STATE_LENGTH, MAX_GAME_STATE_DEPTH)


FIELD_CHECKS = {
    "build": check_build,
    "scene": check_scene,
    "position": check_position,
    "fps": check_fps,
    "category": check_category,
    "message": check_message,
    "gameState": check_game_state,
}
REQUIRED_FIELDS = ("build", "scene", "position", "fps", "category", "message")


def validate_report(body):
    """Validate a POST /reports body and return a clean dict ready to store.

    Collects every problem rather than stopping at the first, so the game
    developer sees all of them in one 400 response.
    """
    if not isinstance(body, dict):
        raise ValidationError("request body must be a JSON object")

    errors = []
    unknown = sorted(set(body) - set(FIELD_CHECKS))
    if unknown:
        errors.append(f"unknown field(s): {', '.join(unknown)}")
    missing = [name for name in REQUIRED_FIELDS if name not in body]
    if missing:
        errors.append(f"missing required field(s): {', '.join(missing)}")

    report = {}
    for name, check in FIELD_CHECKS.items():
        if name in body:
            try:
                report[name] = check(body[name])
            except ValidationError as err:
                errors.extend(err.errors)

    if errors:
        raise ValidationError(errors)
    return report


def validate_list_query(params):
    """Validate GET /reports query parameters.

    Returns (build, limit, next_token). next_token is passed through as an
    opaque string; the handler decodes it.
    """
    errors = []

    build = params.get("build")
    if build is None:
        errors.append("build query parameter is required")
    else:
        try:
            check_build(build)
        except ValidationError as err:
            errors.extend(err.errors)

    limit = DEFAULT_LIMIT
    raw_limit = params.get("limit")
    if raw_limit is not None:
        if raw_limit.isdecimal() and 1 <= int(raw_limit) <= MAX_LIMIT:
            limit = int(raw_limit)
        else:
            errors.append(f"limit must be a whole number from 1 to {MAX_LIMIT}")

    if errors:
        raise ValidationError(errors)
    return build, limit, params.get("nextToken")
