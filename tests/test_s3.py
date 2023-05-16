import os
import pytest
from pathlib import Path
from scripts.classes.s3 import AWSS3UploadBucket

class TestS3Buckets:

    upload_filename="pytest_upload.txt"
    region = 'us-east-1'

    def initialize_bucket(self, bucket_name):
        bucket = AWSS3UploadBucket(
            region=self.region, upload_bucket_name=bucket_name)
        return bucket

    @pytest.fixture
    def default_bucket(self):
        default = self.initialize_bucket(None)
        return default

    def test_find_default_bucket(self, default_bucket):
        bucket = default_bucket
        assert bucket.bucket_name.startswith("cf-templates-")
        assert bucket.bucket_name.endswith(self.region)

    @staticmethod
    def create_test_file(filename):
        with open(filename, "w") as file:
            file.close()

    @staticmethod
    def delete_test_file(file):
        os.remove(file)

    def test_find_non_existent_bucket(self, default_bucket):
        bucket = self.initialize_bucket("fakebucketnamewihcihadoijs")
        # If bucket doesn't exist, falls back to default bucket
        assert bucket.bucket_name == default_bucket.bucket_name

    def test_file_upload(self, default_bucket):
        self.create_test_file(self.upload_filename)
        file_location = Path(__file__).parents[1] / self.upload_filename
        version_id = default_bucket.upload_file(file_location, self.upload_filename)
        if version_id is not None:
            default_bucket.s3.delete_object(Bucket=default_bucket.bucket_name, Key=self.upload_filename,VersionId=version_id)
        else:
            default_bucket.s3.delete_object(Bucket=default_bucket.bucket_name, Key=self.upload_filename)
        self.delete_test_file(file_location)