#!/usr/bin/python

from __future__ import annotations

DOCUMENTATION = r"""
---
module: s3_artifact
short_description: Presign or download one S3 artifact from the controller
description:
  - Uses an explicitly supplied temporary credential to presign one S3 GetObject request locally
    or download one object to the controller.
  - Presigning calls only the SDK's local SigV4 implementation; it does not query S3.
options:
  mode:
    description: Operation to perform.
    type: str
    required: true
    choices: [presign, get]
  bucket:
    description: S3 bucket containing the object.
    type: str
    required: true
  object_key:
    description: S3 object key.
    type: str
    required: true
  region:
    description: AWS region containing the bucket.
    type: str
    required: true
  access_key:
    description: Temporary artifact-reader access key.
    type: str
    required: true
  secret_key:
    description: Temporary artifact-reader secret key.
    type: str
    required: true
  session_token:
    description: Temporary artifact-reader session token.
    type: str
    required: true
  expires_in:
    description: Presigned URL lifetime in seconds.
    type: int
    default: 900
  dest:
    description: Controller destination for C(mode=get).
    type: path
author:
  - ansible-framework maintainers
"""

EXAMPLES = r"""
- name: Sign one artifact on the controller
  delegate_to: localhost
  no_log: true
  s3_artifact:
    mode: presign
    bucket: example-artifacts
    object_key: applications/example.rpm
    region: us-east-1
    access_key: "{{ controller_access_key }}"
    secret_key: "{{ controller_secret_key }}"
    session_token: "{{ controller_session_token }}"
    expires_in: 900
"""

RETURN = r"""
url:
  description: Presigned HTTPS URL.
  returned: mode == 'presign'
  type: str
dest:
  description: Download destination on the controller.
  returned: mode == 'get'
  type: str
"""

import os
import re
import tempfile

from ansible.module_utils.basic import AnsibleModule

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    Config = None
    ClientError = None


ARGUMENT_SPEC = {
    "mode": {
        "type": "str",
        "required": True,
        "choices": ["presign", "get"],
    },
    "bucket": {"type": "str", "required": True},
    "object_key": {"type": "str", "required": True},
    "region": {"type": "str", "required": True},
    # The access-key identifier and session token are embedded in every temporary-credential
    # presigned URL. Adding no_log to either option would make exit_json replace the same value
    # inside the URL and corrupt its signature. Module-wide no_log suppresses output without
    # adding either value to the remove_values set. The secret key is never part of the URL.
    "access_key": {"type": "str", "required": True},
    "secret_key": {"type": "str", "required": True, "no_log": True},
    "session_token": {"type": "str", "required": True},
    "expires_in": {"type": "int", "default": 900},
    "dest": {"type": "path"},
}

AWS_ERROR_CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _fail(module, message, error=None):
    failure = {"msg": message}
    if ClientError is not None and isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code")
        if isinstance(code, str) and AWS_ERROR_CODE_PATTERN.fullmatch(code):
            failure["msg"] = f"{message} AWS error code: {code}."
            failure["error_code"] = code
    module.fail_json(**failure)


def _client(params):
    return boto3.client(
        "s3",
        region_name=params["region"],
        aws_access_key_id=params["access_key"],
        aws_secret_access_key=params["secret_key"],
        aws_session_token=params["session_token"],
        config=Config(signature_version="s3v4"),
    )


def _presign(module, client):
    try:
        url = client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": module.params["bucket"],
                "Key": module.params["object_key"],
            },
            ExpiresIn=module.params["expires_in"],
            HttpMethod="GET",
        )
    except Exception as error:
        _fail(module, "Unable to presign the requested S3 object.", error)

    if not url.startswith("https://"):
        _fail(module, "The SDK returned a non-HTTPS artifact URL.")
    module.exit_json(changed=False, url=url)


def _download(module, client):
    dest = module.params["dest"]
    dest_dir = os.path.dirname(dest)
    if not os.path.isdir(dest_dir):
        _fail(module, "The controller destination directory does not exist.")

    fd, temporary_path = tempfile.mkstemp(prefix=".s3-artifact-", dir=dest_dir)
    os.close(fd)
    os.chmod(temporary_path, 0o600)
    try:
        client.download_file(
            module.params["bucket"],
            module.params["object_key"],
            temporary_path,
        )
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, dest)
    except Exception as error:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        _fail(module, "Unable to download the requested S3 object.", error)

    module.exit_json(changed=True, dest=dest)


def main():
    module = AnsibleModule(
        argument_spec=ARGUMENT_SPEC,
        required_if=[("mode", "get", ["dest"])],
        supports_check_mode=False,
        no_log=True,
    )

    if boto3 is None:
        _fail(module, "boto3 and botocore are required on the Ansible controller.")
    if not 1 <= module.params["expires_in"] <= 3600:
        _fail(module, "expires_in must be between 1 and 3600 seconds.")

    try:
        client = _client(module.params)
    except Exception as error:
        _fail(module, "Unable to initialize the S3 client.", error)
    if module.params["mode"] == "presign":
        _presign(module, client)
    _download(module, client)


if __name__ == "__main__":
    main()
