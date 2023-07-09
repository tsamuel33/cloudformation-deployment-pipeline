import json
import os
import sys
import yaml
from jsonpath_ng.ext import parse

# Instrisic function classes
class Ref(object):
    def __init__(self, data):
        self.data = data

class Sub(object):
    def __init__(self, data):
        self.data = data

class Split(object):
    def __init__(self, data):
        self.data = data

class Select(object):
    def __init__(self, data):
        self.data = data

class Join(object):
    def __init__(self, data):
        self.data = data

class ImportValue(object):
    def __init__(self, data):
        self.data = data

class GetAZs(object):
    def __init__(self, data):
        self.data = data

class GetAtt(object):
    def __init__(self, data):
        self.data = data

class FindInMap(object):
    def __init__(self, data):
        self.data = data

class Cidr(object):
    def __init__(self, data):
        self.data = data

class Base64(object):
    def __init__(self, data):
        self.data = data
    
class And(object):
    def __init__(self, data):
        self.data = data

class Equals(object):
    def __init__(self, data):
        self.data = data

class If(object):
    def __init__(self, data):
        self.data = data

class Not(object):
    def __init__(self, data):
        self.data = data

class Or(object):
    def __init__(self, data):
        self.data = data

class Condition(object):
    def __init__(self, data):
        self.data = data

# Intrisnsic function constructor
def yaml_constructor(loader, node):
    if isinstance(node, (yaml.nodes.SequenceNode)):
        value = loader.construct_sequence(node)
    elif isinstance(node, (yaml.nodes.MappingNode)):
        value = loader.construct_mapping(node)
    elif isinstance(node, (yaml.nodes.ScalarNode)):
        value = loader.construct_scalar(node)
    class_name = node.tag.lstrip("!")
    class_obj = getattr(sys.modules[__name__], class_name)
    if class_name == "GetAtt":
        return { "Fn::GetAtt" : class_obj(value).data.split(".") }
    elif class_name in ["Ref", "Condition"]:
        return { class_name : class_obj(value).data }
    else:
        return { "::".join(("Fn", class_name)) : class_obj(value).data }

def add_yaml_constructor(tag):
    yaml.add_constructor(tag, yaml_constructor, yaml.SafeLoader)

# Add constructors to YAML loader
tags = [
    u'!Ref',
    u'!Sub',
    u'!Split',
    u'!Select',
    u'!Join',
    u'!ImportValue',
    u'!GetAZs',
    u'!GetAtt',
    u'!FindInMap',
    u'!Cidr',
    u'!Base64',
    u'!And',
    u'!Equals',
    u'!If',
    u'!Not',
    u'!Or',
    u'!Condition'
]
for tag in tags:
    add_yaml_constructor(tag)

def create_test_file(filename, data):
    with open(filename, "w") as file:
        file.write(data)
        file.close()
    # #Create file for testing
    # parent = data_path.parent
    # test_file_name = "".join((data_path.stem, "_guard", ".json"))
    # test_file_path = parent / test_file_name
    # create_test_file(test_file_path, json_object)

def delete_test_file(file):
    os.remove(file)

def convert_to_json(data_path):
    with open(data_path, 'r') as template_file:
        template_data = template_file.read()
    if data_path.suffix in [".template", ".yaml", ".yml"]:
        data_object = yaml.safe_load(template_data)
    elif data_path.suffix == ".json":
        data_object = json.loads(template_data)
    template_file.close()
    json_object = json.dumps(data_object, indent=2, default=str)
    return json_object

def parse_parameters(parameter_list):
    if parameter_list is None:
        parameters = None
    else:
        parameters = dict((param['ParameterKey'], param['ParameterValue']) for param in parameter_list)
    return parameters

def get_param_value(parameters, param_key):
    if parameters is not None:
        try:
            output = parameters[param_key]
        except KeyError:
            output = None
    elif parameters is None:
        output = None
    return output

# JSONPath is unable to find a path that has "::"" in it (i.e, Fn::Sub).
# Add quotations to the field name for the search to work.
def clean_location(location):
    output = '$'
    parts = location.split(".")
    for part in parts:
        if "::" in part:
            output = output + "." + '"{}"'.format(part)
        else:
            output = output + "." + part
    return output

def find_and_replace_refs(parser, data, parameters):
    locations = [str(match.full_path) for match in parser.find(data) if (isinstance(match.value, dict)) and "Ref" in match.value]
    for location in locations:
        new_location = clean_location(location)
        location_path = parse(new_location)
        value = location_path.find(data)[0].value
        param_name = value['Ref']
        param_value = get_param_value(parameters, param_name)
        if param_value is not None:
            location_path.update(data, param_value)

def find_and_replace_subs(parser, data, parameters):
    locations = [str(match.full_path) for match in parser.find(data) if (isinstance(match.value, dict)) and "Fn::Sub" in match.value]

def main(stack):
    resources_parser = parse("$.Resources..*")
    parameters = parse_parameters(stack.parameters)
    data = convert_to_json(stack.template_path)
    json_data = json.loads(data)
    find_and_replace_refs(resources_parser, json_data, parameters)