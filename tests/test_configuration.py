import pytest
# from pathlib import Path
from scripts.classes.configuration import Configuration

class TestConfiguration:

    configuration = Configuration("<branch_name>")

    def test_required_settings_entered(self):
        self.configuration.validate_configuration()

    def test_sample_environment(self):
        assert self.configuration.environment == "<ENVIRONMENT_NAME>"
