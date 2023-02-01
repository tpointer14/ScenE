from flask import Flask, render_template, jsonify, Response, request
from flask_sse import sse
import yaml
import os
from yaml.loader import SafeLoader
from functions import loadProcess, loadEmptyTemplate
import requests
import uuid
import redis
import json
import logging
from threading import Thread
import time
from flow import doFlow

app = Flask(__name__)
redis_db = redis.Redis(host='127.0.0.1',port=6379, db=0)
app.config["REDIS_URL"] = "redis://localhost"
app.register_blueprint(sse, url_prefix='/stream')

# GENERAL TODO:
# 1. update file structure: e.g. how to outsource flow logic (e.g. doFlow, handleExclusive, etc.) to another file but keeping sse
# see https://stackoverflow.com/questions/13284858/how-to-share-the-global-app-object-in-flask
# 2. subprocesses (should be a seperate event type, that allows for calling subprocess)
# 3. consider dataelements in the process (especially for loop and exclusive conditions)
# 4. consider endpoints in the process (use endpoints instead of fixed urls)
# 5. use f strings instead of '' + '' (i.e. # val = 'Geeks' print(f"{val}for{val} is a portal for {val}.")
# 6. check why this shit is only working when the file is called "sse.py" (see venjix)

############################################################################
# ENDPOINT: /
# GET - return index.html (navigator)
############################################################################
@app.route('/')
def getIndexPage():
    return render_template('index.html')

############################################################################
# ENDPOINT: /engine/<instance_id>/<sub_directory>
# GET - return everything what is requested - CORE API
# TODO: rewrite that function, that it's possible to navigate through the full process, no matter how deep it is
# or: just delete that shit - do we really need it?!
############################################################################
@app.route('/engine/')
@app.route('/engine/<instance_id>/')
@app.route('/engine/<instance_id>/<sub1>/')
def engine(instance_id = None, sub1 = None):
    if instance_id is None:
        instances = os.listdir('instances')
        instances.sort(reverse=True) #reverse instances, because the latest should be on top.
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
# ENDPOINT: /runner
# GET - return all instances
# POST - prepare new instance (id will be created automatically)
# TODO: additionally return state and whatever is important on that page
############################################################################
@app.route('/runner/')
def getAllInstances():
    instances = os.listdir('instances')
    instances.sort(reverse=True) #reverse instances, because the latest should be on top.
    return render_template('instances.html', instances=instances)

# TODO: process.yaml can be pushed and is directly used instead of empty template
@app.route('/runner/', methods = ['POST'])
def prepareInstance():
    
    # TODO: check if call is good (yaml file in correct format must be appended)
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
# ENDPOINT: /runner/<id>
# GET - return all instances
# POST - prepare new instance (id will be created automatically)
############################################################################
@app.route('/runner/<instance_id>')
def getSingleInstance(instance_id):
    if instance_id is not None:
        process = loadProcess(instance_id)
        return render_template('instance_runner.html', process=process, instance_id=instance_id)
    return render_template('instance_runner.html')

############################################################################
# ENDPOINT: /runner/<id>/current_call
# GET - return current_call from redis
# why we need this: on pageload of a running instance, we should know the current call, in order to highlight it.
# TODO: implement this properly.
############################################################################
@app.route('/runner/<instance_id>/current-call')
def getCurrentCall(instance_id):
    #logging.info('INDEXPAGE requested')
    current_call = redis_db.get(instance_id + '_call')
    if current_call is not None:
        return current_call.decode('utf-8')
    return ''

############################################################################
# ENDPOINT: /runner/<id>/start
# POST - start the instance
# PUT - ?
# DELETE - delete the instance
# TODO: create parameter that triggers a callback on finishing (e.g. for subprocesses)
# TODO: "doFlow" should be started in a new thread
############################################################################
@app.route('/runner/<instance_id>/start/', methods = ['POST'])
def startFlow(instance_id):
    if not os.path.exists('instances/' + str(instance_id)):
        return 'Die Instanz gibts net'
    #start from predefined position?! How's that possible?!
    process = loadProcess(instance_id)
    if process['process']['flow'] == None:
        return 'flow empty', 500
    instance_state = redis_db.get(instance_id+'_state')
    #if instance_state is not None: // später wieder ankommentieren
    #return 'die Instanz wurde schon gestartet'
    redis_db.set(instance_id+'_state', 'running')
    redis_db.set(instance_id+'_livetime', 0.0)
    redis_db.set(instance_id+'_interval', 1.0)
    thread = Thread(target=run, args=(instance_id,))
    thread.start()
    doFlow(instance_id, process['process']['flow'], is_mainflow=True)
    return 'Instance started'

############################################################################
# ENDPOINT: /runner/callback/<callback_uuid>
# POST - do a callback
# TODO: create parameter that triggers a callback on finishing (e.g. for subprocesses)
# TODO: "doFlow" should be started in a new thread
############################################################################
@app.route('/runner/callback/<callback_uuid>', methods = ['POST'])
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


# TODO:
# 1. export that function to flow.py
# 2. rework on skip logic (that can definitley be more beautiful)
# 3. rework on return logic (think about how to handle returns - maybe enums?!)
# 4. refactor that "starting_at" --> do we actually need the skip variable? we could just check if starting_at is None
# 5. refactor that "x" which is used to save return statements
def doFlow(instance_id, flow, starting_at = None, is_mainflow = False):

    #define, if we should skip calls (e.g. for example to jump to a callback)
    skip = False if starting_at is None else True
    
    #loop through each event 
    for event in flow:
        #this is just pattern logic and skip-logic for callbacks
        if event['type'] == 'exclusive':
            if skip == True:
                # das ist bissl kompliziert:
                # ich ruf für jeden Pfad in dem exklusiven Gateway doFlow() auf - also nehm quasi
                # jeden Pfad einzeln und beginn wieder von oben. Wenn da in einem keine passende
                # Startaktivität gefunden wird, werden einfach alle Calls übersprungen und skip = True
                # zurückgegeben. Falls in einem Pfad die Startaktivität gefunden wird, wird dort skip 
                # gleich auf false gesetzt und die restlichen Calls werden durchgeführt. dann wird 
                # True returniert & ich mach im mainflow normal weiter.
                for key, path in event['paths'].items():
                    y, returned_skip = doFlow(instance_id, path['flow'], starting_at = starting_at)
                    if returned_skip == False:
                        skip = returned_skip
                        break
            else:
                flow = handleExclusive(instance_id, event) # returns correct flow
                x = doFlow(instance_id, flow) #check for callback and return in case - recursion
                if x[0] == 'wait for callback':
                    return 'wait for callback', skip
            continue
        elif event['type'] == 'loop':
            if skip == True:
                # falls skip True ist, gehe ohne eine Pre-Condition zu prüfen in den Flow rein und
                # suche nach der Aktivität - ist die da drinnen, dann führe die restlichen aus und 
                # returniere False (weil wir ja dann nimmer skippen müssen, haben sie ja schon
                # gefunden) - DANN: musst du aber trotzdem wieder in die PRECONDITION rein und prüfen
                # ob wir den Loop nochmal machen. - deswegen ist hier (im Vergleich zum exklusiven
                # Gateway) KEIN else.
                y, returned_skip = doFlow(instance_id, event['flow'], starting_at = starting_at)
                if returned_skip == False:
                    skip = returned_skip
            while event['pre-condition'] == True: #write handling method here
                x = doFlow(instance_id, event['flow']) 
                if x[0] == 'wait for callback':
                    return 'wait for callback', skip 
            continue

        #this point is just reached by types call and time
        #skipping logic for that calls:
        if skip == True and event['key'] != starting_at:
            print('SKIP: ' + event['key'])
            continue
        if event['key'] == starting_at:
            skip = False
            continue

        #handle time events:
        if event['type'] == 'time':
            print('TIME: ' + event['key'])
            wait_until(instance_id, event['time'])
            sse.publish({"instance_id": instance_id, "event": event['key']}, type='highlight_current_event')
            continue

        print('CALL: ' + event['key'])
        sse.publish({"instance_id": instance_id, "event": event['key']}, type='highlight_current_event')
        redis_db.set(instance_id + '_call', event['key'])
        x = makeCall(instance_id, event['key'], event['method'], event['endpoint'], event['arguments'])
        if x == 'wait for callback':
            return 'wait for callback', skip
    if is_mainflow:
        redis_db.set(instance_id + '_state', 'ready') # eigentlich finished, aber fürs testen auf ready
        redis_db.set(instance_id + '_call', 'pm_end')
        sse.publish({"instance_id": instance_id, "event": 'pm_end'}, type='highlight_current_event')
    return 'done', skip

# TODO:
# 1. export that function to flow.py
# 2. think about other solution for waiting (i.e. callbacks.)
def wait_until(instance_id, timex):
    while True:
        # if a callback exists, and it's time to fire it --> do it
        livetime = float(redis_db.get(instance_id + '_livetime'))
        if livetime >= timex:
            return True
        time.sleep(0.5)


# TODO:
# 1. export that function to time.py
def run(instance_id):
    with app.app_context():
        previous_time = time.time()
        while redis_db.get(instance_id + '_state').decode('utf-8') == 'running':
            print('time running')
            # increment gametime
            previous_time = incrementTime(instance_id, previous_time)

            # no stress, wait a bit until rerunning the loop
            time.sleep(0.5)

        print('Thread gekillt')
        return 'return?'

# TODO:
# 1. export that function to time.py
def incrementTime(instance_id, previous_time):
    current_time = time.time()
    if redis_db.get(instance_id + '_pause') is None:
        livetime = float(redis_db.get(instance_id + '_livetime'))
        livetime += ((current_time - previous_time) % 60.0)*float(redis_db.get(instance_id + '_interval'))
        redis_db.set(instance_id + '_livetime', livetime)
        sse.publish({"instance_id": instance_id, "livetime": int(livetime)}, type='livetime')
    return current_time #of course the time actually isn't current anymore, but it will after returning be used as "previous_time"

# TODO:
# 1. export that function to flow.py
def handleExclusive(instance_id, event):
    for key, path in event['paths'].items():
        # if a path matches the entry value - return it
        # eval() or something like that is necessary here later
        if path['entry_condition'] == True:
            return path['flow']
    return {} #that return statement should never be reached (TODO: write exception in case it's reached)

# TODO:
# 1. export that function to flow.py
# How to later handle conditions here: JEDER PFAD HAT EINE CONDITION,
# und einer ist als "default" definiert.
def calculateConditionValue(condition_str):
    #later, a condition string (e.g. a == b) must be parsed here
    #at the moment, just fixed values are possible
    return condition_str

# TODO:
# 1. export that function to flow.py
def makeCall(instance_id, event_key, method, url, args=""):
    # create uuid for possible callback
    callback_uuid = str(uuid.uuid1())

    # make call, and include a possible callback URL
    response = requests.request(
        method=method,
        url=url,
        headers = { 'Callback-url':'http://192.168.33.10:5000/runner/'+'callback/'+callback_uuid },
        params = args
    )

    # if a callback is requested in the headers, save callback-uuid with instance
    # and event to redis --> then return an information, that we should stop the
    # current flow and wait for a callback
    if 'Callback' in response.headers and response.headers['Callback'] == 'True': 
        redis_db.set(callback_uuid, json.dumps({'instance':instance_id, 'event':event_key}))
        return 'wait for callback'
    
    return 'go on'



######
######
######
# ALL REGARDING THE TIME MANAGEMENT
# TODO: MAYBE IT'S POSSIBLE TO OUTSOURCE THAT ENDPOINTS TO SOMETHING LIKE "TIME_ENDPOINTS.PY"
######
######
######

# POST - immediatley fire the next callback (without changing time)
@app.route('/runner/<instance_id>/fire/', methods = ['POST'])
def fire_callback(instance_id):
    print('fire called for instance ' + str(instance_id)) # fire inject and stay on current time
    return 'Fired'

# POST - jump to the next callback (by changing the gametime)
@app.route('/runner/<instance_id>/jumpto/', methods = ['POST'])
def jumpto_callback(instance_id):
    print('jumpto called for instance ' + str(instance_id)) # set 1_livetime to the time of the current time_call
    return 'Jumped'

#POST - add to current GameTime
@app.route("/runner/<instance_id>/gametime/", methods = ['POST'])
def addGametime(instance_id):
    print('gametime called for instance ' + str(instance_id)) # add to 1_livetime
    return 'ok'

@app.route('/runner/<instance_id>/interval/', methods = ['POST'])
def updateInterval(instance_id):
    print('interval called for instance ' + str(instance_id)) # set 1_interval to new interval
    return 'ok'

#start thread with timer
@app.route('/runner/<instance_id>/pause/', methods = ['POST'])
def setPause(instance_id):
    print('pause called for instance ' + str(instance_id)) # set 1_pause true in redis
    return 'ok'

# start thread with timer
# todo: CHECK WHAT HAPPENS TO THE RUN METHOD, WHEN JUST DESTROYING THE OBJECT BY ASSIGNING IT "None"
@app.route('/runner/<instance_id>/kill/', methods = ['POST'])
def killGame(instance_id):
    print('kill called for instance ' + str(instance_id)) #brauch ich das?! das sollte default passieren
    return 'ok'






# JUST FOR TESTING THE PROCESS FLOWS
@app.route('/test', methods = ['POST'])
def test():
    print(request.values['test'])
    response = Response()
    #response.headers['Callback'] = "True"
    #print(request.headers['Callback-Url'])
    return response