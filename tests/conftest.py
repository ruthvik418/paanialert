"""Shared test setup: a fake AWS (moto) with the same tables, queue, bucket and secrets."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.update({
    "AWS_DEFAULT_REGION": "ap-south-1",
    "AWS_REGION": "ap-south-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "REPORTS_TABLE": "Reports",
    "CLUSTERS_TABLE": "Clusters",
    "SUBSCRIBERS_TABLE": "Subscribers",
    "NOTICES_TABLE": "Notices",
    "SESSIONS_TABLE": "Sessions",
    "MEDIA_BUCKET": "media-test",
})
os.environ.pop("AWS_PROFILE", None)

SECRETS = {
    "twilio_account_sid": "ACtest",
    "twilio_auth_token": "test-token",
    "hmac_secret": "test-hmac",
    "dashboard_key": "test-dashboard-key",
}


def _table(ddb, name, key, indexes=(), extra_attrs=()):
    attrs = {key, *extra_attrs}
    spec = dict(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in sorted(attrs)],
        KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
    )
    if indexes:
        spec["GlobalSecondaryIndexes"] = list(indexes)
    ddb.create_table(**spec)


@pytest.fixture
def aws():
    from moto import mock_aws

    with mock_aws():
        import boto3

        ddb = boto3.client("dynamodb", region_name="ap-south-1")
        _table(ddb, "Reports", "report_id", extra_attrs=("geohash6", "created_at"), indexes=[{
            "IndexName": "geo-time",
            "KeySchema": [{"AttributeName": "geohash6", "KeyType": "HASH"},
                          {"AttributeName": "created_at", "KeyType": "RANGE"}],
            "Projection": {"ProjectionType": "ALL"},
        }])
        _table(ddb, "Clusters", "cluster_id")
        _table(ddb, "Subscribers", "phone_hash", extra_attrs=("geohash6",), indexes=[{
            "IndexName": "by-cell",
            "KeySchema": [{"AttributeName": "geohash6", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
        }])
        _table(ddb, "Notices", "geohash6")
        _table(ddb, "Sessions", "phone_hash")

        ssm = boto3.client("ssm", region_name="ap-south-1")
        for name, value in SECRETS.items():
            ssm.put_parameter(Name="/paanialert/" + name, Value=value, Type="SecureString")

        queue_url = boto3.client("sqs", region_name="ap-south-1").create_queue(QueueName="incoming")["QueueUrl"]
        os.environ["INCOMING_QUEUE_URL"] = queue_url
        boto3.client("s3", region_name="ap-south-1").create_bucket(
            Bucket="media-test", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
        )

        from common import config, db
        import webhook.app as webhook_app

        config.secret.cache_clear()
        db._resource = None
        webhook_app._sqs = None
        yield
        config.secret.cache_clear()
        db._resource = None
        webhook_app._sqs = None
