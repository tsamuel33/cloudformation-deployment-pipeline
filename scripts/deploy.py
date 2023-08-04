import argparse
import logging
from pathlib import Path
from sys import exit

from scripts.classes.scope import PipelineScope
from scripts.classes.configuration import Configuration

# Set up logger
logger = logging.getLogger(Path(__file__).name)

# # Arguments
parser = argparse.ArgumentParser(description='Accept AWS parameters')
parser.add_argument('--branch', type=str, help='GitHub branch containing templates', required=True)
parser.add_argument('--account_number', type=str, help='AWS account in which templates will be deployed', required=False)
parser.add_argument('--job', type=str, help='Name of GitHub Action job to run', required=True)
args = vars(parser.parse_args())

def lint_templates(pipeline_object):
    exit_code = pipeline_object.lint_templates()
    return exit_code

def validate_templates(configuration, pipeline_object, account_number):
    role_name = configuration.get_config_value("stack_execution_role_name")
    check_period = configuration.get_config_value("cf_check_period_seconds", 15)
    stack_prefix = configuration.get_config_value("stack_name_prefix")
    protection = configuration.get_config_value("termination_protection_enabled", False)
    upload_bucket_name = configuration.get_config_value("cloudformation_upload_bucket_name")
    validation_engine = configuration.get_config_value("policy_as_code_provider")
    account = account_number
    if validation_engine is None:
        logger.info("No policy as code provider selected. Skipping validation...")
        exit_code = 0
        return exit_code
    if validation_engine == "guard":
        exit_code = pipeline_object.cfn_guard_validate(account, role_name, check_period, stack_prefix, protection, upload_bucket_name)
    elif validation_engine == "opa":
        exit_code = pipeline_object.opa_validate(account, role_name, check_period, stack_prefix, protection, upload_bucket_name)
    return exit_code

def deploy(configuration, pipeline_object, account_number):
    role_name = configuration.get_config_value("stack_execution_role_name")
    check_period = configuration.get_config_value("cf_check_period_seconds", 15)
    stack_prefix = configuration.get_config_value("stack_name_prefix")
    protection = configuration.get_config_value("termination_protection_enabled", False)
    upload_bucket_name = configuration.get_config_value("cloudformation_upload_bucket_name")
    exit_code = pipeline_object.deploy_scope(account_number, role_name, check_period,
                     stack_prefix, protection, upload_bucket_name)
    #TODO - Test SAM deployments
    return exit_code

def prepare_to_deploy(job):
    logger.info("Preparing to {} templates...".format(job))
    branch = args['branch']
    config = Configuration(branch)
    environment = config.environment
    if job == 'setup':
        pipeline = None
    else:
        pipeline = PipelineScope(branch, environment)
    return (config, pipeline)

def main(job):
    prep = prepare_to_deploy(job)
    config = prep[0]
    pipeline = prep[1]
    create_length = len(pipeline.create_list)
    update_length = len(pipeline.update_list)
    delete_length = len(pipeline.delete_list)
    if create_length + update_length + delete_length == 0:
        message = "Submitted templates are same as previous" + \
                    " deployment. No actions taken."
        logger.info(message)
        exit_code = 0
    elif job == 'lint':
        lint_exit_code = lint_templates(pipeline)
        exit_code = lint_exit_code
    elif job == 'validate':
        validation_exit_code = validate_templates(config, pipeline, args['account_number'])
        exit_code = validation_exit_code
    elif job == 'deploy':
        deployment_exit_code = deploy(config, pipeline, args['account_number'])
        exit_code = deployment_exit_code
    # Return exit code to GitHub Actions by printing
    print(exit_code)

if __name__ == "__main__":
    main(args['job'])