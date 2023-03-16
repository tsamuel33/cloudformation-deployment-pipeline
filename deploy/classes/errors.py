class CloudFormationError(Exception):
    """Raises an exception when...
    
    Attributes:
        message -- message indicating the specifics of the error
    """

    def __init__(self, message='Generic error') -> None:
        self.message = message
        super().__init__(self.message)