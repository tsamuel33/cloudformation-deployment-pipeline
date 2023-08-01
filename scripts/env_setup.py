import argparse
import logging
from pathlib import Path

from scripts.classes.configuration import Configuration

# Set up logger
logger = logging.getLogger(Path(__file__).name)

# # Arguments
parser = argparse.ArgumentParser(description='Accept AWS parameters')
parser.add_argument('--branch', type=str, help='GitHub branch containing templates', required=True)
parser.add_argument('--github_env_var', type=str, help='Name of the variable to be set in the GitHub environment', required=False)
args = vars(parser.parse_args())

minor_branch_defaults = {
    "github_secret_type": "repository",
    "account_number_secret_name": "NULL_SECRET_NAME",
    "github_assumed_role_name": "None"
}

def main(branch, var):
    logger.info("Setting environment variable: {}...".format(var))
    config = Configuration(branch)
    branch_type = config.branch_type
    if var == "branch_type":
        value = branch_type
    elif var == "environment":
        value = config.environment
    elif branch_type == "minor":
        if var in ["github_secret_type", "account_number_secret_name", "github_assumed_role_name"]:
            value = minor_branch_defaults[var]
        elif var == "policy_as_code_provider":
            # Add section for minor branch in order to check if a default
            # policy as code value was set
            config.config.add_section(branch)
            value = config.get_config_value(var)
            # Clean up added section to prevent unwanted errors
            config.config.remove_section(branch)
    else:
        value = config.get_config_value(var)
    # Must use 'print' rather than 'return' to output value to GitHub Actions
    print(value)

if __name__ == "__main__":
    main(args['branch'], args['github_env_var'])