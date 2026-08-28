# SPDX-FileCopyrightText: 2026 Nicholas Warila
# SPDX-License-Identifier: MIT
"""Provide the botocore exception types caught by the secret lookup."""


class BotoCoreError(Exception):
    pass


class ClientError(Exception):
    def __init__(self, response, operation_name):
        self.response = response
        self.operation_name = operation_name
        error = response.get("Error", {})
        super().__init__(
            f"An error occurred ({error.get('Code', 'Unknown')}) when calling the "
            f"{operation_name} operation: {error.get('Message', 'Unknown')}"
        )
