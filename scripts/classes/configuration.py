import configparser
from pathlib import Path
import logging

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
        {"github_secret_type": ["repository", "deployment"]},
        "stack_execution_role_name",
        "account_number_secret_name"
    ]

    def __init__(self, branch):
        self.initialize_config()
        self.section = branch
        self.validate_configuration()
        self.environment = self.get_config_value("environment")

    def initialize_config(self):
        # Check if config file already exists
        file_exists = Path.is_file(self.config_file)
        if not file_exists:
            message = "Configuration file does not exist at: {}. ".format(
                self.config_file) + "Please create the file and commit " + \
                "to the repository"
            raise ConfigurationError(message)

        self.config = configparser.ConfigParser()
        self.config.read_file(open(self.config_file))

    # TODO - If config value is wrapped in quotations, validation test fails. Ease this contraint
    def get_config_value(self, attribute):
        try:
            value = self.config[self.section].get(attribute)
            return value
        except KeyError:
            message = "Configuration is missing section: {}".format(self.section)
            logger.error(message)
            raise ConfigurationError(message)
        
    # Ensure that required settings exist in the pipeline config
    def validate_configuration(self):
        logger.info("Validating pipeline configuration for branch: {}".format(self.section))
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