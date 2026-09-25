class PSHostUserInterface:
    def __init__(self):
        self.stdout = []
        self.stderr = []


class PSHost:
    def __init__(self, *args, **kwargs):
        del kwargs
        self.rc = 0
        self.ui = args[5]
