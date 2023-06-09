import logging
import subprocess
from .mappings import Mappings
from .configuration import Configuration
from pathlib import Path
from git import Repo
from git.exc import GitCommandError
from pathlib import Path

# Set up logger
logger = logging.getLogger(Path(__file__).name)

class PipelineScope:

    root_dir = Path(__file__).parents[2]
    __repo = Repo(root_dir)
    __remote = __repo.remote()
    __head_commit = __repo.head.commit
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
        "-r"
    ]

    def __init__(self, branch) -> None:
        self.create_list = []
        self.update_list = []
        self.delete_list = []
        self.environment = Configuration(branch).environment
        self.regions = self.get_regions()
        self.deploy_tag = "-".join((self.tag_prefix,branch))
        self.__last_deploy = self.get_last_deployment_commit(self.deploy_tag)
        self.__diff = self.get_diff()
        self.set_scope()


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

    def get_all_environments(self):
        environments = []
        for region in self.regions:
            region_dir = self.deployment_dir / region
            for env in region_dir.iterdir():
                if env.is_dir():
                    if env.name not in environments:
                        environments.append(env.name)
        environments.sort()
        return environments

    def get_last_deployment_commit(self, target_tag):
        try:
            commit = self.__repo.tag(target_tag).commit
        except ValueError as err:
            if err.args[0] == "Reference at " + \
                "'refs/tags/{}' does not exist".format(target_tag):
                message = "Tag '{}' does not exist. ".format(target_tag) + \
                    "Pipeline will attempt to deploy all relevant " + \
                    "CloudFormation stacks."
                logger.warning(message)
            commit = None
        finally:
            return commit

    def create_new_tag(self, target_tag, commit):
        logger.info("Tagging commit...")
        try:
            new_tag = self.__repo.create_tag(target_tag, commit)
            return new_tag
        except GitCommandError as err:
            if "tag '{}' already exists".format(target_tag) in err.stderr:
                existing_tag = self.__repo.tag(target_tag)
                if str(existing_tag.commit) == str(commit):
                    logger.info("Tag already exists on commit.")
                    return existing_tag
                else:
                    logger.error("Tag already exists on a different commit.")
                    raise err
            else:
                raise err

    def push_tag_to_remote(self, target_tag):
        logger.info("Pushing tag to remote repository...")
        tag = self.__repo.tag(target_tag)
        self.__remote.push(tag)

    def delete_tag(self, target_tag):
        logger.info("Deleting tag...")
        try:
            self.__repo.delete_tag(target_tag)
        except GitCommandError as err:
            if "tag '{}' not found".format(target_tag) in err.stderr:
                logger.info("Tag ({}) already deleted.".format(target_tag))

    def delete_tag_from_remote(self, target_tag):
        try:
            self.delete_tag(target_tag)
            logger.info("Removing tag from remote repository...")
            self.__remote.push(refspec=(':{}'.format(target_tag)))
        except GitCommandError as err:
            if "'{}': remote ref does not exist".format(target_tag) in err.stderr:
                logger.info("Tag ({}) already deleted from remote.".format(target_tag))

    def update_deployment_checkpoint(self):
        if self.__last_deploy is not None:
            self.delete_tag_from_remote(self.deploy_tag)
        tag = self.create_new_tag(self.deploy_tag, self.__head_commit)
        self.push_tag_to_remote(tag)

    def get_diff(self):
        if self.__last_deploy is None:
            diff = None
        else:
            diff = self.__last_deploy.diff(self.__head_commit)
        return diff

    def get_file_type(self, file_path):
        file_parts = file_path.parts
        if "deployments" in file_parts and file_path.suffix in self.valid_template_suffixes:
            # Only consider changes in parameter or template files as updates
            # to mappings should not trigger actions on their own, and will
            # should be captured by corresponding template/parameter changes
            if file_parts[-2] in ["parameters", "templates"]:
                file_type = file_parts[-2]
            else:
                file_type = None
            if file_type is None:
                message = "Template file {} ".format(str(file_path)) + \
                    "has invalid folder structure and will be ignored."
                logger.warning(message)
        else:
            file_type = None
        return file_type

    @staticmethod
    def get_file_path(change_type, file):
        if change_type == "D":
            path = Path(file.a_path)
        elif change_type in ["A", "M", "R"]:
            path = Path(file.b_path)
        return path

    @staticmethod
    def load_file(file_path):
        try:
            with open(file_path, 'r') as myFile:
                data = myFile.read()
            return data
        except FileNotFoundError:
            message = "File ({}) not found. ".format(file_path.as_posix()) + \
                "No stack actions will be taken on the file."
            logger.warning(message)
            return None

    def get_target_envs(self, all_envs=False):
        if all_envs or self.environment is None:
            target_envs = self.get_all_environments()
        else:
            target_envs = ["all_envs", self.environment]
        return target_envs

    def append_file(self, change_type, template_file_path):
        data = self.load_file(template_file_path)
        if data is not None:
            if change_type == "A" and template_file_path not in self.create_list:
                self.create_list.append(template_file_path)
            elif change_type in ["M", "R"] and template_file_path not in self.update_list:
                self.update_list.append(template_file_path)
            elif change_type == "D" and template_file_path not in self.delete_list:
                self.delete_list.append(template_file_path)

    def get_template_for_param_mapping(self, param_file_path):
        template_path = None
        template_dir = param_file_path.parents[1] / "templates"
        parts = param_file_path.parts
        region = parts[-4]
        env = parts[-3]
        if env == "all_envs":
            all_envs = True
        else:
            all_envs = False
        param_mapping = Mappings("parameters", region, self.environment, all_envs)
        if param_mapping.mapping is not None:
            template_names = list(param_mapping.mapping.keys())
            for name in template_names:
                param_file = param_mapping.get_mapping_value(name, "parameters")
                if param_file == param_file_path.name:
                    template_path = template_dir / name
        if param_mapping.mapping is None or template_path is None:
            message = "Unable to identify template file corresponding to " + \
                "parameter file '{}' ".format(param_file_path.as_posix()) + \
                "via a mapping file. Attempting to locate template via " + \
                "default naming convention..."
            logger.warning(message)
            matching_templates = []
            for template in template_dir.iterdir():
                if (template.is_file() and template.stem ==
                        param_file_path.stem and template.suffix in
                        self.valid_template_suffixes):
                    matching_templates.append(template)
            if len(matching_templates) == 1:
                template_path = matching_templates[0]
            elif len(matching_templates) == 0:
                message = "No template found corresponding " + \
                    "to {}. ".format(param_file_path.as_posix()) + \
                    "File will be ignored"
                logger.warning(message)
            elif len(matching_templates) > 1:
                message = "Multiple files found corresponding to the " + \
                    "default naming convention: " + \
                    "[{}].".format(", ".join(map(str,matching_templates))) + \
                    " Files will be ignored if they are not located in " + \
                    "the repo's diff."
                logger.warning(message)
        return template_path

    def set_scope(self):
        if self.environment is None:
            self.get_all_templates(True)
        elif self.__diff is None:
            self.get_all_templates()
        else:
            change_types = ["A", "M", "D", "R"]
            environments = self.get_target_envs()
            for change_type in change_types:
                diff_files = self.__diff.iter_change_type(change_type)
                for file in diff_files:
                    path = self.get_file_path(change_type, file)
                    file_type = self.get_file_type(path)
                    if file_type is not None:
                        if file_type == "parameters" and change_type != "D":
                            template_path = self.get_template_for_param_mapping(path)
                        elif file_type == "templates":
                            template_path = path
                        if template_path is not None:
                            env = template_path.parts[-3]
                            if env in environments:
                                self.append_file(change_type, template_path)

    def crawl_template_dir(self, template_dir):
        templates = []
        if template_dir.is_dir():
            message = "Gathering templates from directory: " + \
                "{}".format(template_dir.as_posix())
            logger.info(message)
            for template in template_dir.iterdir():
                if template.is_file() and template.suffix in self.valid_template_suffixes:
                    templates.append(template)
        return templates

    def get_all_templates(self, all=False):
        template_file_paths = []
        if all:
            logger.info("Gathering all template files...")
        environments = self.get_target_envs(all)
        for region in self.regions:
            region_dir = self.deployment_dir / region
            for env in environments:
                template_dir = region_dir / env / "templates"
                templates = self.crawl_template_dir(template_dir)
                template_file_paths.extend(templates)
        for template in template_file_paths:
            self.append_file("M", template)

    def lint_templates(self):
        for region in self.regions:
            self.lint_commands.append(region)
        self.lint_commands.append("-t")
        for template in self.create_list:
            self.lint_commands.append(template.as_posix())
        for template in self.update_list:
            self.lint_commands.append(template.as_posix())
        if self.lint_commands[-1] == "-t":
            logger.info("No templates in scope for linting.")
            code = 0
        else:
            code = subprocess.run(self.lint_commands).returncode
        return code

    def deploy_templates(self):
        pass
