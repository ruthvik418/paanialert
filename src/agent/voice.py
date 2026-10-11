"""Voice notes to text with Amazon Transcribe (batch). Owner: B.

transcribe() starts one job on an audio file already in the media bucket,
letting Transcribe pick Hindi or Indian English, polls every 2 s for up to
60 s, and returns (text, language_code), e.g. ("नल का पानी पीला है", "hi-IN").
The transcript JSON is written to the same bucket under transcripts/, which the
bucket's 7-day lifecycle rule deletes like everything else.

It never raises: a failed, slow or silent recording gives None, and the caller
falls back to asking the person to type.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

import boto3

from common.config import REGION

log = logging.getLogger(__name__)

LANGUAGE_OPTIONS = ["hi-IN", "en-IN"]
POLL_SECONDS = 2
MAX_WAIT_SECONDS = 60
OUTPUT_PREFIX = "transcripts/"
_clients: dict[str, object] = {}
_sleep = time.sleep   # replaced in tests


def _client(service: str):
    if service not in _clients:
        _clients[service] = boto3.client(service, region_name=REGION)
    return _clients[service]


def transcribe(bucket: str, key: str, media_format: str) -> tuple[str, str] | None:
    """(text, language_code) for the recording at s3://bucket/key, or None if there's nothing usable."""
    job = f"paanialert-{uuid.uuid4().hex}"
    try:
        _client("transcribe").start_transcription_job(
            TranscriptionJobName=job,
            Media={"MediaFileUri": f"s3://{bucket}/{key}"},
            MediaFormat=media_format,
            IdentifyLanguage=True,
            LanguageOptions=LANGUAGE_OPTIONS,
            OutputBucketName=bucket,
            OutputKey=f"{OUTPUT_PREFIX}{job}.json",
        )
        for _ in range(MAX_WAIT_SECONDS // POLL_SECONDS):
            _sleep(POLL_SECONDS)
            found = _client("transcribe").get_transcription_job(TranscriptionJobName=job)["TranscriptionJob"]
            status = found["TranscriptionJobStatus"]
            if status == "FAILED":
                log.warning("transcription %s failed: %s", job, found.get("FailureReason", "")[:200])
                return None
            if status == "COMPLETED":
                return _result(bucket, f"{OUTPUT_PREFIX}{job}.json", found.get("LanguageCode") or "")
        log.warning("transcription %s not done after %d s", job, MAX_WAIT_SECONDS)
    except Exception as exc:
        log.warning("transcription of %s failed: %s: %s", key, type(exc).__name__, str(exc)[:300])
    return None


def _result(bucket: str, key: str, language_code: str) -> tuple[str, str] | None:
    body = _client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    results = json.loads(body).get("results") or {}
    text = " ".join(t.get("transcript", "") for t in results.get("transcripts") or []).strip()
    if not text:
        log.info("transcription was empty")
        return None
    return text, language_code or results.get("language_code") or ""
