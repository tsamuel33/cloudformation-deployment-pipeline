import configparser
from os.path import isfile, basename
from pathlib import Path
from .errors import ConfigurationError
import logging

# Set up logger
logger = logging.getLogger(basename(__file__))

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
    config_file = str(root_dir / 'config')

    def __init__(self):
        self.initialize_config()

    def initialize_config(self):
        # Check if config file already exists
        file_exists = isfile(self.config_file)
        if not file_exists:
            message = "Configuration file does not exist at: {}. ".format(
                self.config_file) + "Please create the file and commit " + \
                "to the repository configuration options"
            raise ConfigurationError(message)
        
        self.config = configparser.ConfigParser()
        self.config.read_file(open(self.config_file))
    
    def get_config_value(self, section, attribute):
        try:
            value = self.config[section].get(attribute)
            return value
        except KeyError:
            message = "Configuration is missing section: {}".format(section)
            logger.error(message)
            raise ConfigurationError(message)