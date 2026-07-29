from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ansible.module_utils.common.arg_spec import ModuleArgumentSpecValidator
from ansible.module_utils.common.parameters import remove_values
from botocore.exceptions import ClientError


MODULE_PATH = Path(__file__).resolve().parents[1] / "library" / "s3_artifact.py"
MODULE_SPEC = importlib.util.spec_from_file_location("s3_artifact", MODULE_PATH)
S3_ARTIFACT = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(S3_ARTIFACT)

ACTION_PATH = Path(__file__).resolve().parents[1] / "action_plugins" / "s3_artifact.py"
ACTION_SPEC = importlib.util.spec_from_file_location("s3_artifact_action", ACTION_PATH)
S3_ARTIFACT_ACTION = importlib.util.module_from_spec(ACTION_SPEC)
ACTION_SPEC.loader.exec_module(S3_ARTIFACT_ACTION)


class ModuleResult(Exception):
    def __init__(self, result):
        super().__init__()
        self.result = result


class ModuleStub:
    def __init__(self, params):
        self.params = params

    def exit_json(self, **result):
        raise ModuleResult(result)

    def fail_json(self, **result):
        raise ModuleResult(result)


class S3ArtifactTest(unittest.TestCase):
    def setUp(self):
        self.params = {
            "mode": "presign",
            "bucket": "artifact-fixture",
            "object_key": "objects/fixture.bin",
            "region": "us-east-1",
            "access_key": "reader-identifier-marker",
            "secret_key": "private-value-marker",
            "session_token": "session-value-marker",
            "expires_in": 900,
            "dest": None,
        }
        self.url = (
            "https://example.invalid/object"
            "?reader=reader-identifier-marker&session=session-value-marker"
        )

    def test_module_no_log_does_not_add_url_values_to_remove_values(self):
        validation = ModuleArgumentSpecValidator(S3_ARTIFACT.ARGUMENT_SPEC).validate(self.params)

        self.assertFalse(validation.errors.errors)
        self.assertIn(self.params["secret_key"], validation._no_log_values)
        self.assertNotIn(self.params["access_key"], validation._no_log_values)
        self.assertNotIn(self.params["session_token"], validation._no_log_values)
        self.assertEqual(
            remove_values({"url": self.url}, validation._no_log_values)["url"],
            self.url,
        )

        test_case = self

        class RecordingModule(ModuleStub):
            def __init__(self, argument_spec, required_if, supports_check_mode, no_log):
                test_case.assertIs(argument_spec, S3_ARTIFACT.ARGUMENT_SPEC)
                test_case.assertTrue(no_log)
                super().__init__(test_case.params)

        class PresigningClient:
            def generate_presigned_url(self, **kwargs):
                return test_case.url

        with (
            patch.object(S3_ARTIFACT, "AnsibleModule", RecordingModule),
            patch.object(S3_ARTIFACT, "_client", return_value=PresigningClient()),
            self.assertRaises(ModuleResult) as result,
        ):
            S3_ARTIFACT.main()

        self.assertEqual(result.exception.result["url"], self.url)

    def test_action_plugin_marks_the_controller_result_no_log(self):
        action = S3_ARTIFACT_ACTION.ActionModule.__new__(
            S3_ARTIFACT_ACTION.ActionModule
        )
        action._task = SimpleNamespace(no_log=False)

        with patch.object(
            S3_ARTIFACT_ACTION.NormalActionModule,
            "run",
            return_value={"changed": False, "url": self.url},
        ):
            result = action.run(task_vars={})

        self.assertTrue(action._task.no_log)
        self.assertTrue(result["_ansible_no_log"])
        self.assertEqual(result["url"], self.url)

    def test_presign_failure_surfaces_only_error_code(self):
        class PresigningClient:
            def generate_presigned_url(self, **kwargs):
                raise ClientError(
                    {
                        "Error": {
                            "Code": "NoSuchBucket",
                            "Message": (
                                "private-path-canary private-endpoint-canary"
                            ),
                        }
                    },
                    "GetObject",
                )

        with self.assertRaises(ModuleResult) as result:
            S3_ARTIFACT._presign(ModuleStub(self.params), PresigningClient())

        self.assertEqual(
            result.exception.result["msg"],
            "Unable to presign the requested S3 object. AWS error code: NoSuchBucket.",
        )
        self.assertEqual(result.exception.result["error_code"], "NoSuchBucket")
        self.assertNotIn("private-path-canary", result.exception.result["msg"])
        self.assertNotIn("private-endpoint-canary", result.exception.result["msg"])

    def test_download_failure_surfaces_only_error_code_and_cleans_up(self):
        class DownloadingClient:
            def download_file(self, *args):
                raise ClientError(
                    {
                        "Error": {
                            "Code": "AccessDenied",
                            "Message": (
                                "private-path-canary private-endpoint-canary"
                            ),
                        }
                    },
                    "GetObject",
                )

        with tempfile.TemporaryDirectory() as directory:
            params = {
                **self.params,
                "mode": "get",
                "dest": str(Path(directory) / "artifact.bin"),
            }
            with self.assertRaises(ModuleResult) as result:
                S3_ARTIFACT._download(ModuleStub(params), DownloadingClient())

            self.assertEqual(list(Path(directory).iterdir()), [])

        self.assertEqual(
            result.exception.result["msg"],
            "Unable to download the requested S3 object. AWS error code: AccessDenied.",
        )
        self.assertEqual(result.exception.result["error_code"], "AccessDenied")
        self.assertNotIn("private-path-canary", result.exception.result["msg"])
        self.assertNotIn("private-endpoint-canary", result.exception.result["msg"])


if __name__ == "__main__":
    unittest.main()
