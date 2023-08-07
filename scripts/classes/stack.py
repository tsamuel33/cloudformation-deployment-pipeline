from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from sys import exit
from time import sleep

import boto3
from botocore.exceptions import ClientError, WaiterError
import yaml

from scripts.classes.decorators import boto3_error_decorator
from scripts.classes.mappings import Mappings
from scripts.classes.s3 import AWSS3UploadBucket


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
    changeset_prefix="github-actions-change-set"
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

    def __init__(self, template_file_path, environment, account_number,
                 execution_role_name, check_period=15, stack_prefix=None,
                 protection=False, upload_bucket_name=None) -> None:
        self._initial_time = datetime.now(timezone.utc)
        self._check_period = int(check_period)
        parts = template_file_path.parts
        region = parts[-4]
        if parts[-3] == "all_envs":
            all_envs = True
            folder = "all_envs"
        else:
            all_envs = False
            folder = environment
        self._parameter_mapping = self.get_mapping_file("parameters", region, environment, all_envs)
        self._template_mapping = self.get_mapping_file("templates", region, environment, all_envs)
        if all_envs:
            folder = "all_envs"
        else:
            folder = environment
        self.template_path = template_file_path
        self.rename_logger(folder)
        self.parameter_path = self.get_parameter_file_path(environment, all_envs)
        self.stack_name = self.determine_stack_name(stack_prefix)
        if template_file_path.exists():
            self.parameters = self.create_parameter_list()
            self.size = Path(self.template_path).stat().st_size
        else:
            self.size = 0
        self._cf = boto3.client('cloudformation', region_name=region)
        if self.size > 51200:
            self._upload_bucket = AWSS3UploadBucket(region, upload_bucket_name)
        self.role_arn = "".join(("arn:aws:iam::", str(account_number), ":role/", execution_role_name))
        self._termination_protection = protection

    # Rename logger so it's easier to identify the source when running
    # stack actions in parallel
    def rename_logger(self, folder):
        global logger
        logger_name = "-".join((folder, self.template_path.name))
        logger = logging.getLogger(logger_name)

    def get_mapping_file(self, map_type, region, environment, all_envs):
        mapping = Mappings(map_type, region, environment, all_envs)
        return mapping

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
        template_filename = self.template_path.name
        param_dir = self.template_path.parents[1] / "parameters"
        if all_envs:
            default_name = ".".join((prefix, environment, "json"))
        else:
            default_name = ".".join((prefix, "json"))
        # Attempt to get name from mapping file. Use default if name is not found
        name = None
        if self._parameter_mapping.mapping is not None:
            name = self._parameter_mapping.get_mapping_value(template_filename, "parameters")
        if name is None:
            name = default_name
        path = param_dir / name
        if path.exists():
            return path
        else:
            message = "Parameter file [{}] not found for template: {}".format(path.as_posix(),template_filename)
            logger.warning(message)
            return None

    @staticmethod
    def load_file(file_path):
        if file_path is not None:
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
        else:
            return None
        
    def load_template_body(self):
        body = self.load_file(self.template_path)
        return body

    def upload_template(self):
        logger.info('{} file size is larger than quota. Uploading to {}'.format(self.template_path.name, self._upload_bucket.bucket_name))
        self._upload_bucket.upload_file(self.template_path)
        object_url = "".join(("https://", self._upload_bucket.bucket_name, ".s3.amazonaws.com/", self.template_path.name))
        return object_url

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
                logger.info("Parameter file {} contains parameters that are not used in the template. File will be ignored.".format(self.parameter_path))
            return parameterlist
        if parameters is not None:
            logger.info("Loading parameter file: {}".format(self.parameter_path))
            paramObj = json.loads(parameters)
            paramkeys = list(paramObj.keys())
            for y in paramObj:
                if y in temp_params:
                    paramValue = paramObj[y]
                    entry = {
                            'ParameterKey': str(y),
                            'ParameterValue': str(paramValue)
                        }
                    parameterlist.append(entry)
                    paramkeys.remove(y)
                    del[temp_params[y]]
                else:
                    logger.info("[{}] is defined in parameter file but not listed in the template file. Value will be ignored.".format(y))
        if temp_params != {}:
            logger.info("Values for some defined parameters are not found in the parameters file. Checking template for default values...")
            for param in temp_params:
                try:
                    default = temp_params[param]['Default']
                    entry = {
                            'ParameterKey': str(param),
                            'ParameterValue': str(default)
                        }
                    parameterlist.append(entry)
                except KeyError:
                    logger.error("Required parameter [{}] missing from parameter file and does not have a default value. Aborting operation.".format(param))
                    exit(1)
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

    @boto3_error_decorator(logger)
    def get_stack_events(self, token=None, output="errors"):
        resources = []
        try:
            if token is None:
                response = self._cf.describe_stack_events(StackName=self.stack_name)
            else:
                response = self._cf.describe_stack_events(StackName=self.stack_name, NextToken=token)
            events = response['StackEvents']
            last_event_time = events[-1]['Timestamp']
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
                if "FAILED" in resource_status:
                    try:
                        reason = event['ResourceStatusReason']
                    except KeyError:
                        reason = "N/A"
                    if output == "errors" and timestamp > self._initial_time:
                        id = event['LogicalResourceId']
                        message = "".join(("[", id, "]: ", reason))
                        logger.error(message)
                    if output == "resources":
                        fail_message = "The following resource(s) failed to delete: ["
                        if fail_message in reason:
                            resource_string = reason.split(fail_message)[-1].rstrip("]. ")
                            resources_list = resource_string.split(", ")
                            resources.extend(resources_list)
            if next_token is not None and output == "errors":
                self.get_stack_events(token=next_token)
            elif output == "resources":
                # Remove duplicate resources from resource list
                resources = list(set(resources))
                return resources
        except ClientError as err:
            if err.response['Error']['Code'] == 'ValidationError'and err.response['Error']['Message'] == 'Stack [{}] does not exist'.format(self.stack_name):
                message = "Deletion of stack [{}]".format(self.stack_name) + \
                    " complete. No further stack events will be gathered."
                logger.info(message)

    def monitor_stack_progress(self, action_type):
        status = ''
        if action_type == "CREATE":
            self.failure_statuses.append('DELETE_IN_PROGRESS')
        #TODO - Add a break if possible so this doesn't run forever
        while status not in self.success_statuses and status not in self.failure_statuses and status is not None:
            sleep(self._check_period)
            status = self.get_stack()
            if status is None and action_type == "DELETE":
                logger.info("Stack {} has been deleted".format(self.stack_name))
                status = 'DELETE_COMPLETE'
                return "SUCCESS"
            elif status in self.success_statuses:
                logger.info("Stack action {} complete for stack: {}".format(action_type,self.stack_name))
                return "SUCCESS"
            elif status in self.failure_statuses:
                logger.error("Stack action {} failed on stack {}. Gathering details...".format(action_type,self.stack_name))
                self.get_stack_events()
                return "FAILURE"
            elif status is None:
                logger.info("Stack {} not found.".format(self.stack_name))
                # This scenario should not occur, but considering a
                # failure if stack can't be found for CREATE or UPDATE actions
                return "FAILURE"
            else:
                logger.info("Stack action {} still in progress for stack {}...".format(action_type,self.stack_name))

    @boto3_error_decorator(logger)
    def create_stack(self):
        logger.info("Creating stack: {}".format(self.stack_name))
        try:
            if 0 < self.size <= 51200:
                body = self.load_template_body()
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
                object_url = self.upload_template()
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
            return None
        except ClientError as err:
            if err.response['Error']['Code'] == "AlreadyExistsException":
                message = "Stack [{}] already ".format(self.stack_name) + \
                    "exists. No action taken."
                logger.info(message)
                return "SUCCESS"
            else:
                raise err

    @boto3_error_decorator(logger)
    def update_stack(self):
        logger.info("Updating stack: {}".format(self.stack_name))
        try:
            if 0 < self.size <= 51200:
                body = self.load_template_body()
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
                object_url = self.upload_template()
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
            return None
        except ClientError as err:
            if err.response['Error']['Code'] == 'ValidationError' and err.response['Error']['Message'] == 'No updates are to be performed.':
                logger.info("No updates required for stack: {}".format(self.stack_name))
                return "SUCCESS"
            elif err.response['Error']['Code'] == 'ValidationError' and err.response['Error']['Message'] == 'Stack [{}] does not exist'.format(self.stack_name):
                logger.info("Stack {} does not exist. Attempting to create stack...".format(self.stack_name))
                status = self.run_stack_actions("CREATE")
                return status
            else:
                raise err

    @boto3_error_decorator(logger)
    def describe_change_set(self, change_set_id=None):
        if change_set_id is None:
            change_set_id = "-".join((self.changeset_prefix,self.stack_name))
        logger.info("Getting details for change set: {}".format(change_set_id))
        response = self._cf.describe_change_set(ChangeSetName=change_set_id, StackName=self.stack_name)
        id = response['ChangeSetId']
        status = response['Status']
        changes = response['Changes']
        return (id, status, changes)

    @boto3_error_decorator(logger)
    def create_change_set(self):
        logger.info("Creating change set for stack: {}".format(self.stack_name))
        try:
            if 0 < self.size <= 51200:
                body = self.load_template_body()
                response = self._cf.create_change_set(
                    StackName=self.stack_name,
                    TemplateBody=body,
                    Parameters=self.parameters,
                    Capabilities=[
                        'CAPABILITY_IAM',
                        'CAPABILITY_NAMED_IAM',
                        'CAPABILITY_AUTO_EXPAND',
                    ],
                    RoleARN=self.role_arn,
                    ChangeSetName="-".join((self.changeset_prefix,self.stack_name)),
                    Description='Update to stack via GitHub Actions',
                    ChangeSetType='UPDATE'
                )
            else:
                object_url = self.upload_template()
                response = self._cf.create_change_set(
                    StackName=self.stack_name,
                    TemplateURL=object_url,
                    Parameters=self.parameters,
                    Capabilities=[
                        'CAPABILITY_IAM',
                        'CAPABILITY_NAMED_IAM',
                        'CAPABILITY_AUTO_EXPAND',
                    ],
                    RoleARN=self.role_arn,
                    ChangeSetName="-".join((self.changeset_prefix,self.stack_name)),
                    Description='Update to stack via GitHub Actions',
                    ChangeSetType='UPDATE'
                )
            id = response['Id']
            waiter = self._cf.get_waiter('change_set_create_complete')
            waiter.wait(
                ChangeSetName=id,
                WaiterConfig={
                    'Delay': self._check_period
                }
            )
            logger.info("Change set created: {}".format(id))
            return id
        except WaiterError as err:
            reason = err.last_response['StatusReason']
            if reason == "The submitted information didn't contain changes. Submit different information to create a change set.":
                logger.info("Change set did not contain any changes. Deleting change set...")
                self.delete_change_set()
            else:
                raise err
        except ClientError as err:
            if err.response['Error']['Code'] == 'AlreadyExistsException':
                logger.info("Conflicting change set exists. Deleting conflicting change set...")
                id = self.describe_change_set()[0]
                self.delete_change_set(id)
                logger.info("Change set deleted. Attempting to create new change set...")
                self.create_change_set()
            else:
                raise err

    @boto3_error_decorator(logger)
    def delete_change_set(self, change_set_id=None):
        if change_set_id is None:
            change_set_id = "-".join((self.changeset_prefix,self.stack_name))
        logger.info("Deleting change set: {}".format(change_set_id))
        self._cf.delete_change_set(ChangeSetName=change_set_id, StackName=self.stack_name)

    #TODO - Add a way to trigger the skipping of failed resources (via config?)
    @boto3_error_decorator(logger)
    def delete_stack(self, retain_list=[], skip_failed_resources=False):
        logger.info("Deleting stack: {}".format(self.stack_name))
        stack_status = self.get_stack()
        if stack_status is None:
            logger.info("Stack {} has been deleted".format(self.stack_name))
            status = 'SUCCESS'
            return status
        elif skip_failed_resources:
            if stack_status == 'DELETE_FAILED':
                logger.info("Gathering failed resources from previous deletion attempt...")
                retain_list = self.get_stack_events(output="resources")
                logger.info("Attempting to delete stack while retaining the following resources: {}".format(", ".join(retain_list)))
        self._cf.delete_stack(
            StackName=self.stack_name,
            RetainResources=retain_list,
            RoleARN=self.role_arn
        )
        return None

    def run_stack_actions(self, action_type):
        if action_type == "CREATE":
            status = self.create_stack()
        elif action_type == "UPDATE":
            status = self.update_stack()
        elif action_type == "DELETE":
            status = self.delete_stack()
        if status is not None:
            outcome = status
        else:
            outcome = self.monitor_stack_progress(action_type)
        return outcome