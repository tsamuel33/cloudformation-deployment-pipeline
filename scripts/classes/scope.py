import logging
import subprocess
from .mappings import Mappings
from pathlib import Path
from git import Repo
from git.exc import GitCommandError
from pathlib import Path
from sys import exit

# Set up logger
logger = logging.getLogger(Path(__file__).name)

class PipelineScope:

    root_dir = Path(__file__).parents[2]
    repo = Repo(root_dir)
    deployment_dir = root_dir / "deployments"
    tag_prefix = "cf-deployment"
    valid_template_suffixes = [
        ".yaml",
        ".yml",
        ".template",
        ".json"
    ]
    valid_regions = [
        "af-south-1",
        "ap-east-1",
        "ap-northeast-1",
        "ap-northeast-2",
        "ap-northeast-3",
        "ap-south-1",
        "ap-south-2",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-southeast-3",
        "ap-southeast-4",
        "ca-central-1",
        "eu-central-1",
        "eu-central-2",
        "eu-north-1",
        "eu-south-1",
        "eu-south-2",
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        "me-central-1"
        "me-south-1",
        "sa-east-1",
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2"
    ]
    lint_commands = [
        "cfn-lint",
        "-I",
        "--non-zero-exit-code",
        "error",
        "-t"
    ]

    # TODO - Add target environment as variable. Pull from configuration or use config class
    def __init__(self, target_branch="main") -> None:
        self.deploy_tag = "-".join((self.tag_prefix,target_branch))
        self.regions = self.get_regions()
        self.environments = self.get_environments()
        self.last_deploy = self.get_last_deployment_commit(self.deploy_tag)
        self._diff = self.get_diff()
        self.create_list = []
        self.update_list = []
        self.delete_list = []
        if self._diff is not None:
            self.get_created_files()
            self.get_modified_files()
            self.get_deleted_files()

    def get_regions(self):
        regions = []
        for region in self.deployment_dir.iterdir():
            if region.is_dir():
                if region.name in self.valid_regions:
                    regions.append(region.name)
                else:
                    message = "{} is not a valid AWS ".format(region.name) + \
                        "region and files in this folder will be ignored." + \
                        " If this is a newer region, please add it to the" + \
                        " 'valid_regions' list in the " + \
                        "{} file.".format(Path(__file__))
                    logger.warning(message)
        regions.sort()
        return regions

    def get_environments(self):
        environments = []
        self.all_envs = False
        for region in self.regions:
            region_dir = self.deployment_dir / region
            for env in region_dir.iterdir():
                if env.is_dir():
                    if env.name == "all_envs":
                        self.all_envs = True
                    elif env.name not in environments:
                        environments.append(env.name)
        environments.sort()
        return environments

    def get_last_deployment_commit(self, target_tag):
        try:
            commit = self.repo.tag(target_tag).commit
        except ValueError as err:
            if err.args[0] == "Reference at " + \
                "'refs/tags/{}' does not exist".format(target_tag):
                message = "Tag '{}' does not exist. ".format(target_tag) + \
                    "Pipeline will attempt to create all relevant " + \
                    "CloudFormation stacks."
                logger.warning(message)
            commit = None
        finally:
            return commit

    def create_new_tag(self, target_tag, commit):
        try:
            new_tag = self.repo.create_tag(target_tag, commit)
            return new_tag
        except GitCommandError as err:
            if "tag '{}' already exists".format(target_tag) in err.stderr:
                existing_tag = self.repo.tag(target_tag)
                if existing_tag.commit == commit:
                    return existing_tag
                else:
                    logger.error("Tag already exists on a different commit.")
                    # exit()
            else:
                raise err

    def delete_tag(self, target_tag):
        self.repo.delete_tag(target_tag)

    def get_diff(self):
        head_commit = self.repo.head.commit
        if self.last_deploy is None:
            diff = None
        else:
            diff = head_commit.diff(self.last_deploy)
        return diff

    def get_file_type(self, file_path):
        file_parts = file_path.parts
        file_type = None
        if len(file_parts) == 5 and file_parts[3] == "parameters":
            file_type = "parameters"
        elif len(file_parts) == 6 and file_parts[3] == "templates":
            file_type = file_parts[4]
            if file_type not in ["cloudformation", "sam"]:
                message = "Template file {} has ".format(str(file_path)) + \
                    "invalid subfolder name. Name must be 'sam' or " + \
                    "'cloudformation'. File will be ignored."
                logger.warning(message)
        if file_type is None:
            message = "Template file {} ".format(str(file_path)) + \
                "has invalid file structure and will be ignored."
            logger.warning(message)
        return file_type

    @staticmethod
    def get_file_path(change_type, file):
        if change_type == "D":
            path = Path(file.a_path)
        else:
            path = Path(file.b_path)
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
            # TODO - Update warning message
            message = "Parameter file ({}) not found. ".format(filename) + \
                "Stack actions will fail if template does not have " + \
                "default values defined for all parameters."
            logger.warning(message)
            return None

    #TODO - Ensure appended files are located in valid regions and environments for this branch
    def append_file(self, change_type, template_file_path):
        if template_file_path is not None:
            data = self.load_file(template_file_path)
            if data is not None:
                if change_type == "A" and template_file_path not in self.create_list:
                    self.create_list.append(template_file_path)
                elif change_type == "M" and template_file_path not in self.update_list:
                    self.update_list.append(template_file_path)
                elif change_type == "D" and template_file_path not in self.delete_list:
                    self.delete_list.append(template_file_path)

    # Only need this for modifications or renames?
    def get_template_for_param_mapping(self, param_file_path):
        template_path = None
        # TODO - add logic to determine between sam and cloudformation. Remove hardcoded "cloudformation"
        template_dir = param_file_path.parents[1] / "templates" / "cloudformation"
        parts = param_file_path.parts
        region = parts[1]
        if parts[2] == "all_envs":
            all_envs = True
        else:
            all_envs = False
        # TODO - add logic to get environment. Remove hardcoded "dev"
        param_mapping = Mappings("parameters", region, "dev", all_envs)
        if param_mapping.mapping is not None:
            template_names = list(param_mapping.mapping.keys())
            for name in template_names:
                param_file = param_mapping.get_mapping_value(name, "parameters")
                if param_file == param_file_path.name:
                    template_path = template_dir / name
        return template_path

    #change_type, list_to_append, path_type, file_type (calculated)
    # TODO - create separate functions for each check
    def get_templates(self, change_type):
        diff_files = self._diff.iter_change_type(change_type)
        for file in diff_files:
            path = self.get_file_path(change_type, file)
            parts = path.parts
            if "deployments" in parts and path.suffix in self.valid_template_suffixes:
                type = self.get_file_type(path)
                if type == "parameters" and change_type != "D":
                    template_path = self.get_template_for_param_mapping(path)
                elif type is not None:
                    template_path = path
                self.append_file(change_type, template_path)

    def get_created_files(self):
        self.get_templates("A")

    def get_modified_files(self):
        self.get_templates("M")

    def get_deleted_files(self):
        self.get_templates("D")

    def lint_templates(self):
        for template in self.create_list:
            self.lint_commands.append(template.as_posix())
        for template in self.update_list:
            self.lint_commands.append(template.as_posix())
        code = subprocess.run(self.lint_commands).returncode
        return code
