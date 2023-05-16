import pytest
# from pathlib import Path
from scripts.classes.configuration import Configuration

class TestConfiguration:

    configuration = Configuration("<branch_name>")

    def test_required_settings_entered(self):
        self.configuration.validate_configuration()

