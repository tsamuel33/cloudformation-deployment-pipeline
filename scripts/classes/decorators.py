from functools import wraps
from sys import exit

from botocore.exceptions import ClientError, ParamValidationError

# Decorator to output Boto3 errors in the format set by the logger so
# errors are easier to see in the output
def boto3_error_decorator(logger):
    def error_decorator(func):
        @wraps(func)
        def error_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ClientError as err:
                logger.error(err)
                exit(err)
            except ParamValidationError as err:
                logger.error(err)
                exit(err)
        return error_wrapper
    return error_decorator