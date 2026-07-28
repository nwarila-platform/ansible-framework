#!/usr/bin/python

from ansible.module_utils.basic import AnsibleModule


def main():
    module = AnsibleModule(
        argument_spec={
            "role_arn": {"type": "str", "required": True},
            "role_session_name": {"type": "str", "required": True},
            "region": {"type": "str", "required": True},
            "duration_seconds": {"type": "int", "required": True},
        },
        supports_check_mode=False,
    )
    module.exit_json(
        changed=False,
        sts_creds={
            "access_key": "TEST_ACCESS_MARKER",
            "secret_key": "TEST_PRIVATE_MARKER",
            "session_token": "TEST_SESSION_MARKER",
        },
    )


if __name__ == "__main__":
    main()
