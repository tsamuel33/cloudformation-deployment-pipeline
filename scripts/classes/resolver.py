import json
import os
import sys
import yaml
from jsonpath_ng.ext import parse
import base64

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
    json_data = json.loads(json_object)
    return json_data

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

def process_template(location, data, parameters):
    parsed_location = parse_location(location)
    loc = parsed_location[0]
    action = parsed_location[1]
    safe_loc = clean_location(loc)
    safe_path = parse(safe_loc)
    current = parse(clean_location(location)).find(data)[0].value
    if action == "Ref":
        replace_ref(safe_path, data, parameters, current)
    elif action == "Fn::Split":
        replace_split(safe_path, data, current)
    elif action == "Fn::Select":
        replace_select(safe_path, data, current)
    elif action == "Fn::Join":
        replace_join(safe_path, data, current)
    elif action == "Fn::FindInMap":
        replace_findinmap(safe_path, data, current)
    elif action == "Fn::Base64":
        replace_base64(safe_path, data, current)
    elif action == "Fn::Equals":
        replace_equals(safe_path, data, current)
    elif action == "Fn::Not":
        replace_not(safe_path, data, current)
    elif action == "Fn::And":
        replace_and(safe_path, data, current)
    elif action == "Fn::Or":
        replace_or(safe_path, data, current)
    elif action == "Condition":
        replace_condition(safe_path, data, current)
    elif action == "Fn::If":
        replace_if(safe_path, data, current)

#TODO - Set reference evaluation for AWS pseudo-parameters
def replace_ref(json_path, data, parameters, param_key):
    value = get_param_value(parameters, param_key)
    if value is not None:
        json_path.update(data, value)

def replace_split(json_path, data, input):
    proceed = False
    if isinstance(input[0], str) and isinstance(input[1], str):
        proceed = True
    if proceed:
        delimiter = input[0]
        input_string = input[1]
        value = input_string.split(str(delimiter))
        json_path.update(data, value)

def replace_select(json_path, data, input):
    proceed = False
    if isinstance(input[0], int) and isinstance(input[1], list):
        proceed = True
    if proceed:
        index = input[0]
        input_list = input[1]
        value = input_list[index]
        json_path.update(data, value)

def replace_join(json_path, data, input):
    proceed = False
    if isinstance(input[0], str) and isinstance(input[1], list):
        proceed = True
    if proceed:
        delimiter = input[0]
        input_list = input[1]
        value = delimiter.join(input_list)
        json_path.update(data, value)

def replace_findinmap(json_path, data, input):
    proceed = False
    if isinstance(input, list) and len(input) == 3:
        proceed = True
    if proceed:
        parser_string = "$.Mappings"
        for level in input:
            parser_string = ".".join((parser_string, level))
        value = parse(parser_string).find(data)[0].value
        json_path.update(data, value)

def get_condition_value(data, input):
    parser_string = ".".join(("$.Conditions", input))
    value = parse(parser_string).find(data)[0].value
    return value

#TODO - Condition logic isn't straightforward. Might have to loop a few times
def replace_condition(json_path, data, input):
    if isinstance(input, str):
        value = get_condition_value(data, input)
        if type(value) is bool:
            json_path.update(data, value)

def replace_sub(json_path, data, input):
    pass

def replace_importvalue(json_path, data, input):
    pass

def replace_getazs(json_path, data, input):
    pass

def replace_getatt(json_path, data, input):
    pass

def replace_cidr(json_path, data, input):
    pass

def replace_base64(json_path, data, input):
    proceed = False
    if isinstance(input, str):
        proceed = True
    if proceed:
        utf8_string = input.encode("utf-8")
        value = base64.b64encode(utf8_string).decode("utf-8")
        json_path.update(data, value)

def replace_and(json_path, data, input):
    proceed = False
    if isinstance(input, list) and len(input) >= 2 and len(input) <= 10:
        all_bool = True
        for item in input:
            if type(item) is not bool:
                all_bool = False
                break
        proceed = all_bool
    if proceed:
        value = True
        for item in input:
            if item is False:
                value = False
                break
        json_path.update(data, value)

def replace_equals(json_path, data, input):
    proceed = False
    if isinstance(input, list) and len(input) == 2:
        if type(input[0]) == type(input[1]):
            proceed = True
    if proceed:
        if input[0] == input[1]:
            value = True
        else:
            value = False
        json_path.update(data, value)

#TODO - set up way to remove property if AWS::NoValue is provided
# https://stackoverflow.com/questions/16279212/how-to-use-dot-notation-for-dict-in-python
def replace_if(json_path, data, input):
    proceed = False
    if isinstance(input, list):
        proceed = True
    if proceed:
        condition = None
        if isinstance(input[0], bool):
            condition = input[0]
        elif isinstance(input[0], str):
            condition = get_condition_value(data, input[0])
        if condition is True:
            value = input[1]
        elif condition is False:
            value = input[2]
        if isinstance(condition, bool):
            json_path.update(data, value)

def replace_not(json_path, data, input):
    proceed = False
    if isinstance(input, list) and len(input) == 1:
        if isinstance(input[0], bool):
            proceed = True
    if proceed:
        value = not input[0]
        json_path.update(data, value)

def replace_or(json_path, data, input):
    proceed = False
    if isinstance(input, list) and len(input) >= 2 and len(input) <= 10:
        all_bool = True
        for item in input:
            if type(item) is not bool:
                all_bool = False
                break
        proceed = all_bool
    if proceed:
        value = False
        for item in input:
            if item is True:
                value = True
                break
        json_path.update(data, value)

def parse_location(json_full_path):
    parts = json_full_path.split(".")
    func = parts[-1]
    parts.remove(func)
    parent = ".".join(parts)
    return(parent, func)

def locate_all_to_replace(parser, data):
    intrinsic_funcs = [
    'Ref',
    'Condition',
    'Fn::Sub',
    'Fn::Split',
    'Fn::Select',
    'Fn::Join',
    'Fn::ImportValue',
    'Fn::GetAZs',
    'Fn::GetAtt',
    'Fn::FindInMap',
    'Fn::Cidr',
    'Fn::Base64',
    'Fn::And',
    'Fn::Equals',
    'Fn::If',
    'Fn::Not',
    'Fn::Or'
    ]
    locations = []
    for func in intrinsic_funcs:
        loc = [str(match.full_path) for match in parser.find(data) if (isinstance(match.value, (dict, list, str)) and str(match.path) == func)]
        locations.extend(loc)
    locations.sort(key=lambda x: len(x), reverse=True)
    return locations


def main(stack):
    resources_parser = parse("$.Resources..*")
    parameters = parse_parameters(stack.parameters)
    json_data = convert_to_json(stack.template_path)
    all_parser = parse("$.*..*")
    locations = locate_all_to_replace(all_parser, json_data)
    for location in locations:
        process_template(location, json_data, parameters)
    print(json_data)