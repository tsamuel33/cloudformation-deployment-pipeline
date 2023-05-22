import json
import sys
import boto3
from botocore.exceptions import ClientError
import logging
from .decorators import boto3_error_decorator
from pathlib import Path

# Set up logger
logger = logging.getLogger(Path(__file__).name)

class AWSCloudFormationStack:
    """
    A base class used to represent a CloudFormation stack
    
    ...

    Attributes
    ----------
    template_filename : str
        name of the template file
    parameter_filename : str
        name of the parameter file if available
    region : str
        region to deploy the template
    cf : object
        object representing the CloudFormation boto3 client
    s3 : object
        object representing the S3 boto3 client
    stack_name : str
        name of the CloudFormation stack
    """

    deployment_dir = Path(__file__).parents[2] / "deployments"
    default_stack_prefix = "managed-app"
    success_statuses = [
        'CREATE_COMPLETE',
        'UPDATE_COMPLETE'
    ]
    failure_statuses = [
        'CREATE_FAILED',
        'ROLLBACK_IN_PROGRESS',
        'ROLLBACK_FAILED',
        'ROLLBACK_COMPLETE',
        'DELETE_IN_PROGRESS',
        'DELETE_FAILED',
        'DELETE_COMPLETE',
        'UPDATE_FAILED',
        'UPDATE_ROLLBACK_FAILED',
        'UPDATE_ROLLBACK_COMPLETE'
    ]

    def __init__(self, template_file_name, parameter_mapping_object,
                 template_mapping_object, environment, s3_upload_object,
                 account_number, execution_role_name, all_envs=True,
                 region='us-east-1', stack_prefix=None,
                 template_type="cloudformation") -> None:
        self.parameter_mapping = parameter_mapping_object
        self.template_mapping = template_mapping_object
        if all_envs:
            folder = "all_envs"
        else:
            folder = environment
        self.template_path = self.deployment_dir / region / folder / "templates" / template_type / template_file_name
        self.parameter_path = self.get_parameter_file_path(template_file_name, region, environment, folder, all_envs)
        self.stack_name = self.determine_stack_name(template_file_name, stack_prefix)
        self.parameters = self.create_parameter_list()
        self.size = Path(self.template_path).stat().st_size
        # # TODO - Add an indication for the existence of a parameter file. Use this as a pre-validation if cfn-lint doesn't provide that.
        self.cf = boto3.client('cloudformation', region_name=region)
        self.upload_bucket = s3_upload_object
        self.role_arn = "".join(("arn:aws:iam::", account_number, ":role/", execution_role_name))

    def determine_stack_name(self, filename, prefix):
        # Start off using default stack naming convention
        stack_suffix = filename.split(".")[0]
        if prefix is None:
            stack_name = "-".join((self.default_stack_prefix, stack_suffix))
        else:
            stack_name = "-".join((prefix, stack_suffix))
        # Check if custom stack name is set in mapping file
        if self.template_mapping is not None:
            name = self.template_mapping.get_mapping_value(filename, "templates")
            if name is not None:
                stack_name = name
        return stack_name

    def get_parameter_file_path(self, filename, region, environment, folder, all_envs=True):
        # Set up default names
        prefix = filename.split(".")[0]
        if all_envs:
            default_name = ".".join((prefix, environment, "json"))
        else:
            default_name = ".".join((prefix, "json"))
        # Attempt to get name from mapping file. Use default if name is not found
        name = self.parameter_mapping.get_mapping_value(filename, "parameters")
        if name is None:
            name = default_name
        path = self.deployment_dir / region / folder / "parameters" / name
        return path

    # TODO - Ensure pipeline takes yaml and json
    @staticmethod
    def load_file(file_path):
        try:
            with open(file_path, 'r') as myFile:
                data = myFile.read()
            return data
        except FileNotFoundError:
            filename = file_path.name
            # Give warning message for missing parameter file. This will not
            # apply to template files as the template must exist to initialize
            # the stack class
            message = "Parameter file ({}) not found. ".format(filename) + \
                "Stack actions will fail if template does not have " + \
                "default values defined for all parameters."
            logger.warning(message)

    def create_parameter_list(self):
        parameters = self.load_file(self.parameter_path)
        if parameters is None:
            parameterlist = None
        if parameters is not None:
            parameterlist = []
            paramObj = json.loads(parameters)
            for y in paramObj:
                paramValue = paramObj[y]
                entry = {
                        'ParameterKey': y,
                        'ParameterValue': paramValue,
                        'UsePreviousValue': False
                    }
                parameterlist.append(entry)
        return parameterlist

    #TODO - Also have it get stack details for failure
    @boto3_error_decorator(logger)
    def get_stack(self):
        response = self.cf.describe_stacks(StackName=self.stack_name)['Stacks'][0]
        status = response['StackStatus']
        try:
            reason = response['StackStatusReason']
        except KeyError:
            reason = "N/A"
        finally:
            return (status, reason)

    @boto3_error_decorator(logger)
    def validate_template(self):
        template_body = self.load_file(self.template_path)
        self.cf.validate_template(TemplateBody=template_body)

    @boto3_error_decorator(logger)
    def validate_template_s3(self, template_url):
        self.cf.validate_template(TemplateURL=template_url)

    def create_stack(self):
        logger.info("Creating stack: {}".format(self.stack_name))
        try:
            if self.size > 51200:
                createTemplateResponse = self.cf.create_stack(
                    StackName=self.stack_name,
                    TemplateBody=self.load_file(self.template_path),
                    Parameters=self.parameters,
                    # TimeoutInMinutes=123,
                    Capabilities=[
                        'CAPABILITY_IAM',
                        'CAPABILITY_NAMED_IAM',
                        'CAPABILITY_AUTO_EXPAND'
                    ],
                    RoleARN=self.role_arn,
                    # EnableTerminationProtection=True|False,
                    OnFailure='DELETE'
                )
            else:
                logger.info('{} file size is larger than quota. Uploading to {}'.format(self.template_path.name, self.upload_bucket.bucket_name))
                self.upload_bucket.upload_file(self.template_path)
                object_url = "".join(("https://", self.upload_bucket.bucket_name, ".s3.amazonaws.com/", self.template_path.name))
                createTemplateResponse = self.cf.create_stack(
                    StackName=self.stack_name,
                    TemplateURL=object_url,
                    Parameters=self.parameters,
                    # TimeoutInMinutes=123,
                    Capabilities=[
                        'CAPABILITY_IAM',
                        'CAPABILITY_NAMED_IAM',
                        'CAPABILITY_AUTO_EXPAND'
                    ],
                    RoleARN=self.role_arn,
                    # EnableTerminationProtection=True|False,
                    OnFailure='DELETE'
                )
            logger.info('Creation of stack: {} in progress...'.format(createTemplateResponse['StackId']))
        except ClientError as err:
            if err.response['Error']['Code'] == "AlreadyExistsException":
                logger.info("Stack already exists.")
            else:
                raise err

    #TODO - Add change set methods (create, describe, delete)

    @boto3_error_decorator(logger)
    def update_stack_local(self):
        stackupdateresponse = self.cf.update_stack(
            StackName=self.stack_name,
            TemplateBody=self.load_file(self.template_path),
            Parameters=self.parameters,
            Capabilities=[
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            RoleARN=self.role_arn,
            DisableRollback=False
        )
        return stackupdateresponse

    @boto3_error_decorator(logger)
    def update_stack_s3(self, parameters, template_url):
        stackupdateresponse = self.cf.update_stack(
            StackName=self.stack_name,
            TemplateURL=template_url,
            Parameters=parameters,
            Capabilities=[
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            RoleARN=self.role_arn,
            DisableRollback=False
        )
        return stackupdateresponse
    
    #TODO - Add way to handle retaining resources when stack is in DELETE_FAILED state
    def delete_stack(self):
        stackdeletionresponse = self.cf.delete_stack(
            StackName=self.stack_name,
            # RetainResources=[
            #     'string',
            # ],
            RoleARN=self.role_arn
        )
        return stackdeletionresponse