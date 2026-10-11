"""Lambda entry point for the playtest-reports HTTP API.

API Gateway (HTTP API, payload format 2.0) sends both routes here:
  POST /reports  store a report
  GET  /reports  list reports for one build, newest first
Both routes require the shared secret in the x-playtest-secret header.
"""

import base64
import binascii
import functools
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from validation import ValidationError, validate_list_query, validate_report

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SECRET_HEADER = "x-playtest-secret"
SECRET_CACHE_SECONDS = 300
# A guard against abuse, set well above the largest valid report (about
# 10.7 KB) so whitespace and escaping in the game's JSON never hit it. The
# per-field limits in validation.py are the real contract.
MAX_BODY_BYTES = 32 * 1024
# Fields validation stores as JSON strings, turned back into objects on read.
JSON_STRING_FIELDS = ("gameState",)

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()

# Read from SSM on first use, then kept in memory for warm invocations so we
# don't call SSM (and KMS) on every request. The TTL lets a rotated secret
# take effect within five minutes without a redeploy.
_secret_cache = {"value": None, "expires_at": 0.0}


@functools.cache
def aws_client(service):
    """One boto3 client per service, reused across warm invocations."""
    return boto3.client(service)


def lambda_handler(event, context):
    try:
        if not is_authorized(event):
            return response(401, {"error": f"missing or invalid {SECRET_HEADER} header"})

        route = event.get("routeKey")
        if route == "POST /reports":
            return create_report(event)
        if route == "GET /reports":
            return list_reports(event)
        return response(404, {"error": "not found"})

    except ValidationError as err:
        return response(400, {"error": "invalid request", "details": err.errors})
    except Exception:
        logger.exception("unhandled error")
        return response(500, {"error": "internal error"})


def is_authorized(event):
    # HTTP API payload 2.0 lowercases header names.
    provided = (event.get("headers") or {}).get(SECRET_HEADER)
    if not provided:
        return False
    # compare_digest takes the same time whether the first or last character
    # differs, so response timing doesn't leak how much of a guess was right.
    return hmac.compare_digest(provided.encode(), get_shared_secret().encode())


def get_shared_secret():
    now = time.monotonic()
    if _secret_cache["value"] is None or now >= _secret_cache["expires_at"]:
        result = aws_client("ssm").get_parameter(
            Name=os.environ["SECRET_PARAMETER_NAME"], WithDecryption=True
        )
        _secret_cache["value"] = result["Parameter"]["Value"]
        _secret_cache["expires_at"] = now + SECRET_CACHE_SECONDS
    return _secret_cache["value"]


def create_report(event):
    report = validate_report(read_json_body(event))

    created_at = utc_timestamp()
    report_id = new_report_id()
    item = {
        **report,
        # Sort key: ISO-8601 UTC timestamps sort correctly as plain strings,
        # and the id suffix keeps two reports in the same millisecond apart.
        "sk": f"{created_at}#{report_id}",
        "id": report_id,
        "createdAt": created_at,
    }
    aws_client("dynamodb").put_item(
        TableName=os.environ["TABLE_NAME"],
        Item={key: _serializer.serialize(value) for key, value in item.items()},
    )
    logger.info("stored report %s for build %s", report_id, report["build"])
    return response(201, {"id": report_id, "build": report["build"], "createdAt": created_at})


def list_reports(event):
    build, limit, next_token = validate_list_query(event.get("queryStringParameters") or {})

    params = {
        "TableName": os.environ["TABLE_NAME"],
        # "#build" is a placeholder for the attribute name, which avoids
        # clashes with DynamoDB's reserved words.
        "KeyConditionExpression": "#build = :build",
        "ExpressionAttributeNames": {"#build": "build"},
        "ExpressionAttributeValues": {":build": {"S": build}},
        "ScanIndexForward": False,  # descending sort key = newest first
        "Limit": limit,
    }
    if next_token:
        params["ExclusiveStartKey"] = {"build": {"S": build}, "sk": {"S": decode_token(next_token)}}

    result = aws_client("dynamodb").query(**params)

    reports = [to_report(item) for item in result.get("Items", [])]
    body = {"reports": reports}
    if "LastEvaluatedKey" in result:
        body["nextToken"] = encode_token(result["LastEvaluatedKey"]["sk"]["S"])
    return response(200, body)


def read_json_body(event):
    raw = event.get("body")
    if not raw:
        raise ValidationError("request body must be a JSON object")
    # API Gateway base64-encodes bodies it doesn't treat as text. Decode first
    # so the size limit applies to the JSON itself, however it arrived.
    if event.get("isBase64Encoded"):
        try:
            data = base64.b64decode(raw, validate=True)
        except binascii.Error:
            raise ValidationError("request body is not valid base64") from None
    else:
        data = raw.encode("utf-8")
    if len(data) > MAX_BODY_BYTES:
        raise ValidationError(f"request body must be at most {MAX_BODY_BYTES} bytes")
    try:
        return json.loads(data)
    except (ValueError, RecursionError):
        # ValueError covers bad syntax and invalid UTF-8; RecursionError is
        # what Python raises for very deeply nested arrays or objects.
        raise ValidationError("request body is not valid JSON") from None


def to_report(item):
    """Convert a DynamoDB item back into the JSON shape clients see."""
    report = {key: _deserializer.deserialize(value) for key, value in item.items()}
    report.pop("sk")  # internal key; id and createdAt carry the same information
    for name in JSON_STRING_FIELDS:
        if name in report:
            report[name] = json.loads(report[name])
    return report


def encode_token(sort_key):
    # Opaque to clients and safe in a URL. Only the sort key is needed
    # because the build comes from the query string.
    return base64.urlsafe_b64encode(sort_key.encode()).decode().rstrip("=")


def decode_token(token):
    # Reject anything that isn't a token we issued before it reaches DynamoDB:
    # real tokens are about 84 characters and decode to "<timestamp>#<id>".
    sort_key = ""
    if len(token) <= 200:
        try:
            padded = token + "=" * (-len(token) % 4)
            sort_key = base64.b64decode(padded, altchars="-_", validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            pass
    if "#" not in sort_key:
        raise ValidationError("nextToken is invalid")
    return sort_key


def utc_timestamp():
    """Current UTC time to the millisecond, e.g. 2026-10-11T15:30:00.123Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_report_id():
    return str(uuid.uuid4())


def response(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }


def _json_default(value):
    # DynamoDB returns every number as Decimal, which json can't serialize.
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")
