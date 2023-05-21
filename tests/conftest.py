import pytest
from scripts.classes.s3 import AWSS3UploadBucket

def pytest_addoption(parser):
    parser.addoption("--region", action="store", help="AWS region used for tests", type=str)
    parser.addoption("--environment", action="store", help="application environment used for tests", type=str)

def pytest_generate_tests(metafunc):
    if "region" in metafunc.fixturenames:
        metafunc.parametrize("region", [metafunc.config.getoption("region")], indirect=True)
    if "environment" in metafunc.fixturenames:
        metafunc.parametrize("environment", [metafunc.config.getoption("environment")], indirect=True)

@pytest.fixture(scope="module")
def region(request):
    return request.config.getoption("--region")

@pytest.fixture(scope="module")
def environment(request):
    return request.config.getoption("--environment")

@pytest.fixture(scope="module")
def default_bucket(region):
    default = AWSS3UploadBucket(
        region=region, upload_bucket_name=None)
    return default