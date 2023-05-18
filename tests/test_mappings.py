import pytest
from scripts.classes.mappings import Mappings

class TestMappings:

    __region = "us-east-1"
    __environment = "dev"

    @pytest.fixture
    def sample_all_envs_parameters_mapping(self):
        mapping = Mappings("parameters", self.__region, self.__environment, True)
        return mapping
    
    @pytest.fixture
    def sample_all_envs_templates_mapping(self):
        mapping = Mappings("templates", self.__region, self.__environment, True)
        return mapping
    
    @pytest.fixture
    def sample_dev_parameters_mapping(self):
        mapping = Mappings("parameters", self.__region, self.__environment)
        return mapping
    
    @pytest.fixture
    def sample_dev_templates_mapping(self):
        mapping = Mappings("templates", self.__region, self.__environment)
        return mapping

    def test_all_envs_parameter_mapping_value(self, sample_all_envs_parameters_mapping):
        value = sample_all_envs_parameters_mapping.get_mapping_value("template_file_name")
        assert value == "parameter_file_name"

    def test_all_envs_template_mapping_value(self, sample_all_envs_templates_mapping):
        value = sample_all_envs_templates_mapping.get_mapping_value("template_file_name")
        assert value == "existing_stack_name1"

    def test_dev_parameter_mapping(self, sample_dev_parameters_mapping):
        assert sample_dev_parameters_mapping.mapping is None

    def test_dev_template_mapping(self, sample_dev_templates_mapping):
        assert sample_dev_templates_mapping.mapping is None