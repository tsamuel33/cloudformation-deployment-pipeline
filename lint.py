import subprocess
from pathlib import Path

commands = [
    "cfn-lint",
    "--non-zero-exit-code",
    "error",
    "-t"
]

deployment_dir = Path(__file__).parent / "deployments"
template_dir = deployment_dir/"us-east-1"/"all_envs"/"templates"/"cloudformation"

for template in template_dir.iterdir():
    if template.is_file() and template.suffix in [".template", ".yaml", ".yml", ".json"]:
        commands.append(template)

subprocess.run(commands)