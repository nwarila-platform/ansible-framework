FEATURE_SUPPORTED_AUTHTYPES = [
    "basic", "kerberos", "ntlm", "certificate", "credssp", "plaintext", "ssl"
]

from winrm.protocol import Protocol

__all__ = ["Protocol"]
