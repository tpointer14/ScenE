import yaml
from yaml.loader import SafeLoader

def loadProcess(id):
    with open("instances/" + str(id) + "/process.yaml", "r") as stream:
        try:
            process = list(yaml.load_all(stream, Loader=SafeLoader))[0] 
        except yaml.YAMLError as exc:
            print(exc)
    return process

def loadEmptyTemplate():
    with open("empty_template.yaml", "r") as stream:
        try:
            process = list(yaml.load_all(stream, Loader=SafeLoader))[0] 
        except yaml.YAMLError as exc:
            raise Exception("Sorry, something went wrong when loading the template") 
    return process
