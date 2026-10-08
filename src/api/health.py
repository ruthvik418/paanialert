import json


def handler(event, context):
    """Smoke test for a fresh deploy: GET /health returns {"ok": true}."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": True}),
    }
