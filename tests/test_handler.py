"""Handler tests with DynamoDB and SSM stubbed out.

botocore's Stubber sits inside a real boto3 client. Each test queues the exact
request it expects and the response to return. The Stubber fails the call if
the handler sends anything different, and no request ever leaves the machine,
so these tests need no AWS credentials.
"""

import base64
import json

import boto3
import pytest
from botocore.stub import Stubber

import handler
import validation

TABLE = "playtest-reports-test"
PARAMETER = "/playtest-reports/shared-secret"
SECRET = "test-secret"
TIMESTAMP = "2026-10-11T15:30:00.123Z"
REPORT_ID = "0b6f7d1e-3c1a-4e5b-9a7d-2f4c8e6a1b3c"

REPORT = {
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

# The same report as DynamoDB's typed JSON: S = string, N = number, M = map.
ITEM = {
    "build": {"S": "0.4.2"},
    "sk": {"S": f"{TIMESTAMP}#{REPORT_ID}"},
    "id": {"S": REPORT_ID},
    "createdAt": {"S": TIMESTAMP},
    "scene": {"S": "res://levels/forest.tscn"},
    "position": {"M": {"x": {"N": "12.5"}, "y": {"N": "0"}, "z": {"N": "-3.25"}}},
    "fps": {"N": "58.2"},
    "category": {"S": "bug"},
    "message": {"S": "Fell through the floor near the bridge"},
    "gameState": {
        "S": '{"v":1,"weapon":{"name":"shotgun","ammo":4,"action":"Reloading/Default","aim":"Hip"}}'
    },
}


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", TABLE)
    monkeypatch.setenv("SECRET_PARAMETER_NAME", PARAMETER)
    # Pin the generated values so the expected DynamoDB item is predictable.
    monkeypatch.setattr(handler, "utc_timestamp", lambda: TIMESTAMP)
    monkeypatch.setattr(handler, "new_report_id", lambda: REPORT_ID)
    # Each test starts with an empty secret cache.
    monkeypatch.setitem(handler._secret_cache, "value", None)
    monkeypatch.setitem(handler._secret_cache, "expires_at", 0.0)


@pytest.fixture(autouse=True)
def aws(monkeypatch):
    # Fake credentials stop boto3 from looking up whatever AWS login is on
    # this machine; the Stubber answers before anything is signed or sent.
    session = boto3.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing", region_name="us-east-1"
    )
    clients = {"dynamodb": session.client("dynamodb"), "ssm": session.client("ssm")}
    monkeypatch.setattr(handler, "aws_client", clients.__getitem__)
    stubbers = {name: Stubber(client) for name, client in clients.items()}
    for stubber in stubbers.values():
        stubber.activate()

    yield stubbers

    for stubber in stubbers.values():
        stubber.assert_no_pending_responses()  # every queued call was made
        stubber.deactivate()


def expect_secret_lookup(aws):
    aws["ssm"].add_response(
        "get_parameter",
        {"Parameter": {"Name": PARAMETER, "Type": "SecureString", "Value": SECRET}},
        {"Name": PARAMETER, "WithDecryption": True},
    )


def query_params(**overrides):
    return {
        "TableName": TABLE,
        "KeyConditionExpression": "#build = :build",
        "ExpressionAttributeNames": {"#build": "build"},
        "ExpressionAttributeValues": {":build": {"S": "0.4.2"}},
        "ScanIndexForward": False,
        "Limit": 25,
        **overrides,
    }


def make_event(route, body=None, query=None, secret=SECRET):
    """A minimal API Gateway HTTP API (payload 2.0) event."""
    headers = {"content-type": "application/json"}
    if secret is not None:
        headers["x-playtest-secret"] = secret
    return {
        "version": "2.0",
        "routeKey": route,
        "headers": headers,
        "queryStringParameters": query,
        "body": None if body is None else json.dumps(body),
        "isBase64Encoded": False,
    }


def as_base64(event):
    """The same event as API Gateway sends it when it treats the body as binary."""
    return {
        **event,
        "body": base64.b64encode(event["body"].encode()).decode(),
        "isBase64Encoded": True,
    }


def call(event):
    result = handler.lambda_handler(event, None)
    return result["statusCode"], json.loads(result["body"])


# POST /reports


def test_post_stores_report_and_returns_201(aws):
    expect_secret_lookup(aws)
    aws["dynamodb"].add_response("put_item", {}, {"TableName": TABLE, "Item": ITEM})

    status, body = call(make_event("POST /reports", REPORT))

    assert status == 201
    assert body == {"id": REPORT_ID, "build": "0.4.2", "createdAt": TIMESTAMP}


def test_post_accepts_base64_encoded_body(aws):
    expect_secret_lookup(aws)
    aws["dynamodb"].add_response("put_item", {}, {"TableName": TABLE, "Item": ITEM})

    status, _ = call(as_base64(make_event("POST /reports", REPORT)))

    assert status == 201


def test_post_with_invalid_fields_returns_400_listing_every_problem(aws):
    expect_secret_lookup(aws)
    bad = {**REPORT, "position": {"x": 1, "y": 2}, "fps": "fast", "category": "typo", "extra": 1}

    status, body = call(make_event("POST /reports", bad))

    # No put_item was queued, so reaching DynamoDB would fail the test.
    assert status == 400
    assert body == {
        "error": "invalid request",
        "details": [
            "unknown field(s): extra",
            "position must be an object with exactly x, y and z",
            "fps must be a number",
            "category must be one of: bug, crash, feedback",
        ],
    }


@pytest.mark.parametrize("base64_encoded", [False, True])
def test_post_accepts_every_field_at_its_limit(aws, base64_encoded):
    # The body cap has to leave room for every field at its own maximum,
    # including when API Gateway delivers the body base64-encoded.
    expect_secret_lookup(aws)
    aws["dynamodb"].add_response("put_item", {})  # the item's shape is checked above
    wrapper = len('{"notes":""}')
    report = {
        **REPORT,
        "build": "b" * 64,
        "scene": "s" * validation.MAX_SCENE_LENGTH,
        "message": "m" * validation.MAX_MESSAGE_LENGTH,
        "gameState": {"notes": "g" * (validation.MAX_GAME_STATE_LENGTH - wrapper)},
    }
    event = make_event("POST /reports", report)

    status, _ = call(as_base64(event) if base64_encoded else event)

    assert status == 201


def test_post_with_malformed_json_returns_400(aws):
    expect_secret_lookup(aws)
    event = make_event("POST /reports")
    event["body"] = "{not json"

    status, body = call(event)

    assert status == 400
    assert body["details"] == ["request body is not valid JSON"]


def test_post_with_oversized_body_returns_400(aws):
    expect_secret_lookup(aws)
    event = make_event("POST /reports")
    # Two UTF-8 bytes per character, so this is over the limit in bytes but
    # under it in characters.
    event["body"] = "é" * (handler.MAX_BODY_BYTES // 2 + 1)

    status, body = call(event)

    assert status == 400
    assert body["details"] == ["request body must be at most 32768 bytes"]


def test_size_limit_applies_after_base64_decoding(aws):
    # About 30 KB of JSON fits the 32 KB limit even though its base64 form
    # (about 40 KB) doesn't. Getting a message-length error back, rather
    # than a body-size one, shows the size check measured the decoded JSON.
    expect_secret_lookup(aws)
    event = as_base64(make_event("POST /reports", {**REPORT, "message": "m" * 30_000}))

    status, body = call(event)

    assert status == 400
    assert body["details"] == ["message must be at most 2000 characters"]


def test_post_with_deeply_nested_json_returns_400(aws):
    expect_secret_lookup(aws)
    event = make_event("POST /reports")
    event["body"] = "[" * 5000 + "]" * 5000

    status, body = call(event)

    assert status == 400
    assert body["details"] == ["request body is not valid JSON"]


def test_dynamodb_failure_returns_generic_500(aws):
    expect_secret_lookup(aws)
    aws["dynamodb"].add_client_error(
        "put_item", service_error_code="InternalServerError", http_status_code=500
    )

    status, body = call(make_event("POST /reports", REPORT))

    assert status == 500
    assert body == {"error": "internal error"}


# Shared secret


def test_missing_secret_returns_401_without_calling_ssm(aws):
    # Nothing is queued for SSM, so a lookup would fail the test.
    status, body = call(make_event("POST /reports", REPORT, secret=None))

    assert status == 401
    assert body == {"error": "missing or invalid x-playtest-secret header"}


def test_wrong_secret_returns_401(aws):
    expect_secret_lookup(aws)

    status, _ = call(make_event("GET /reports", query={"build": "0.4.2"}, secret="wrong"))

    assert status == 401


def test_secret_is_fetched_once_and_cached(aws):
    expect_secret_lookup(aws)  # queued once, used by both requests
    for _ in range(2):
        aws["dynamodb"].add_response("put_item", {}, {"TableName": TABLE, "Item": ITEM})

    assert call(make_event("POST /reports", REPORT))[0] == 201
    assert call(make_event("POST /reports", REPORT))[0] == 201


# GET /reports


def test_get_returns_reports_newest_first(aws):
    expect_secret_lookup(aws)
    aws["dynamodb"].add_response("query", {"Items": [ITEM]}, query_params())

    status, body = call(make_event("GET /reports", query={"build": "0.4.2"}))

    assert status == 200
    assert body == {"reports": [{**REPORT, "id": REPORT_ID, "createdAt": TIMESTAMP}]}


def test_get_pages_with_next_token(aws):
    expect_secret_lookup(aws)
    last_key = {"build": {"S": "0.4.2"}, "sk": {"S": f"{TIMESTAMP}#{REPORT_ID}"}}
    aws["dynamodb"].add_response(
        "query", {"Items": [ITEM], "LastEvaluatedKey": last_key}, query_params(Limit=1)
    )
    aws["dynamodb"].add_response(
        "query", {"Items": []}, query_params(Limit=1, ExclusiveStartKey=last_key)
    )

    _, first_page = call(make_event("GET /reports", query={"build": "0.4.2", "limit": "1"}))
    token = first_page["nextToken"]
    status, second_page = call(
        make_event("GET /reports", query={"build": "0.4.2", "limit": "1", "nextToken": token})
    )

    assert status == 200
    assert second_page == {"reports": []}


def test_get_without_build_returns_400(aws):
    expect_secret_lookup(aws)

    status, body = call(make_event("GET /reports"))

    assert status == 400
    assert body["details"] == ["build query parameter is required"]


@pytest.mark.parametrize("token", ["!!!", "a", "bm8taGFzaA", "x" * 300])
def test_get_with_invalid_next_token_returns_400(aws, token):
    expect_secret_lookup(aws)

    status, body = call(make_event("GET /reports", query={"build": "0.4.2", "nextToken": token}))

    assert status == 400
    assert body["details"] == ["nextToken is invalid"]
