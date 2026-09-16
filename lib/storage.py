import os
from urllib.parse import quote, unquote

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

S3_CLIENT_CONFIG = Config(
    signature_version="s3v4",
    s3={"addressing_style": "virtual"},
)
_bucket_region = None


def _required(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"Missing {name} in .env or Streamlit secrets. Add S3_BUCKET, AWS_REGION, and AWS credentials."
        )
    return value


def s3_config() -> dict:
    return {
        "bucket": _required("S3_BUCKET"),
        "region": os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1",
        "prefix": (os.getenv("S3_PREFIX") or "startup-form").strip().strip("/"),
        "access_key": os.getenv("AWS_ACCESS_KEY_ID") or None,
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY") or None,
    }


def _raw_client(region: str, access_key: str | None, secret_key: str | None):
    kwargs = {
        "region_name": region,
        "config": S3_CLIENT_CONFIG,
        "endpoint_url": f"https://s3.{region}.amazonaws.com",
    }
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


def _normalize_region(value: str | None) -> str:
    if not value:
        return "us-east-1"
    if value == "EU":
        return "eu-west-1"
    return value


def resolve_bucket_region(cfg: dict) -> str:
    global _bucket_region
    if _bucket_region:
        return _bucket_region
    guessed = _normalize_region((cfg["region"] or "us-east-1").strip())
    probe = _raw_client(guessed, cfg["access_key"], cfg["secret_key"])
    try:
        loc = probe.get_bucket_location(Bucket=cfg["bucket"])
        _bucket_region = _normalize_region(loc.get("LocationConstraint"))
        return _bucket_region
    except ClientError as exc:
        headers = (exc.response.get("ResponseMetadata") or {}).get("HTTPHeaders") or {}
        header_region = headers.get("x-amz-bucket-region")
        if header_region:
            _bucket_region = _normalize_region(header_region)
            return _bucket_region
        raise RuntimeError(f"Could not determine S3 bucket region: {exc}") from exc


def s3_client():
    cfg = s3_config()
    region = resolve_bucket_region(cfg)
    cfg["region"] = region
    return _raw_client(region, cfg["access_key"], cfg["secret_key"]), cfg


def object_key(stored_filename: str) -> str:
    cfg = s3_config()
    return f"{cfg['prefix']}/{stored_filename}"


def s3_uri(key: str, bucket: str | None = None) -> str:
    return f"s3://{bucket or s3_config()['bucket']}/{key}"


def upload_bytes(stored_filename: str, content: bytes, content_type: str | None) -> dict:
    client, cfg = s3_client()
    key = object_key(stored_filename)
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    try:
        client.put_object(Bucket=cfg["bucket"], Key=key, Body=content, **extra)
    except ClientError as exc:
        code = (exc.response.get("Error") or {}).get("Code") or ""
        if code in {"NoSuchBucket", "404"}:
            raise RuntimeError(
                f"S3 bucket {cfg['bucket']!r} does not exist. Create it in AWS or set S3_BUCKET to an existing bucket."
            ) from exc
        raise RuntimeError(f"S3 upload failed: {exc}") from exc
    except BotoCoreError as exc:
        raise RuntimeError(f"S3 upload failed: {exc}") from exc
    return {
        "key": key,
        "path": s3_uri(key, cfg["bucket"]),
        "url": f"/api/files/{stored_filename}",
    }


def stored_name_from_path(path: str) -> str:
    text = (path or "").strip()
    if text.startswith("/api/files/"):
        return unquote(text.rsplit("/", 1)[-1])
    if text.startswith("s3://"):
        without = text[5:]
        _, _, key = without.partition("/")
        return key.rsplit("/", 1)[-1]
    return text.rsplit("/", 1)[-1]


def presigned_url(stored_filename: str, download_name: str | None = None) -> str:
    client, cfg = s3_client()
    key = object_key(stored_filename)
    params = {"Bucket": cfg["bucket"], "Key": key}
    if download_name:
        safe_name = quote(download_name.replace("\r", "").replace("\n", ""), safe="._-")
        params["ResponseContentDisposition"] = f"attachment; filename=\"{safe_name}\""
    try:
        return client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=3600,
        )
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"Could not create S3 download link: {exc}") from exc
