import pytest
from scripts.classes.s3 import AWSS3UploadBucket

def pytest_addoption(parser):
    parser.addoption("--account_number", action="store", help="AWS account number used for tests", type=str)
    parser.addoption("--branch", action="store", help="Repository branch used for tests", type=str)

def pytest_generate_tests(metafunc):
    if "account_number" in metafunc.fixturenames:
        metafunc.parametrize("account_number", [metafunc.config.getoption("account_number")], indirect=True)
    if "branch" in metafunc.fixturenames:
        metafunc.parametrize("branch", [metafunc.config.getoption("branch")], indirect=True)

@pytest.fixture(scope="module")
def account_number(request):
    return request.config.getoption("--account_number")

@pytest.fixture(scope="module")
def branch(request):
    return request.config.getoption("--branch")

@pytest.fixture(scope="module")
def default_bucket(account_number):
    default = AWSS3UploadBucket(
        account_number=account_number, upload_bucket_name=None)
    return default