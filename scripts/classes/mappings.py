import json
import logging
from pathlib import Path

# Set up logger
logger = logging.getLogger(Path(__file__).name)

class Mappings:

    root_dir = Path(__file__).parents[2]
    deployment_dir = root_dir / "deployments"

    def __init__(
            self, mapping_type, region, environment,
            all_environments=False) -> None:
        if all_environments:
            mapping_dir = self.deployment_dir/region/"all_envs"/"mappings"
            mapping_file_name = ".".join((mapping_type, environment, "json"))
        else:
            mapping_dir = self.deployment_dir/region/environment/"mappings"
            mapping_file_name = ".".join((mapping_type, "json"))
        self.mapping_file_path = mapping_dir / mapping_file_name
        self.mapping = self.load_mapping_file(mapping_type)

    def load_mapping_file(self, mapping_type):
        try:
            with open(self.mapping_file_path, "r") as file:
                loaded_file = json.load(file)
                file.close()
                return loaded_file
        except FileNotFoundError:
            if mapping_type == "parameters":
                message = "File {} not".format(self.mapping_file_path) + \
                    " found. Default naming convention will be " + \
                    "used to locate parameter files."
            elif mapping_type == "templates":
                message = "File {} not".format(self.mapping_file_path) + \
                    " found. Custom names will not be used for stacks " + \
                    "and previously existing stacks will not be imported " + \
                    "into the pipeline"
            logger.warning(message)
            return None

    def get_mapping_value(self, key):
        value = self.mapping[key]
        return value
