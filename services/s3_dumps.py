"""Browse and download dump files from S3.

Config (.env). `<name>_<env>` wins for each env; the unsuffixed value is a fallback:
    AWS_ACCESS_KEY_ID_<ENV> / AWS_SECRET_ACCESS_KEY_<ENV> / AWS_REGION_<ENV>   (e.g. ..._PROD, ..._DEV)
    AWS_BUCKET_NAME_<ENV>  bucket holding the dumps          (e.g. AWS_BUCKET_NAME_PROD)
    S3_DUMP_PREFIX_<ENV>   optional key prefix to browse     (e.g. S3_DUMP_PREFIX_PROD=dumps/)

Downloads are served through short-lived presigned URLs, so the file goes straight
from S3 to the browser. Only keys under the configured prefix can be presigned.
"""
import os
import shutil
import tempfile
import zipfile
from datetime import datetime

from services.mongo_common import normalize_env

PRESIGN_TTL_SECONDS = 300
AGENT_KEY_TEMPLATE = "agents/{agent_id}/versions/{version_id}/clean_files/"
MAX_ZIP_BYTES = 1_000_000_000   # largest total size "Download all" will zip

_clients: dict = {}


class S3Error(Exception):
    pass


def _env_var(name: str, env: str) -> str:
    return (os.getenv(f"{name}_{env.upper()}") or os.getenv(f"{name}_{env}") or os.getenv(name) or "").strip()


def _client(env: str):
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise S3Error("boto3 is not installed. Run: pip install -r requirements.txt")

    key_id = _env_var("AWS_ACCESS_KEY_ID", env)
    secret = _env_var("AWS_SECRET_ACCESS_KEY", env)
    region = _env_var("AWS_REGION", env) or _env_var("AWS_DEFAULT_REGION", env)
    if not (key_id and secret and region):
        sfx = env.upper()
        raise S3Error(
            f"Missing AWS configuration for '{env}' in .env: "
            f"AWS_ACCESS_KEY_ID_{sfx} / AWS_SECRET_ACCESS_KEY_{sfx} / AWS_REGION_{sfx}"
        )

    cache_key = (key_id, region)
    if cache_key not in _clients:
        _clients[cache_key] = boto3.client(
            "s3",
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            region_name=region,
            # SigV4 + regional endpoint keeps presigned URLs valid for every region
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return _clients[cache_key]


def _location(env: str | None) -> tuple[str, str, str]:
    env = normalize_env(env)
    bucket = _env_var("AWS_BUCKET_NAME", env)
    if not bucket:
        raise S3Error(f"Missing S3 configuration for '{env}' in .env: AWS_BUCKET_NAME_{env.upper()}")
    return env, bucket, _env_var("S3_DUMP_PREFIX", env)


def _aws_call(fn, *args, **kwargs):
    from botocore.exceptions import BotoCoreError, ClientError
    try:
        return fn(*args, **kwargs)
    except ClientError as e:
        err = e.response.get("Error", {})
        raise S3Error(f"S3 error {err.get('Code', '')}: {err.get('Message', str(e))}")
    except BotoCoreError as e:
        raise S3Error(f"AWS error: {e}")


def _agent_files(env: str | None, agent_id: str, agent_version_id: str):
    """Resolve the env and list every file for one agent version (newest first).

    Keys live at <prefix>agents/{agent_id}/versions/{agent_version_id}/clean_files/..., so S3
    is asked for exactly that prefix instead of scanning the whole bucket.
    Returns (env, bucket, s3_client, scan_prefix, objects).
    """
    agent_id = (agent_id or "").strip()
    agent_version_id = (agent_version_id or "").strip()
    if not agent_id or not agent_version_id:
        raise S3Error("agent_id and agent_version_id are both required")
    for value in (agent_id, agent_version_id):
        if "/" in value or ".." in value:
            raise S3Error("agent_id and agent_version_id must not contain '/' or '..'")

    env, bucket, base_prefix = _location(env)
    s3 = _client(env)
    scan_prefix = f"{base_prefix}{AGENT_KEY_TEMPLATE.format(agent_id=agent_id, version_id=agent_version_id)}"

    objects = []

    def _scan():
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=scan_prefix):
            objects.extend(o for o in page.get("Contents", []) if not o["Key"].endswith("/"))

    _aws_call(_scan)
    objects.sort(key=lambda o: o["LastModified"], reverse=True)
    return env, bucket, s3, scan_prefix, objects


def list_dumps(env: str | None, agent_id: str, agent_version_id: str) -> dict:
    """List all dump files for one agent version (no content)."""
    env, bucket, _s3, scan_prefix, objects = _agent_files(env, agent_id, agent_version_id)
    files = [{
        "key": o["Key"],
        "name": o["Key"][len(scan_prefix):] or o["Key"],
        "size": o["Size"],
        "last_modified": o["LastModified"].isoformat(),
    } for o in objects]
    return {"env": env, "bucket": bucket, "prefix": scan_prefix, "agent_id": agent_id.strip(),
            "agent_version_id": agent_version_id.strip(), "total": len(files),
            "total_size": sum(f["size"] for f in files), "files": files}


def zip_dumps(env: str | None, agent_id: str, agent_version_id: str) -> tuple[str, str]:
    """Zip every dump file for one agent version into a temp file.

    Returns (zip_path, download_filename). The caller must delete zip_path when done.
    """
    env, bucket, s3, scan_prefix, objects = _agent_files(env, agent_id, agent_version_id)
    if not objects:
        raise S3Error("No files found for this agent ID and agent version ID")
    total = sum(o["Size"] for o in objects)
    if total > MAX_ZIP_BYTES:
        raise S3Error(f"Files total {total / 1_000_000:.0f} MB, over the {MAX_ZIP_BYTES // 1_000_000} MB "
                      "download-all limit. Download them individually.")

    fd, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for o in objects:
                arcname = o["Key"][len(scan_prefix):] or o["Key"].rsplit("/", 1)[-1]
                body = _aws_call(s3.get_object, Bucket=bucket, Key=o["Key"])["Body"]
                try:
                    with zf.open(arcname, "w", force_zip64=True) as dest:
                        shutil.copyfileobj(body, dest)
                finally:
                    body.close()
    except BaseException:
        os.remove(zip_path)
        raise
    return zip_path, f"{agent_id.strip()}_{agent_version_id.strip()}_clean_files.zip"


def presign_download(env: str | None, key: str) -> dict:
    env, bucket, prefix = _location(env)
    key = (key or "").strip()
    if not key or ".." in key.split("/") or not key.startswith(prefix):
        raise S3Error("Invalid object key for this environment")
    s3 = _client(env)
    # Confirm it exists so the user gets a clear error instead of an XML page from S3
    _aws_call(s3.head_object, Bucket=bucket, Key=key)
    filename = key.rsplit("/", 1)[-1].replace('"', "")
    url = _aws_call(
        s3.generate_presigned_url,
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )
    return {"url": url, "filename": filename, "expires_in": PRESIGN_TTL_SECONDS,
            "generated_at": datetime.utcnow().isoformat() + "Z"}
