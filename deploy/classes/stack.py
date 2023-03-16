import json
# import yaml
import os
import boto3

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
        self.s3 = boto3.client('s3', region_name=self.region)

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


    # def create_stack(self):
    #     response = self.cf.create_stack(
    #         StackName='string',
    #         TemplateBody='string',
    #         TemplateURL='string',
    #         Parameters=[
    #             {
    #                 'ParameterKey': 'string',
    #                 'ParameterValue': 'string',
    #                 'UsePreviousValue': True|False,
    #                 'ResolvedValue': 'string'
    #             },
    #         ],
    #         DisableRollback=True|False,
    #         RollbackConfiguration={
    #             'RollbackTriggers': [
    #                 {
    #                     'Arn': 'string',
    #                     'Type': 'string'
    #                 },
    #             ],
    #             'MonitoringTimeInMinutes': 123
    #         },
    #         TimeoutInMinutes=123,
    #         NotificationARNs=[
    #             'string',
    #         ],
    #         Capabilities=[
    #             'CAPABILITY_IAM'|'CAPABILITY_NAMED_IAM'|'CAPABILITY_AUTO_EXPAND',
    #         ],
    #         ResourceTypes=[
    #             'string',
    #         ],
    #         RoleARN='string',
    #         OnFailure='DO_NOTHING'|'ROLLBACK'|'DELETE',
    #         StackPolicyBody='string',
    #         StackPolicyURL='string',
    #         Tags=[
    #             {
    #                 'Key': 'string',
    #                 'Value': 'string'
    #             },
    #         ],
    #         ClientRequestToken='string',
    #         EnableTerminationProtection=True|False
    #     )