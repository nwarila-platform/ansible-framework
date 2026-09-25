from __future__ import annotations

from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from botocore.awsrequest import AWSResponse


class RawResponse:
    def __init__(self, body: bytes):
        self.body = BytesIO(body)

    def stream(self, amount=1024, decode_content=False):
        del decode_content
        while True:
            chunk = self.body.read(amount)
            if not chunk:
                return
            yield chunk


class Pill:
    def __init__(self, session):
        self.session = session

    def record(self):
        self.session._session.register("before-send", before_send)


def attach(session, data_path=None):
    del data_path
    return Pill(session)


def decode_aws_chunks(payload):
    decoded = bytearray()
    remaining = payload
    while remaining:
        header, separator, remainder = remaining.partition(b"\r\n")
        if not separator:
            return payload
        try:
            size = int(header.split(b";", 1)[0], 16)
        except ValueError:
            return payload
        if size == 0:
            return bytes(decoded)
        decoded.extend(remainder[:size])
        remaining = remainder[size:]
        if not remaining.startswith(b"\r\n"):
            return payload
        remaining = remaining[2:]
    return bytes(decoded)


def before_send(request, **kwargs):
    del kwargs
    authorization = request.headers.get("Authorization", b"")
    if isinstance(authorization, bytes):
        authorization = authorization.decode(errors="replace")
    token = request.headers.get("X-Amz-Security-Token", b"")
    if isinstance(token, bytes):
        token = token.decode(errors="replace")
    credential = ""
    if "Credential=" in authorization:
        credential = authorization.split("Credential=", 1)[1].split("/", 1)[0]
    target = request.headers.get("X-Amz-Target", b"")
    if isinstance(target, bytes):
        target = target.decode(errors="replace")
    url = urlparse(request.url)
    session_target = None
    if "StartSession" in target:
        session_target = json.loads(request.body).get("Target")
    record = {
        "kind": "before-send",
        "url": request.url,
        "method": request.method,
        "target": target,
        "session_target": session_target,
        "signing_access_key_id": credential,
        "security_token_present": bool(token),
        "security_token_sha256": hashlib.sha256(token.encode()).hexdigest() if token else None,
        "answered": url.scheme == "https" and (url.hostname or "").endswith(".invalid"),
    }
    with Path(os.environ["CREDRES_PLACEBO_LOG"]).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    if not record["answered"]:
        raise RuntimeError(f"refused a request outside https://*.invalid: {url.hostname}")
    object_path = url.path.lstrip("/").replace("/", "_")
    store_path = Path(os.environ["CREDRES_STORE"]) / object_path
    if request.method == "PUT" and object_path:
        body = request.body
        if isinstance(body, str):
            payload = body.encode()
        elif isinstance(body, bytes):
            payload = body
        elif hasattr(body, "read"):
            position = body.tell() if hasattr(body, "tell") else None
            payload = body.read()
            if position is not None and hasattr(body, "seek"):
                body.seek(position)
        else:
            payload = bytes(body or b"")
        store_path.write_bytes(decode_aws_chunks(payload))
    elif request.method == "DELETE" and object_path:
        store_path.unlink(missing_ok=True)
    headers = {"content-type": "application/x-amz-json-1.1", "x-amz-bucket-region": "us-test-1"}
    if not target:
        body = b""
    elif "StartSession" in target:
        body = json.dumps({
            "SessionId": "session-IDENTITY-CANARY",
            "StreamUrl": "wss://stream.invalid/session",
            "TokenValue": "DERIVED-SESSION-TOKEN",
        }).encode()
    else:
        body = b"{}"
    return AWSResponse(request.url, 200, headers, RawResponse(body))
