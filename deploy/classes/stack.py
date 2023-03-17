import json
import yaml
import os
import boto3
import logging

# Set up logger
logger = logging.getLogger(os.path.basename(__file__))

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

    default_stack_prefix = "managed-app-"

    def __init__(self, template_file_name, parameter_file_name=None, region='us-east-1', stackname=None) -> None:
        self.template_filename = self.get_file_name(template_file_name)
        self.parameter_filename = self.get_file_name(parameter_file_name)
        self.determine_stack_name(stackname)
        self.region = region
        self.cf = boto3.client('cloudformation', region_name=self.region)

    @staticmethod
    def get_file_name(name) -> str:
        if name is not None:
            file = name.split(".")[0]
        else:
            file = ''
        return file

    def determine_stack_name(self, name):
        if name is not None:
            self.stack_name = name
        else:
            self.stack_name = self.default_stack_prefix + self.template_filename

    def create_parameter_list(parameter_file, dynamic_param_dict):
        parameterlist = []
        with open(parameter_file, 'r') as myParameterFile:
            paramData = myParameterFile.read()
        paramObj = json.loads(paramData)
        for x in dynamic_param_dict:
            paramObj[x] = dynamic_param_dict[x]
        for y in paramObj:
            paramValue = paramObj[y]
            entry = {
                    'ParameterKey': y,
                    'ParameterValue': paramValue,
                    'UsePreviousValue': False
                }
            parameterlist.append(entry)
        return parameterlist

    def get_stack(self):
        response = self.cf.describe_stacks(StackName=self.stack_name)
        status = response['Stacks'][0]['StackStatus']
        return status

    # TODO - set this up to take yaml and json
    @staticmethod
    def load_template(file):
        with open(file, 'r') as myFile:
            data = myFile.read()
        return data

    def create_stack(self, parameters,
            account_id, template_string, execution_role_name):
        stackCreateResponse = self.cf.create_stack(
            StackName=self.stack_name,
            TemplateBody=template_string,
            Parameters=parameters,
            # TimeoutInMinutes=123,
            Capabilities=[
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            RoleARN="".join(('arn:aws:iam::', account_id, ':role/app/', execution_role_name)),
            # EnableTerminationProtection=True|False,
            OnFailure='DELETE'
        )
        return stackCreateResponse

    def create_stack_s3(self, parameters,
            account_id,template_url, execution_role_name):
        stackcreateresponse = self.cf.create_stack(
            StackName=self.stack_name,
            TemplateURL=template_url,
            Parameters=parameters,
            # TimeoutInMinutes=123,
            Capabilities=[
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            RoleARN="".join(('arn:aws:iam::', account_id, ':role/app/', execution_role_name)),
            # EnableTerminationProtection=True|False,
            OnFailure='DELETE'
        )
        return stackcreateresponse

    def update_stack(self, parameters,
            account_id, template_string, execution_role_name):
        stackupdateresponse = self.cf.update_stack(
            StackName=self.stack_name,
            TemplateBody=template_string,
            Parameters=parameters,
            Capabilities=[
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            RoleARN="".join(('arn:aws:iam::', account_id, ':role/app/', execution_role_name)),
            DisableRollback=False
        )
        return stackupdateresponse

    def update_stack_s3(self, parameters,
            account_id,template_url, execution_role_name):
        stackupdateresponse = self.cf.update_stack(
            StackName=self.stack_name,
            TemplateURL=template_url,
            Parameters=parameters,
            Capabilities=[
                'CAPABILITY_IAM',
                'CAPABILITY_NAMED_IAM',
                'CAPABILITY_AUTO_EXPAND'
            ],
            RoleARN="".join(('arn:aws:iam::', account_id, ':role/app/', execution_role_name)),
            DisableRollback=False
        )
        return stackupdateresponse