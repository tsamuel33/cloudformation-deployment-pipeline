import boto3
import json
import logging
import yaml
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from .decorators import boto3_error_decorator
from pathlib import Path
from sys import exit
from time import sleep

# Set up logger
logger = logging.getLogger(Path(__file__).name)

class AWSCloudFormationStack:
    """
    A base class used to represent a CloudFormation stack
    
    ...

    Attributes
    ----------
    template_path : str
        Location of the template file
    parameter_path : str
        Location of the parameter file if available
    stack_name : str
        Name of the CloudFormation stack
    self.size : int
        Size of the template file in bytes
    role_arn : str
        ARN of the IAM role used to execute the CloudFormation actions
    """

    deployment_dir = Path(__file__).parents[2] / "deployments"
    default_stack_prefix = "managed-app"
    success_statuses = [
        'CREATE_COMPLETE',
        'UPDATE_COMPLETE',
        'DELETE_COMPLETE'
    ]
    failure_statuses = [
        'CREATE_FAILED',
        'ROLLBACK_IN_PROGRESS',
        'ROLLBACK_FAILED',
        'ROLLBACK_COMPLETE',
        'DELETE_FAILED',
        'UPDATE_FAILED',
        'UPDATE_ROLLBACK_FAILED',
        'UPDATE_ROLLBACK_IN_PROGRESS',
        'UPDATE_ROLLBACK_COMPLETE',
        'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS'
    ]

    def __init__(self, template_file_path, parameter_mapping_object,
                 template_mapping_object, environment, s3_upload_object,
                 account_number, execution_role_name, check_period=15,
                 all_envs=True, region='us-east-1', stack_prefix=None,
                 protection=False) -> None:
        self._initial_time = datetime.now(timezone.utc)
        self._check_period = check_period
        self._parameter_mapping = parameter_mapping_object
        self._template_mapping = template_mapping_object
        if all_envs:
            folder = "all_envs"
        else:
            folder = environment
        self.template_path = template_file_path
        self.rename_logger(folder)
        self.parameter_path = self.get_parameter_file_path(environment, all_envs)
        self.stack_name = self.determine_stack_name(stack_prefix)
        self.parameters = self.create_parameter_list()
        self.size = Path(self.template_path).stat().st_size
        self._cf = boto3.client('cloudformation', region_name=region)
        self._upload_bucket = s3_upload_object
        self.role_arn = "".join(("arn:aws:iam::", account_number, ":role/", execution_role_name))
        self._termination_protection = protection

    # Rename logger so it's easier to identify the source when running
    # stack actions in parallel
    def rename_logger(self, folder):
        global logger
        logger_name = "-".join((folder, self.template_path.name))
        logger = logging.getLogger(logger_name)

    def determine_stack_name(self, prefix):
        # Start off using default stack naming convention
        stack_suffix = self.template_path.stem
        filename = self.template_path.name
        if prefix is None:
            stack_name = "-".join((self.default_stack_prefix, stack_suffix))
        else:
            stack_name = "-".join((prefix, stack_suffix))
        # Check if custom stack name is set in mapping file
        if self._template_mapping is not None:
            name = self._template_mapping.get_mapping_value(filename, "templates")
            if name is not None:
                stack_name = name
        # If stack name contains underscores, replace them with hyphens
        stack_name = stack_name.replace("_", "-")
        return stack_name

    def get_parameter_file_path(self, environment, all_envs=True):
        # Set up default names
        prefix = self.template_path.stem
        filename = self.template_path.name
        if all_envs:
            default_name = ".".join((prefix, environment, "json"))
        else:
            default_name = ".".join((prefix, "json"))
        # Attempt to get name from mapping file. Use default if name is not found
        name = self._parameter_mapping.get_mapping_value(filename, "parameters")
        if name is None:
            name = default_name
        param_dir = self.template_path.parents[1] / "parameters"
        path = param_dir / name
        return path

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
            return None

    def create_parameter_list(self):
        template = self.load_file(self.template_path)
        parameters = self.load_file(self.parameter_path)
        parameterlist = []
        if self.template_path.suffix == ".json":
            templateObj = json.loads(template)
        elif self.template_path.suffix in [".template", ".yaml", ".yml"]:
            templateObj = yaml.load(template, Loader=yaml.BaseLoader)
        try:
            temp_params = templateObj['Parameters']
        except KeyError:
            logger.info("Template for stack {} does not use input parameters".format(self.stack_name))
            if parameters is not None:
                logger.warning("Parameter file {} contains parameters that are not used in the template. File will be ignored.".format(self.parameter_path))
            return parameterlist
        if parameters is not None:
            logger.info("Loading parameter file: {}".format(self.parameter_path))
            paramObj = json.loads(parameters)
            paramkeys = list(paramObj.keys())
            for y in paramObj:
                if y in temp_params:
                    paramValue = paramObj[y]
                    entry = {
                            'ParameterKey': y,
                            'ParameterValue': paramValue,
                            'UsePreviousValue': False
                        }
                    parameterlist.append(entry)
                    paramkeys.remove(y)
                    del[temp_params[y]]
                else:
                    logger.warning("[{}] is defined in parameter file but not listed in the template file. Value will be ignored.".format(y))
        if temp_params != {}:
            logger.info("Values for some defined parameters are not found in the parameters file. Checking template for default values...")
            for param in temp_params:
                try:
                    default = temp_params[param]['Default']
                    entry = {
                            'ParameterKey': param,
                            'ParameterValue': default,
                            'UsePreviousValue': False
                        }
                    parameterlist.append(entry)
                except KeyError:
                    logger.error("Required parameter [{}] missing from parameter file and does not have a default value. Aborting operation.".format(param))
                    exit()
        return parameterlist

    @boto3_error_decorator(logger)
    def get_stack(self):
        try:
            response = self._cf.describe_stacks(StackName=self.stack_name)
            stack_status = response['Stacks'][0]['StackStatus']
            return stack_status
        except ClientError as err:
            if err.response['Error']['Code'] == 'ValidationError'and err.response['Error']['Message'] == 'Stack with id {} does not exist'.format(self.stack_name):
                stack_status = None
                return stack_status
            else:
                raise err

    #TODO - Add error handling if stack is deleted prior to getting events
    @boto3_error_decorator(logger)
    def get_stack_events(self, token=None):
        if token is None:
            response = self._cf.describe_stack_events(StackName=self.stack_name)
        else:
            response = self._cf.describe_stack_events(StackName=self.stack_name, NextToken=token)
        events = response['StackEvents']
        event_length = len(events)
        last_event_time = events[event_length - 1]['Timestamp']
        if last_event_time > self._initial_time:
            try:
                next_token = response['NextToken']
            except KeyError:
                next_token = None
        else:
            next_token = None
        for event in events:
            timestamp = event['Timestamp']
            resource_status = event['ResourceStatus']
            if "FAILED" in resource_status and timestamp > self._initial_time:
                try:
                    reason = event['ResourceStatusReason']
                    logger.error(reason)
                except KeyError:
                    reason = "N/A"
        if next_token is not None:
            self.get_stack_events(next_token)

    def monitor_stack_progress(self, action_type):
        status = ''
        if action_type == "CREATE":
            self.failure_statuses.append('DELETE_IN_PROGRESS')
        while status not in self.success_statuses and status not in self.failure_statuses:
            sleep(self._check_period)
            status = self.get_stack()
            if status is None and action_type == "DELETE":
                logger.info("Stack {} has been deleted".format(self.stack_name))
                status = 'DELETE_COMPLETE'
            elif status in self.success_statuses:
                logger.info("Stack action {} complete for stack: {}".format(action_type,self.stack_name))
            elif status in self.failure_statuses:
                logger.error("Stack action {} failed on stack {}. Gathering details...".format(action_type,self.stack_name))
                self.get_stack_events()
            else:
                logger.info("Stack action {} still in progress for stack {}...".format(action_type,self.stack_name))

    @boto3_error_decorator(logger)
    def create_stack(self):
        logger.info("Creating stack: {}".format(self.stack_name))
        try:
            if self.size < 51200:
                body = self.load_file(self.template_path)
                self._cf.validate_template(TemplateBody=body)
                createTemplateResponse = self._cf.create_stack(
                    StackName=self.stack_name,
                    TemplateBody=body,
                    Parameters=self.parameters,
                    Capabilities=[
                        'CAPABILITY_IAM',
                        'CAPABILITY_NAMED_IAM',
                        'CAPABILITY_AUTO_EXPAND'
                    ],
                    RoleARN=self.role_arn,
                    EnableTerminationProtection=self._termination_protection,
                    OnFailure='DELETE'
                )
            else:
                logger.info('{} file size is larger than quota. Uploading to {}'.format(self.template_path.name, self._upload_bucket.bucket_name))
                self._upload_bucket.upload_file(self.template_path)
                object_url = "".join(("https://", self._upload_bucket.bucket_name, ".s3.amazonaws.com/", self.template_path.name))
                self._cf.validate_template(TemplateURL=object_url)
                createTemplateResponse = self._cf.create_stack(
                    StackName=self.stack_name,
                    TemplateURL=object_url,
                    Parameters=self.parameters,
                    Capabilities=[
                        'CAPABILITY_IAM',
                        'CAPABILITY_NAMED_IAM',
                        'CAPABILITY_AUTO_EXPAND'
                    ],
                    RoleARN=self.role_arn,
                    EnableTerminationProtection=self._termination_protection,
                    OnFailure='DELETE'
                )
            logger.info('Creation of stack {} in progress...'.format(createTemplateResponse['StackId']))
        except ClientError as err:
            if err.response['Error']['Code'] == "AlreadyExistsException":
                logger.info("Stack already exists. No action taken.")
            else:
                raise err

    @boto3_error_decorator(logger)
    def update_stack(self):
        logger.info("Updating stack: {}".format(self.stack_name))
        try:
            if self.size < 51200:
                body = self.load_file(self.template_path)
                self._cf.validate_template(TemplateBody=body)
                stackUpdateResponse = self._cf.update_stack(
                    StackName=self.stack_name,
                    TemplateBody=body,
                    Parameters=self.parameters,
                    Capabilities=[
                        'CAPABILITY_IAM',
                        'CAPABILITY_NAMED_IAM',
                        'CAPABILITY_AUTO_EXPAND'
                    ],
                    RoleARN=self.role_arn,
                    DisableRollback=False
                )
            else:
                logger.info('{} file size is larger than quota. Uploading to {}'.format(self.template_path.name, self._upload_bucket.bucket_name))
                self._upload_bucket.upload_file(self.template_path)
                object_url = "".join(("https://", self._upload_bucket.bucket_name, ".s3.amazonaws.com/", self.template_path.name))
                self._cf.validate_template(TemplateURL=object_url)
                stackUpdateResponse = self._cf.update_stack(
                    StackName=self.stack_name,
                    TemplateURL=object_url,
                    Parameters=self.parameters,
                    Capabilities=[
                        'CAPABILITY_IAM',
                        'CAPABILITY_NAMED_IAM',
                        'CAPABILITY_AUTO_EXPAND'
                    ],
                    RoleARN=self.role_arn,
                    DisableRollback=False
                )
            logger.info('Update of stack {} in progress...'.format(stackUpdateResponse['StackId']))
        except ClientError as err:
            if err.response['Error']['Code'] == 'ValidationError' and err.response['Error']['Message'] == 'No updates are to be performed.':
                logger.info("No updates required for stack: {}".format(self.stack_name))
            elif err.response['Error']['Code'] == 'ValidationError' and err.response['Error']['Message'] == 'Stack [{}] does not exist'.format(self.stack_name):
                logger.info("Stack {} does not exist. Attempting to create stack...".format(self.stack_name))
                self.run_stack_actions("CREATE")
            else:
                raise err

    #TODO - Add change set methods (create, describe, delete)

    #TODO - Add way to handle retaining resources when stack is in DELETE_FAILED
    @boto3_error_decorator(logger)
    def delete_stack(self):
        logger.info("Deleting stack: {}".format(self.stack_name))
        stackdeletionresponse = self._cf.delete_stack(
            StackName=self.stack_name,
            # RetainResources=[
            #     'string',
            # ],
            RoleARN=self.role_arn
        )
        return stackdeletionresponse

    def run_stack_actions(self, action_type):
        # if action_type != "DELETE":
        #     self.parameters = self.create_parameter_list()
        if action_type == "CREATE":
            self.create_stack()
        elif action_type == "UPDATE":
            self.update_stack()
        elif action_type == "DELETE":
            self.delete_stack()
        self.monitor_stack_progress(action_type)