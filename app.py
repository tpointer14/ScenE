from flask import Flask, render_template, jsonify, Response, request
import yaml
import os
from yaml.loader import SafeLoader
from functions import loadProcess, loadEmptyTemplate
import requests
import uuid
import redis
import json
import logging

app = Flask(__name__)
# don't sort the returned json: BE AWARE --> by default, JSONs are defined as
# "unsorted set of key/value pairs", so your browser or a random library could
# easily fuck up the order again --> check using arrays
app.config['JSON_SORT_KEYS'] = False
redis_db = redis.Redis(host='127.0.0.1',port=6379, db=0)
#logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)

if __name__ == '__main__':
    app.run(port=5000, debug=True)

#kommende TODOs: INSTANZEN HINPUSHEN, DATAELEMENTS FOR EXCLUSIVE AND LOOP CONDITIONS, SUBPROCESSES

############################################################################
# ENDPOINT: /ui
# GET - return index.html
############################################################################
@app.route('/')
def getIndexPage():
    #logging.info('INDEXPAGE requested')
    instance_id = request.args.get('instance')
    if instance_id is not None:
        process = loadProcess(instance_id)
        return render_template('index.html', process=process)
    return render_template('index.html')


############################################################################
# ENDPOINT: /instances/<instance_id>/<sub_directory>
# GET - return everything what is requested
############################################################################
@app.route('/instances/')
@app.route('/instances/<instance_id>/')
@app.route('/instances/<instance_id>/<sub1>/')
def navigating(instance_id = None, sub1 = None):
    if instance_id is None:
        instances = os.listdir('instances')
        instances.sort(reverse=True)
        return instances
    else:
        if not os.path.exists('instances/' + str(instance_id)):
            return 'Instanz "' + instance_id + '" existiert nicht.', 500
        process = loadProcess(instance_id)
        if sub1 is not None:
            try:
                return process['process'][sub1]
            except KeyError as e:
                return 'Eigenschaft "' + sub1 + '" existiert nicht.', 500
        else:
            return list(process['process'].keys())


############################################################################
# ENDPOINT: /instances
# POST - create new instance (id will be created automatically)
############################################################################

@app.route('/instances/', methods = ['POST'])
def createInstance():
    #directly start it?!
    #check if call is good (yaml file in correct format must be appended)
    process = loadEmptyTemplate()
    
    # search for free instance_id
    i = 1
    while(True):
        #create new directory for instance
        path = 'instances/' + str(i)
        if not os.path.exists(path):
            os.makedirs(path)
            with open(path + '/process.yaml', 'w') as outfile:
                yaml.dump(process, outfile)
            
            #set state and dataelements and break the loop
            redis_db.set(str(i)+'_state', 'ready')
            #for key,value in process['dataelements']:
            #    redis_db.set(str(i)+'_'+key, value)
            return str(i)
        else:
            i += 1

############################################################################
# ENDPOINT: /instances/<id>/start
# POST - start the instance
# PUT - ?
# DELETE - delete the instance
############################################################################
@app.route('/instances/<instance_id>/start', methods = ['POST'])
def startFlow(instance_id):
    #here, some information is necessary - > callback when it's finished or failed?
    if not os.path.exists('instances/' + str(instance_id)):
        return 'Die Instanz gibts net'
    #start from predefined position?! How's that possible?!
    process = loadProcess(instance_id)
    if process['process']['flow'] == None:
        return 'flow empty', 500
    instance_state = redis_db.get(instance_id+'_state')
    if instance_state is not None:
        return 'die Instanz wurde schon gestartet'
    redis_db.set(instance_id+'_state', 'running')
    doFlow(instance_id, process['process']['flow'], is_mainflow=True)
    return 'Instance started'

@app.route('/callback/<callback_uuid>', methods = ['POST'])
def handleCallback(callback_uuid):
    #check if callback_uuid exists and if so, load it
    redis_entry = redis_db.get(callback_uuid)
    if redis_entry is None:
        return 'Kein Callback verfügbar mit UUID ' + callback_uuid, 500
    callback = json.loads(redis_entry)

    #load instance and start it
    process = loadProcess(callback['instance'])
    doFlow(callback['instance'], process['process']['flow'], starting_at = callback['event'], is_mainflow=True)

    #delete callback_uuid from redis and return
    redis_db.delete(callback_uuid)
    return 'Callback ok', 200

def doFlow(instance_id, flow, starting_at = None, is_mainflow = False):
    
    #define, if we should skip calls (e.g. for example to jump to a callback)
    skip = False if starting_at is None else True
    
    #loop through each event 
    for call in flow:
        if not call['key'].startswith('a') and not call['key'].startswith('t'): #then it's a pattern like exclusive, loop, parallel, etc.
            if call['key'].startswith('exclusive'):
                if skip == True:
                    # das ist bissl kompliziert:
                    # ich ruf für jeden Pfad in dem exklusiven Gateway doFlow() auf - also nehm quasi
                    # jeden Pfad einzeln und beginn wieder von oben. Wenn da in einem keine passende
                    # Startaktivität gefunden wird, werden einfach alle Calls übersprungen und skip = True
                    # zurückgegeben. Falls in einem Pfad die Startaktivität gefunden wird, wird dort skip 
                    # gleich auf false gesetzt und die restlichen Calls werden durchgeführt. dann wird 
                    # True returniert & ich mach im mainflow normal weiter.
                    for key, path in call['paths'].items():
                        y, returned_skip = doFlow(instance_id, path['flow'], starting_at = starting_at)
                        if returned_skip == False:
                            skip = returned_skip
                            break
                else:
                    flow = handleExclusive(instance_id, call) # returns correct flow
                    x = doFlow(instance_id, flow) #check for callback and return in case - recursion
                    if x[0] == 'wait for callback':
                        return 'wait for callback', skip
                continue
            elif call['key'].startswith('loop'):
                if skip == True:
                    # falls skip True ist, gehe ohne eine Pre-Condition zu prüfen in den Flow rein und
                    # suche nach der Aktivität - ist die da drinnen, dann führe die restlichen aus und 
                    # returniere False (weil wir ja dann nimmer skippen müssen, haben sie ja schon
                    # gefunden) - DANN: musst du aber trotzdem wieder in die PRECONDITION rein und prüfen
                    # ob wir den Loop nochmal machen. - deswegen ist hier (im Vergleich zum exklusiven
                    # Gateway) KEIN else.
                    y, returned_skip = doFlow(instance_id, call['flow'], starting_at = starting_at)
                    if returned_skip == False:
                        skip = returned_skip
                while call['pre-condition'] == True: #write handling method here
                    x = doFlow(instance_id, call['flow']) 
                    if x[0] == 'wait for callback':
                        return 'wait for callback', skip 
                continue

        #this point is just reached by calls --> call['key'].startswith('a') or 't' == True
        #skip them 
        if skip == True and call['key'] != starting_at:
            print('SKIP: ' + call['key'])
            continue
        if call['key'] == starting_at:
            skip = False
            continue

        method = 'post' if call['key'].startswith('t') else call['method']
        endpoint = 'http://127.0.0.1:5000/timeservice' if call['key'].startswith('t') else call['endpoint']
        print('CALL: ' + call['key'])
        x = makeCall(instance_id, call['key'], method, endpoint)
        if x == 'wait for callback':
            return 'wait for callback', skip
    if is_mainflow:
        redis_db.set(instance_id + '_state', 'finished')
    return 'done', skip

def handleExclusive(instance_id, call):
    for key, path in call['paths'].items():
        # if a path matches the entry value - return it
        # eval() or something like that is necessary here later
        if path['entry_condition'] == True:
            return path['flow']
    return {} #that return statement should never be reached (TODO: write exception in case it's reached)

# How to later handle conditions here: JEDER PFAD HAT EINE CONDITION,
# und einer ist als "default" definiert.
def calculateConditionValue(condition_str):
    #later, a condition string (e.g. a == b) must be parsed here
    #at the moment, just fixed values are possible
    return condition_str

def makeCall(instance_id, call_key, method, url, args=""):
    # create uuid for possible callback
    callback_uuid = str(uuid.uuid1())

    # make call, and include a possible callback URL
    response = requests.request(
        method=method,
        url=url,
        headers = { 'Callback-url':'http://192.168.33.10:5000/'+'callback/'+callback_uuid }
    )
    # val = 'Geeks'
    # print(f"{val}for{val} is a portal for {val}.")

    # if a callback is requested in the headers, save callback-uuid with instance
    # and event to redis --> then return an information, that we should stop the
    # current flow and wait for a callback
    if 'Callback' in response.headers and response.headers['Callback'] == 'True': 
        redis_db.set(callback_uuid, json.dumps({'instance':instance_id, 'event':call_key}))
        return 'wait for callback'
    
    return 'go on'


# JUST FOR TESTING THE PROCESS FLOWS
@app.route('/test', methods = ['POST'])
def test():
    response = Response()
    #response.headers['Callback'] = "True"
    #print(request.headers['Callback-Url'])
    return response

# JUST FOR TESTING THE PROCESS FLOWS
@app.route('/timeservice', methods = ['POST'])
def timeservice():
    response = Response()
    response.headers['Callback'] = "True"
    print('timeservice')
    print(request.headers['Callback-Url'])
    return response