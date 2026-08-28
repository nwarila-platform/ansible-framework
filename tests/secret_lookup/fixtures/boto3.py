# SPDX-FileCopyrightText: 2026 Nicholas Warila
# SPDX-License-Identifier: MIT
"""Provide the one boto3 operation the secret lookup exercises."""


class _Body:
    @staticmethod
    def read():
        return b"fixture-secret\n"


class _Client:
    @staticmethod
    def get_object(**kwargs):
        return {"Body": _Body()}


CLIENT = _Client()


def client(service_name):
    if service_name != "s3":
        raise AssertionError(f"unexpected service: {service_name}")
    return CLIENT
