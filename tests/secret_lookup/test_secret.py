# SPDX-FileCopyrightText: 2026 Nicholas Warila
# SPDX-License-Identifier: MIT
"""Prove the secret lookup preserves and verifies the stored bytes.

The fixture replaces the controller's S3 dependencies so every failure mode is deterministic and
the suite cannot use credentials or the network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ansible.errors import AnsibleError


FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(FIXTURES_PATH))

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402


PLUGIN_PATH = Path(__file__).resolve().parents[2] / "lookup_plugins" / "secret.py"
PLUGIN_SPEC = importlib.util.spec_from_file_location("secret_lookup", PLUGIN_PATH)
SECRET = importlib.util.module_from_spec(PLUGIN_SPEC)
PLUGIN_SPEC.loader.exec_module(SECRET)

URL = "s3://fixture-bucket/applications/fixture/credential.txt"


class Body:
    def __init__(self, value: bytes):
        self.value = value

    def read(self):
        return self.value


class S3Client:
    def __init__(self, value: bytes = b"fixture-secret\n", error=None):
        self.value = value
        self.error = error
        self.calls = []

    def get_object(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"Body": Body(self.value)}


class SecretLookupTest(unittest.TestCase):
    def setUp(self):
        boto3.CLIENT = S3Client()

    @staticmethod
    def _run(terms):
        lookup = SECRET.LookupModule()
        with patch.object(lookup, "set_options"):
            return lookup.run(terms)

    def test_digest_uses_raw_bytes_and_delivered_value_is_not_trimmed(self):
        raw = b"fixture-secret\n"
        raw_digest = hashlib.sha256(raw).hexdigest()
        stripped_digest = hashlib.sha256(raw.strip()).hexdigest()

        with patch.object(SECRET.LookupModule, "_get_object", return_value=raw):
            self.assertEqual(self._run([URL, raw_digest]), ["fixture-secret\n"])
            with self.assertRaisesRegex(AnsibleError, "stored object changed"):
                self._run([URL, stripped_digest])

    def test_malformed_digest_is_invalid_input(self):
        malformed = ("", "   ", "a" * 63, "g" * 64)

        for digest in malformed:
            with self.subTest(digest=digest), self.assertRaisesRegex(
                AnsibleError, "not a SHA-256"
            ):
                self._run([URL, digest])

    def test_lookup_does_not_cache_objects(self):
        raw = b"fixture-secret"
        digest = hashlib.sha256(raw).hexdigest()

        with patch.object(
            SECRET.LookupModule, "_get_object", return_value=raw
        ) as get_object:
            self._run([URL, digest])
            self._run([URL, digest])

        self.assertEqual(get_object.call_count, 2)

    def test_wrong_number_of_terms_is_rejected(self):
        valid_digest = "a" * 64

        for terms in ([], [URL, valid_digest, "extra"]):
            with self.subTest(terms=terms), self.assertRaisesRegex(
                AnsibleError, "give one URL"
            ):
                self._run(terms)

    def test_non_s3_scheme_is_rejected(self):
        with self.assertRaisesRegex(AnsibleError, "not a scheme this plugin reads"):
            self._run(["vault://fixture/credential"])

    def test_url_without_bucket_is_rejected(self):
        with self.assertRaisesRegex(AnsibleError, "names no bucket or no key"):
            self._run(["s3:///applications/fixture/credential.txt"])

    def test_url_without_key_is_rejected(self):
        for url in ("s3://fixture-bucket", "s3://fixture-bucket/"):
            with self.subTest(url=url), self.assertRaisesRegex(
                AnsibleError, "names no bucket or no key"
            ):
                self._run([url])

    def test_empty_and_whitespace_only_objects_are_rejected(self):
        for raw in (b"", b" \t\r\n"):
            with (
                self.subTest(raw=raw),
                patch.object(SECRET.LookupModule, "_get_object", return_value=raw),
                self.assertRaisesRegex(AnsibleError, "is empty"),
            ):
                self._run([URL])

    def test_non_utf8_object_is_rejected(self):
        with (
            patch.object(SECRET.LookupModule, "_get_object", return_value=b"\xff"),
            self.assertRaisesRegex(AnsibleError, "is not valid UTF-8"),
        ):
            self._run([URL])

    def test_mocked_s3_client_receives_parsed_bucket_and_key(self):
        client = S3Client()
        boto3.CLIENT = client

        self.assertEqual(
            SECRET.LookupModule._get_object(
                "fixture-bucket", "applications/fixture/credential.txt", URL
            ),
            b"fixture-secret\n",
        )
        self.assertEqual(
            client.calls,
            [
                {
                    "Bucket": "fixture-bucket",
                    "Key": "applications/fixture/credential.txt",
                }
            ],
        )

    def test_client_error_names_url_without_object_value(self):
        object_value = "private-object-value-canary"
        boto3.CLIENT = S3Client(
            value=object_value.encode(),
            error=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "access denied"}},
                "GetObject",
            ),
        )

        with self.assertRaises(AnsibleError) as result:
            SECRET.LookupModule._get_object(
                "fixture-bucket", "applications/fixture/credential.txt", URL
            )

        self.assertIn(URL, str(result.exception))
        self.assertNotIn(object_value, str(result.exception))


if __name__ == "__main__":
    unittest.main()
