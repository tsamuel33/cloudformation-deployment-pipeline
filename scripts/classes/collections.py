from pathlib import Path

class PipelineScope:

    root_dir = Path(__file__).parents[2]
    deployment_dir = root_dir / "deployments"

    def __init__(self) -> None:
        self.get_regions()
        self.get_environments()

    def get_regions(self):
        self.regions = []
        for region in self.deployment_dir.iterdir():
            if region.is_dir() and region not in self.regions:
                self.regions.append(region.name)

    def get_environments(self):
        self.environments = []
        for region in self.regions:
            region_dir = self.deployment_dir / region
            for env in region_dir.iterdir():
                if env.is_dir() and env.name != "all_envs" and env.name not in self.environments:
                    self.environments.append(env.name)

    def get_cloudformation_templates(self):
        pass

    def get_sam_templates(self):
        pass