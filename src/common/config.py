"""Settings and secrets.

Secrets live in SSM Parameter Store under /paanialert/ and are read once per
Lambda cold start, then cached. Never put a secret in code or in template.yaml.
"""
import os
from functools import lru_cache

import boto3

SSM_PREFIX = os.environ.get("SSM_PREFIX", "/paanialert/")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

# The parameters every environment needs (see README → Getting started).
SECRET_NAMES = ("twilio_account_sid", "twilio_auth_token", "hmac_secret", "dashboard_key")

TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")


@lru_cache(maxsize=None)
def secret(name: str) -> str:
    """Return a SecureString parameter, e.g. secret("twilio_auth_token")."""
    ssm = boto3.client("ssm", region_name=REGION)
    response = ssm.get_parameter(Name=SSM_PREFIX + name, WithDecryption=True)
    return response["Parameter"]["Value"]


def table(name: str) -> str:
    """Physical DynamoDB table name, passed in by template.yaml as <NAME>_TABLE."""
    return os.environ[f"{name.upper()}_TABLE"]
