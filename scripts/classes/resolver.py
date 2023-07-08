import json
import os
import subprocess
import sys
import yaml
from pathlib import Path
# from jsonpath_ng import jsonpath, parse
from jsonpath_ng.ext import parse
import re

root_dir = Path(__file__).parents[2]
template_path = root_dir / "deployments" / "us-east-1" / "all_envs" / "templates" / "example.template"
# template_path = root_dir / "deployments" / "us-east-1" / "all_envs" / "templates" / "example_guard.json"
cfn_guard_dir = root_dir / "rules" / "cfn-guard"
guard_commands = [
        "cfn-guard",
        "validate",
        "-r",
        cfn_guard_dir.as_posix()
    ]

parameters_from_stack = [
    {
        'ParameterKey': 'RandomParameter',
        'ParameterValue': 'non-default'
    },
    {
        'ParameterKey': 'IngressProtocol',
        'ParameterValue': '6'
    },
    {
        'ParameterKey': 'Prefix',
        'ParameterValue': 'TravisParam'
    }
]

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
    if class_name == "Ref":
        return { "Ref": class_obj(value).data }
    elif class_name == "GetAtt":
        return { "Fn::GetAtt" : class_obj(value).data.split(".") }
    elif class_name == "Condition":
        return { "Condition" : class_obj(value).data }
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

    #Create file for testing
    parent = data_path.parent
    test_file_name = "".join((data_path.stem, "_guard", ".json"))
    test_file_path = parent / test_file_name
    create_test_file(test_file_path, json_object)
    return json_object

def cfn_guard_validate(template_path):
    guard_commands.append("-d")
    guard_commands.append(template_path.as_posix())
    code = subprocess.run(guard_commands).returncode
    return code

def get_param_value(parameters, param_key):
    result = None
    if parameters is not None:
        for entry in parameters:
            if entry['ParameterKey'] == param_key:
                result = entry['ParameterValue']
                break
    if result is None:
        # Placeholder value so the regex sub command doesn't get
        # confused later.
        output = ":".join(('Resource_Ref', param_key))
    else:
        output = result
    return output

def replace_string(regex, replacements : list, source_string):
    output = source_string
    for replacement in replacements:
        output = re.sub(regex, replacement, output, count=1)
    return output

def find_and_replace_refs(parser, data, parameters=None):
    ref_regex = '([\'"]?{\s*[\\\\]?[\'"]?Ref[\\\\]?[\'"]?\s*:\s*[\\\\]?[\'"]?)([a-zA-Z]*)([\\\\]?[\'"]?\s*}[\'"]?)'
    ref_locations = [str(match.full_path) for match in parser.find(data) if (isinstance(match.value, str) and re.search(ref_regex, match.value) is not None)]
    for location in ref_locations:
        exact = parse(location)
        value = exact.find(data)[0].value #gives the string value of the jsonpath location identified
        to_replace = re.findall(ref_regex, value) #gives list of refs in the above string
        to_replace_param_names = [param[1] for param in to_replace] # names of parameters that need values
        to_replace_param_values = [get_param_value(parameters_from_stack, param) for param in to_replace_param_names] # values corresponding to above
        output = replace_string(ref_regex, to_replace_param_values, value)
        exact.update(data, output)

def main():
    data = convert_to_json(template_path) #string
    json_data = json.loads(data)
    # test_parse = parse('$.Resources.DefaultSecurityGroup.Properties.VpcId')
    # x = test_parse.find(json_data)
    # print(x[0].value)
    resources_parser = parse("$.Resources..*")
    # exact = parse('Resources.DefaultSecurityGroup.Properties.VpcId')
    # print(exact.find(json_data)[0].value)
    find_and_replace_refs(resources_parser, json_data)
    # print(json_data)


    # # output = [match.value for match in test_parse.find(json_data)]
    # ref_regex = '([\'"]?{\s*[\\\\]?[\'"]?Ref[\\\\]?[\'"]?\s*:\s*[\\\\]?[\'"]?)([a-zA-Z0-9]*)([\\\\]?[\'"]?\s*}[\'"]?)'
    # refs = [parse(location).find(json_data)[0].value for location in ref_locations]
    # param_names = [re.search(ref_regex, ref).group(2) for ref in refs]
    # param_values = [get_param_default(parameters_from_stack, param_name) for param_name in param_names]
    # print(param_names)
    # print(param_values)


    # x = parse('Resources..Type')
    # aws_types = [match.value for match in x.find(json.loads(data))]
    # print(aws_types)
    # jsonpath.Where
    # replace_refs(json_string, params)
    
    # # # output = re.findall(ref_regex, json_string) #will need to use this since search only returns the first match in a string
    # test_regex = '([\'"]?{\s*[\\\\]?[\'"]?Ref[\\\\]?[\'"]?\s*:\s*[\\\\]?[\'"]?)([a-zA-Z]*)([\\\\]?[\'"]?\s*}[\'"]?)'
    # output = re.search(test_regex, json_string)
    # outputs = re.findall(test_regex, json_string)
    # print(type(outputs))
    # print(output.group(2))
    # param_name = output.group(0)
    # resources = json_data['Resources']
    # # x = get_param_default(params, 'Prefix')
    # ref = resources['DefaultSecurityGroup']['Properties']['VpcId']
    # refs = parse("$.Resources..*")
    # values = [(str(match.full_path), match.value) for match in refs.find(json_data) if '"Ref" :' in str(match.value)]
    # print(values)
    # for value in values:
    #     default = get_param_default(params, )
    # ref_list = [k for k,v in resources.items()] #if "Ref" in v
    # print(ref_list)
    # if ref == '{ "Ref" : RandomParameter }':
    #     print('Correct')
    # # else:
    # #     print('Incorrect')
    # # print(type(json_data))
    # # print(params)

if __name__ == "__main__":
    #TODO - set up module to accept a stack class instance
    main()
    # target_key1 = "RandomParameter"
    # target_key2 = "IngressProtocol"
    # example = parse('$[*]')
    # output = [match.value['ParameterValue'] for match in example.find(parameters_from_stack) if match.value['ParameterKey'] == target_key2][0]
    # print(output)

    # newlist = [expression for item in iterable if condition == True]