import configparser
import logging
from pathlib import Path

# Set up logger
logger = logging.getLogger(Path(__file__).name)

class ConfigurationError(Exception):
    """Raises an exception when...
    
    Attributes:
        message -- message indicating the specifics of the error
    """

    def __init__(self, message='Generic error') -> None:
        self.message = message
        super().__init__(self.message)

class Configuration:
    """
    A base class used to represent the configuration settings for the
    deployment pipeline.
    ...

    Attributes
    ----------
    # config : obj
    #     Object representing the configuration file
    """

    root_dir = Path(__file__).parents[2]
    config_file = root_dir / 'config'
    required_settings = [
        "environment",
        {"github_secret_type": ["repository", "environment", "organization"]},
        "stack_execution_role_name",
        "account_number_secret_name"
    ]

    def __init__(self, branch):
        self.config = self.initialize_config()
        self.section = branch
        self.branch_type = self.validate_configuration()
        if self.branch_type == "minor":
            # Add section for minor branch to get default environment
            self.config.add_section(branch)
            self.section = self.get_config_value("lowest_branch")
            message = "Using settings of branch: {}".format(self.section)
            logger.info(message)
            # Clean up added section to prevent unwanted errors
            self.config.remove_section(branch)
        self.environment = self.get_config_value("environment")

    def initialize_config(self):
        # Check if config file already exists
        file_exists = Path.is_file(self.config_file)
        if not file_exists:
            message = "Configuration file does not exist at: {}. ".format(
                self.config_file) + "Please create the file and commit " + \
                "to the repository"
            raise ConfigurationError(message)
        config = configparser.ConfigParser()
        config.read_file(open(self.config_file))
        return config

    # TODO - If config value is wrapped in quotations, validation test fails. Ease this contraint
    def get_config_value(self, attribute, fallback=None):
        try:
            value = self.config[self.section].get(attribute, fallback)
            if value is not None:
                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                return value
        except KeyError:
            message = "Configuration is missing section: {}".format(self.section)
            logger.error(message)
            raise ConfigurationError(message)
        
    # Ensure that required settings exist in the pipeline config
    def validate_configuration(self):
        logger.info("Validating pipeline configuration for branch: {}".format(self.section))
        if self.section in self.config.sections():
            branch_type = "major"
            for item in self.required_settings:
                if type(item) == str:
                    setting = self.get_config_value(item)
                elif type(item) == dict:
                    key = list(item.keys())[0]
                    values = item[key]
                    setting = self.get_config_value(key)
                    if setting not in values:
                        message = "Required setting ({}) has invalid value: {}. Valid entries are: {}".format(key, setting, ", ".join(values))
                        logger.error(message)
                        raise ConfigurationError(message)
                if setting is None:
                    message = "Required setting ({}) is missing from section {} of the config file.".format(item, self.section)
                    logger.error(message)
                    raise ConfigurationError(message)
        else:
            branch_type = "minor"
            message = "Configuration is missing section for branch: " + \
                "{}. Running as minor branch...".format(self.section)
            logger.info(message)
        return branch_type