import boto3
import logging
from .decorators import boto3_error_decorator
from pathlib import Path

# Set up logger
logger = logging.getLogger(Path(__file__).name)

class AWSS3UploadBucket:
    """
    A base class used to represent an S3 bucket used to store
    CloudFormation templates

    ...

    Attributes
    ----------
    s3 : object
        object representing the S3 boto3 client
    bucket_name : str
        name of the S3 bucket used to upload large CloudFormation templates
    bucket_exists : bool
        boolean stating if an S3 bucket exists in the account for template upload
    s3_bucket : object
        object representing the S3 bucket used to upload large CloudFormation templates
    versioning_enabled : NoneType or str
        represents if versioning is enabled on the S3 bucket
    """

    def __init__(self, region='us-east-1', upload_bucket_name=None) -> None:
        self.s3 = boto3.client('s3', region_name=region, verify=False) #TODO - Remove verify=False after testing is complete
        s3_resource = boto3.resource('s3', region_name=region, verify=False) #TODO - Remove verify=False after testing is complete
        self.get_cf_bucket(region, upload_bucket_name)
        self.s3_bucket = s3_resource.Bucket(self.bucket_name)
        self.versioning_enabled = self.s3_bucket.Versioning().status

    @boto3_error_decorator(logger)
    def get_cf_bucket(self, region, bucket_name=None):
        bucket_list = self.s3.list_buckets()
        buckets = bucket_list['Buckets']
        parsed_response = self.parse_bucket_list(buckets, region, bucket_name)
        self.bucket_name = parsed_response[0]
        self.bucket_exists = parsed_response[1]

    def parse_bucket_list(self, parsing_list, region, target_name=None, target_prefix='cf-templates-'):
        s3_bucket = ''
        bucket_exists = True
        if target_name is not None:
            for b in parsing_list:
                if b['Name'] == target_name:
                    s3_bucket = b['Name']
            if s3_bucket == '':
                message = "Bucket: {} does not exist. Checking for default CloudFormation bucket".format(target_name)
                logger.warning(message)
        # Look for default CF upload bucket if one is not provided or if provided bucket doesn't exist
        if s3_bucket == '':
            for b in parsing_list:
                if b['Name'].startswith(target_prefix) and b['Name'].endswith(region):
                    s3_bucket = b['Name']
        if s3_bucket == '':
            message1 = "Default CloudFormation bucket does not exist in account."
            message2 = "If a CloudFormation template is over 51,200 bytes, deployment may fail."
            message3 = "If pipeline fails, please create an S3 bucket for file upload or re-run pipeline after default CloudFormation bucket has been initialized."
            logger.warning(message1)
            logger.warning(message2)
            logger.warning(message3)
            bucket_exists = False
        return (s3_bucket, bucket_exists)

    # TODO - Update this function when adding Lambda and API Gateway functionality
    # TODO - modify this to be a generic S3 bucket class and create a subclass for Lambda/API gateway
    # def upload_object(self, temp_path, folder_name, file_name):
    #     filePath = "/".join((temp_path, file_name))
    #     objectKey = "/".join((folder_name, file_name))
    #     logger.info("Uploading file: %s" % (file_name))
    #     self.s3_bucket.upload_file(filePath, objectKey)
    #     logger.info("File uploaded successfully")

    # def zip_folder(temp_path, artifact_dir, artifact_folder_name):
    #     sourceFolder = "/".join((artifact_dir, artifact_folder_name))
    #     zipFileName = "".join((artifact_folder_name, "_", ZIP_FILE_SUFFIX, ".zip"))
    #     zipFilePath = "".join((temp_path, zipFileName))
    #     with ZipFile(zipFilePath, "w") as zipObject:
    #         for (root,dirs,files) in os.walk(sourceFolder):
    #             for file in files:
    #                 filePath = os.path.join(root, file)
    #                 newPath = filePath.replace(sourceFolder, '')
    #                 zipObject.write(filePath, newPath)
    #         zipObject.close()
    #     logger.info("Created: %s" % (zipFilePath))
    #     return zipFileName

    # def identify_main_frontend_js_files(artifact_dir, frontend_key):
    #     frontendFolder = "/".join((artifact_dir, parameter_dict[frontend_key]))
    #     mainFiles = []
    #     files = os.listdir(frontendFolder)
    #     for file in files:
    #         if file.lower().startswith("main.") and file.lower().endswith(".js"):
    #             mainFiles.append(file)
    #     return mainFiles

    @boto3_error_decorator(logger)
    def upload_template(self, template_location, file_name):
        with open(template_location, "rb") as template:
            response = self.s3.put_object(Body=template,Bucket=self.bucket_name,Key=file_name)
            if self.versioning_enabled is not None:
                version_id = response['VersionId']
                template.close()
                return version_id
            else:
                template.close()
                return None