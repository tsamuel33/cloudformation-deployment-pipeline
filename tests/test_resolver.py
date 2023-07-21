import pytest
from pathlib import Path
from scripts.classes.stack import AWSCloudFormationStack
import scripts.classes.resolver

class TestCloudFormationResolver:

    root_dir = Path(__file__).parents[1]
    region = "us-east-1"
    template_dir = root_dir / "deployments" / region / "all_envs" / "templates"
    resolver_path = root_dir / "scripts" / "classes" / "resolver.py"


    @pytest.fixture
    def stack_fixture_example(self):
        stack = AWSCloudFormationStack(self.template_dir / "example.template", environment="dev", account_number=123456789012, execution_role_name="fakerole")
        return stack

    def test_template_resolution(self, stack_fixture_example):
        scripts.classes.resolver.main(stack_fixture_example)