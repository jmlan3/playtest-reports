from decimal import Decimal

import pytest

from validation import ValidationError, validate_list_query, validate_report

VALID = {
    "build": "0.4.2",
    "scene": "res://levels/forest.tscn",
    "position": {"x": 12.5, "y": 0, "z": -3.25},
    "fps": 58.2,
    "category": "bug",
    "message": "Fell through the floor near the bridge",
    "gameState": {
        "v": 1,
        "weapon": {"name": "shotgun", "ammo": 4, "action": "Reloading/Default", "aim": "Hip"},
    },
}

BUILD_ERROR = "build must be 1-64 characters of letters, digits, '.', '_' or '-'"


def test_valid_report_is_converted_for_dynamodb():
    report = validate_report(VALID)

    assert report["position"] == {"x": Decimal("12.5"), "y": Decimal("0"), "z": Decimal("-3.25")}
    assert report["fps"] == Decimal("58.2")
    assert report["gameState"] == (
        '{"v":1,"weapon":{"name":"shotgun","ammo":4,"action":"Reloading/Default","aim":"Hip"}}'
    )


def test_game_state_is_optional():
    body = {key: value for key, value in VALID.items() if key != "gameState"}

    assert "gameState" not in validate_report(body)


def test_weapon_state_is_no_longer_a_top_level_field():
    # The weapon now lives inside gameState.
    with pytest.raises(ValidationError) as caught:
        validate_report({**VALID, "weaponState": {"weapon": "shotgun"}})

    assert caught.value.errors == ["unknown field(s): weaponState"]


def test_game_state_has_room_for_recent_history():
    # Room for the recent-history list the game sends with its snapshot.
    game_state = {"recent": "x" * 5000}

    report = validate_report({**VALID, "gameState": game_state})

    assert report["gameState"] == f'{{"recent":"{"x" * 5000}"}}'


def nested(levels, kind=dict):
    """Objects ({"a": {"a": {}}}) or arrays ([[[]]]) nested exactly `levels` deep."""
    value = kind()
    for _ in range(levels - 1):
        value = {"a": value} if kind is dict else [value]
    return value


def test_game_state_may_nest_up_to_the_depth_limit():
    report = validate_report({**VALID, "gameState": nested(32)})

    assert report["gameState"].count("{") == 32


def test_numbers_are_rounded_to_three_decimal_places():
    report = validate_report({**VALID, "position": {"x": 1.23456, "y": 0, "z": 0}})

    assert report["position"]["x"] == Decimal("1.235")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("build", "", BUILD_ERROR),
        ("build", "0.4.2 beta", BUILD_ERROR),
        ("build", "x" * 65, BUILD_ERROR),
        ("scene", "   ", "scene must be a non-empty string"),
        ("message", "x" * 2001, "message must be at most 2000 characters"),
        ("category", "Bug", "category must be one of: bug, crash, feedback"),
        ("fps", True, "fps must be a number"),
        ("fps", "60", "fps must be a number"),
        ("fps", -1, "fps must be between 0 and 1000"),
        ("fps", float("nan"), "fps must be between 0 and 1000"),
        ("position", [1, 2, 3], "position must be an object with exactly x, y and z"),
        ("position", {"x": 1, "y": 2}, "position must be an object with exactly x, y and z"),
        ("position", {"x": 1, "y": 2, "z": "3"}, "position.z must be a number"),
        ("position", {"x": 1, "y": 2e7, "z": 3}, "position.y must be between -1000000 and 1000000"),
        ("gameState", ["Grounded/Idle"], "gameState must be an object"),
        ("gameState", nested(33), "gameState must be nested at most 32 levels deep"),
        ("gameState", {"a": nested(32, list)}, "gameState must be nested at most 32 levels deep"),
        ("gameState", None, "gameState must be an object"),
        ("gameState", {"recent": "x" * 8200}, "gameState must be at most 8192 characters as JSON"),
    ],
)
def test_invalid_field_is_rejected_with_a_clear_message(field, value, error):
    with pytest.raises(ValidationError) as caught:
        validate_report({**VALID, field: value})

    assert caught.value.errors == [error]


def test_every_problem_is_reported_at_once():
    with pytest.raises(ValidationError) as caught:
        validate_report({"build": "0.4.2", "fps": -5, "color": "red"})

    assert caught.value.errors == [
        "unknown field(s): color",
        "missing required field(s): scene, position, category, message",
        "fps must be between 0 and 1000",
    ]


def test_body_must_be_an_object():
    with pytest.raises(ValidationError) as caught:
        validate_report([VALID])

    assert caught.value.errors == ["request body must be a JSON object"]


def test_list_query_defaults():
    assert validate_list_query({"build": "0.4.2"}) == ("0.4.2", 25, None)


def test_list_query_accepts_limit_and_next_token():
    params = {"build": "0.4.2", "limit": "10", "nextToken": "abc"}

    assert validate_list_query(params) == ("0.4.2", 10, "abc")


def test_list_query_requires_build():
    with pytest.raises(ValidationError) as caught:
        validate_list_query({})

    assert caught.value.errors == ["build query parameter is required"]


@pytest.mark.parametrize("limit", ["0", "101", "-1", "ten", "1.5"])
def test_list_query_rejects_bad_limit(limit):
    with pytest.raises(ValidationError) as caught:
        validate_list_query({"build": "0.4.2", "limit": limit})

    assert caught.value.errors == ["limit must be a whole number from 1 to 100"]
