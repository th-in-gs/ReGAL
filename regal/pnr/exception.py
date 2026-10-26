class PnrError(Exception):
    def __init__(self, msg):
        self.msg = msg


class FitError(PnrError):
    # The design does not fit in the device
    pass
