class WinRMError(Exception):
    pass


class WinRMOperationTimeoutError(WinRMError):
    pass


class WinRMTransportError(WinRMError):
    def __init__(self, protocol, code, message):
        self.protocol = protocol
        self.code = code
        self.message = message
        super().__init__(f"Bad HTTP response returned from server. Code {code}")


class WSManFaultError(WinRMError):
    def __init__(self, code=0, message="", response="", reason="", wmierror_code=0,
                 fault_code="", fault_subcode=""):
        self.wmierror_code = wmierror_code
        super().__init__(message)
