# SPDX-FileCopyrightText: 2026 Nicholas Warila
# SPDX-License-Identifier: MIT
"""Read one deployment secret, named by URL.

WHY THIS EXISTS
    Seven tasks across two repositories each carried the same twenty-four lines of S3 module
    arguments and its own non-empty guard, differing only in bucket and object. Seven copies of one
    idea is seven places to drift, and the guard is easy to forget at a new call site.

WHY A URL
    The scheme names the backend. Secrets move to Vault later; a `vault://` term then routes to a
    new branch here and every call site keeps the shape it already has.

WHY NO CACHE
    Measured on ansible-core 2.21.2: Ansible already caches a templated variable's value for the
    run -- four references across two separate variables holding the same lookup produced ONE call.
    A cache here would be redundant, and a cached value returned before its caller's digest was
    checked would silently defeat a pin.

WHAT IT DELIBERATELY DOES NOT DO
    It does not hide a secret. The value returns as an ordinary string because that is the only
    thing Ansible can template -- the consuming task still needs `no_log: true`. Anything else
    would be theatre: the controller is Python and has no protected-memory type.

    It does not normalize the object. Whatever bytes S3 holds are what the caller receives, decoded
    as UTF-8 and otherwise untouched, because the existing consumers were written against untrimmed
    content and existing digests were computed over the stored bytes.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit

from ansible.errors import AnsibleError
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display

DOCUMENTATION = """
name: secret
short_description: Read one deployment secret, named by URL
description:
  - Returns the object at the given URL as a string, decoded UTF-8 and otherwise unmodified.
  - The URL scheme selects the backend. C(s3://bucket/key) is the only scheme carried today.
  - An object that is absent, or whose content is empty or only whitespace, is an error.
options:
  _terms:
    description:
      - The secret URL, e.g. C(s3://my-bucket/applications/pdq/svc-pdq-password.txt).
      - An optional second term is the SHA-256 the STORED BYTES must have, as 64 hex characters.
        A mismatch fails the read, so a changed object under an unchanged pin stops the play.
    required: true
    type: list
    elements: str
"""

EXAMPLES = """
- name: 'PROCESS | Ensure The Background Service User'
  no_log: true
  ansible.windows.win_user:
    name: 'svc-pdq'
    password: >-
      {{ lookup('secret',
                's3://' ~ aws_account_id ~ '-ansible/applications/pdq/svc-pdq-password.txt') }}
"""

RETURN = """
_raw:
  description: The object's content, decoded UTF-8, unmodified.
  type: list
  elements: str
"""

display = Display()

_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        self.set_options(var_options=variables, direct=kwargs)
        if not 1 <= len(terms) <= 2:
            raise AnsibleError(
                "secret lookup: give one URL, and optionally the SHA-256 of its stored bytes"
            )

        url = str(terms[0])
        expected = self._digest(terms[1], url) if len(terms) == 2 else None

        bucket, key = self._parse(url)
        raw = self._get_object(bucket, key, url)

        # The digest attests to what S3 stores, so it is taken before any decoding.
        if expected:
            actual = hashlib.sha256(raw).hexdigest()
            if actual != expected:
                # Neither digest is the secret, so naming both is safe and is the whole diagnostic.
                raise AnsibleError(
                    f"secret lookup: {url} has sha256 {actual}, expected {expected}. The stored "
                    "object changed under an unchanged pin."
                )

        try:
            secret = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AnsibleError(f"secret lookup: {url} is not valid UTF-8 ({exc})")

        # Emptiness is judged on the trimmed value; the value DELIVERED is never trimmed, because
        # the consumers this replaces were written against the stored bytes.
        if not secret.strip():
            raise AnsibleError(
                f"secret lookup: {url} is empty. Refusing to supply an empty credential."
            )

        display.vvv(f"secret lookup: read {url} ({len(raw)} bytes)")
        return [secret]

    @staticmethod
    def _digest(term, url: str) -> str:
        # A blank second term must NOT quietly mean "unpinned": the contract says a supplied digest
        # is enforced, so anything that is not a well-formed SHA-256 is invalid input.
        candidate = str(term).strip().lower()
        if not _SHA256.match(candidate):
            raise AnsibleError(
                f"secret lookup: the digest given for {url} is not a SHA-256. Expected 64 hex "
                f"characters, got {len(candidate)}."
            )
        return candidate

    @staticmethod
    def _parse(url: str) -> tuple[str, str]:
        parts = urlsplit(url)
        if parts.scheme != "s3":
            raise AnsibleError(
                f"secret lookup: '{parts.scheme or url}' is not a scheme this plugin reads. "
                "Use s3://bucket/key."
            )
        bucket, key = parts.netloc, parts.path.lstrip("/")
        if not bucket or not key:
            raise AnsibleError(f"secret lookup: '{url}' names no bucket or no key")
        return bucket, key

    @staticmethod
    def _get_object(bucket: str, key: str, url: str) -> bytes:
        # Imported here, not at module scope, so a controller without boto3 fails on the task that
        # needs a secret rather than on every play that merely loads this plugin.
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError as exc:
            raise AnsibleError(f"secret lookup: boto3 is required on the controller ({exc})")

        try:
            return boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            # The URL identifies the failure; the value never appears in an error.
            raise AnsibleError(f"secret lookup: cannot read {url}: {exc}")
