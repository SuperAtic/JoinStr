import requests
import time
import json
import random
import string
import threading
from flask import Flask, render_template, request, session
from jinja2 import Environment, FileSystemLoader
from nostr.event import Event
from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.filter import Filter, Filters
from nostr.key import PrivateKey


app = Flask(__name__)
app.secret_key = 'test-key'

url = "http://127.0.0.1:<PORT>/wallet/<WALLET_NAME>"

'''
Change RPC credentials
'''

headers = {
    'Authorization': 'Basic dXNlcjpwYXNz',
    'Content-Type': 'text/plain'
}

round_input_list = []
round_output_list =[]
round_tx_list =[]
round_vout_list =[]
round_amt_list = []
round_psbt_list = []

def zip_function(a, b):
    return zip(a, b)

env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
env.globals['zip'] = zip_function

def get_random_string(length):

    letters = string.ascii_lowercase
    random_str = ''.join(random.choice(letters) for i in range(length))

    return random_str

def getkey():

    private_key = PrivateKey()
    public_key = private_key.public_key

    return public_key,private_key


def getcoins():
    payload = "{\"jsonrpc\": \"1.0\", \"id\": \"joinstr\", \"method\": \"listunspent\"}"


    response = requests.request("POST", url, headers=headers, data=payload)

    i =0
    tx_list =[]
    vout_list=[]
    amtlist = []
    for i in range(0,len(response.json()['result'])):
        txid = response.json()['result'][i]['txid']
        tx_list.append(str(txid))
        vout = response.json()['result'][i]['vout']
        vout_list.append(str(vout))
        amount = response.json()['result'][i]['amount']
        amtlist.append(str(amount))
        i = i + 1        
    return tx_list,vout_list,amtlist

def publish(data):

    relay_manager = RelayManager()
    relay_manager.add_relay("wss://nostr.openordex.org")
    relay_manager.open_connections()
    time.sleep(2)

    public_key, private_key = getkey()
    event = Event(private_key.public_key.hex(), json.dumps(data), kind=10110)
    private_key.sign_event(event)
    eventid = event.id

    relay_manager.publish_message(event)
    time.sleep(1)
    relay_manager.close_connections()

    return eventid

def getevents(event_type):

    random_id = get_random_string(10)

    filters = Filters([Filter(kinds=[10110])])
    subscription_id = random_id
    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())

    relay_manager = RelayManager()
    relay_manager.add_relay("wss://nostr.openordex.org")
    relay_manager.add_subscription(subscription_id, filters)
    relay_manager.open_connections()
    time.sleep(1.25)

    message = json.dumps(request)
    relay_manager.publish_message(message)
    time.sleep(1)

    utxo_list = []
    amount_list = []
    output_list =[]
    event = {}
    spsbt = []

    i = 0


    while relay_manager.message_pool.has_events():
        event_msg = relay_manager.message_pool.get_event()
        # Ensure event is a valid JSON
        try:
            event = json.loads(event_msg.event.content)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
        continue

        event = json.loads(event_msg.event.content)
        if event_type == "input":
            try:
                utxo_list.append(event['utxo'])
                amount_list.append(event['amount'])
            except:
                continue
        elif event_type == "output":
            try:
                output_list.append(event['address'])
            except:
                continue
        elif event_type == "signed":
            try:
                spsbt.append(event['signed_psbt'])
            except:
                continue

        i = i + 1

    relay_manager.close_connections()

    return event,utxo_list,amount_list, output_list,spsbt,i

def checkevents(event_type):

    time.sleep(30)

    event,input_list,amount_list,output_list,spsbt,num_i = getevents(event_type)

    if num_i % 5 !=0 or num_i == 0:
        checkevents(event_type)
    else:
        if event_type == 'input':
            for k in range(len(input_list) - 5, len(input_list)):
                round_input_list.append(input_list[k])
                round_amt_list.append(amount_list[k])
        elif event_type == 'output':
            for k in range(len(output_list) - 5, len(output_list)):
                round_output_list.append(output_list[k])
        elif event_type == 'signed':
            for k in range(len(spsbt) - 5, len(spsbt)):
                round_psbt_list.append(spsbt[k])

        if event_type == 'input':
            return round_input_list,round_amt_list
        elif event_type == 'output':
            return round_output_list
        elif event_type == 'signed':
            return round_psbt_list

def getaddress():
    payload = "{\"jsonrpc\": \"1.0\", \"id\": \"joinstr\", \"method\": \"getnewaddress\"}"
    response = requests.request("POST", url, headers=headers, data=payload)

    return response.json()['result']

def getutxoinfo(j):

    payload = "{\"jsonrpc\": \"1.0\",\r\n \"id\": \"joinstr\",\r\n  \"method\": \"scantxoutset\",\r\n  \"params\": [\"start\", [\"" + str(round_input_list[j]) + "\"]]\r\n}"
    response = requests.request("POST", url, headers=headers, data=payload)

    txid = response.json()['result']['unspents'][0]['txid']
    vout = response.json()['result']['unspents'][0]['vout']
    amount = response.json()['result']['total_amount']

    return txid,vout,amount

def createtx(round_tx_list, round_vout_list, round_output_list, postmix_ov):

    payload = "{\"jsonrpc\": \"1.0\",\r\n \"id\": \"joinstr\",\r\n  \"method\": \"createpsbt\",\r\n  \"params\": [[{\"txid\":\"" + str(round_tx_list[0]) + "\",\"vout\":" + str(round_vout_list[0]) + "},{\"txid\":\"" + str(round_tx_list[1]) + "\",\"vout\":" + str(round_vout_list[1]) + "}, {\"txid\":\"" + str(round_tx_list[2]) + "\",\"vout\":" + str(round_vout_list[2]) + "},{\"txid\":\"" + str(round_tx_list[3]) + "\",\"vout\":" + str(round_vout_list[3]) + "},{\"txid\":\"" + str(round_tx_list[4]) + "\",\"vout\":" + str(round_vout_list[4]) + "}],\r\n    [{\"" + str(round_output_list[0]) +"\":" + str(postmix_ov) + "},\r\n    {\"" + str(round_output_list[1]) + "\":" + str(postmix_ov) + "},\r\n    {\"" + str(round_output_list[2]) + "\":" + str(postmix_ov) + "},\r\n    {\"" + str(round_output_list[3]) + "\":" + str(postmix_ov) + "},\r\n    {\"" + str(round_output_list[4]) + "\":" + str(postmix_ov) + "}]]\r\n}"
    response = requests.request("POST", url, headers=headers, data=payload)

    upsbt = response.json()['result']

    return upsbt

def signtx(unsigned_psbt):

    payload = "{\"jsonrpc\": \"1.0\",\r\n \"id\": \"joinstr\",\r\n  \"method\": \"walletprocesspsbt\",\r\n  \"params\": [\"" + str(unsigned_psbt) + "\"]\r\n}"
    response = requests.request("POST", url, headers=headers, data=payload)

    signed_psbt = response.json()['result']['psbt']

    return signed_psbt

def combinetx(round_psbt_list):

    print(round_psbt_list)

    payload = "{\"jsonrpc\": \"1.0\",\r\n \"id\": \"joinstr\",\r\n  \"method\": \"combinepsbt\",\r\n  \"params\": [[\"" + str(round_psbt_list[0]) + "\",\"" + str(round_psbt_list[1]) + "\",\"" + str(round_psbt_list[2]) + "\",\"" + str(round_psbt_list[3]) + "\",\"" + str(round_psbt_list[4]) + "\"]]\r\n}"
    response = requests.request("POST", url, headers=headers, data=payload)

    combined_psbt = response.json()['result']
    print(combined_psbt)

    return combined_psbt


def finalizetx(combinedtx):

    payload = "{\"jsonrpc\": \"1.0\",\r\n \"id\": \"joinstr\",\r\n  \"method\": \"finalizepsbt\",\r\n  \"params\": [\"" + str(combinedtx) + "\"]\r\n}"
    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.json())
    final_tx = response.json()['result']['hex']

    return final_tx

def sendtx(finalizedtx):

    url = "https://mempool.space/api/tx"

    payload = str(finalizedtx)
    headers = {
        'Content-Type': 'text/plain'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    txid = response.text

    return txid

def validate_psbt(psbt):

    payload = "{\"jsonrpc\": \"1.0\",\r\n \"id\": \"joinstr\",\r\n  \"method\": \"decodepsbt\",\r\n  \"params\": [\"" + psbt + "\"]\r\n}"
    response = requests.request("POST", url, headers=headers, data=payload)

    if response.status_code == 200:
            decoded_psbt = response.json().get("result", {})

        psbt_outputs = decoded_psbt.get("tx", {}).get("vout", [])
        output_addresses = [output.get("scriptPubKey", {}).get("addresses", [])[0] for output in psbt_outputs]

        if wallet_address in output_addresses:
            return True
        else:
            print("None of the PSBT outputs belong to your wallet.")
            return False
    else:
        print("Error decoding PSBT:", response.text)
        return False
    except Exception as e:
        print("Error decoding PSBT:", str(e))
        return False
    

@app.route('/main')
def select_input():
    tx_list,vout_list, amtlist = getcoins()
    return render_template('coin_template.html', tx_list=tx_list, vout_list=vout_list, amtlist=amtlist, zip=zip)

@app.route('/in', methods=['POST'])
def publishandcheck_input():

    utxo = request.form['utxo']
    amount = request.form['amount']
    data = {"utxo": utxo, "amount": amount, "type": "input"}

    eventid = publish(data)

    print(eventid)

    thread = threading.Thread(target=checkevents, args=('input',), daemon=True)
    thread.start()
    loading=True

    return render_template('in_template.html', eventid=eventid, loading=loading)

@app.route('/out', methods=['GET'])
def publishandcheck_output():

    '''
    TODO: Check if we are publishing the last output for this round and add `last_bool` in event content json based on it
    '''

    address = getaddress()

    data = {"address": address, "type": "output"}

    eventid = publish(data)

    thread = threading.Thread(target=checkevents, args=('output',), daemon=True)
    thread.start()
    loading=True

    return render_template('out_template.html', eventid=eventid, loading=loading)

@app.route('/psbt', methods=['GET'])
def createpsbt():

    input_sum = sum(session.get('round_amt_list'))
    input_list = session.get('round_input_list')
    round_output_list = session.get('round_output_list')

    round_tx_list, round_vout_list = [string.split(':')[0] for string in input_list], [string.split(':')[1] for string in input_list]

    '''
    TODO: Check each amount in round_amt_list and give error if its not supported by joinstr pools
    '''

    postmix_ov = (input_sum - 0.00001)/5

    unsigned_psbt = createtx(round_tx_list, round_vout_list, round_output_list, postmix_ov)

    loading = True
    session['unsigned_psbt'] = unsigned_psbt

    return render_template('psbt_template.html', psbt = unsigned_psbt, loading=loading)

@app.route('/sign', methods=['GET'])
def publishandcheck_signedpsbt():

    psbt = session.get('unsigned_psbt')

    if psbt:
        if validate_psbt(psbt):
            signed_psbt = signtx(psbt)

            if signed_psbt:
                data = {"signed_psbt": signed_psbt, "type": "signed"}

                eventid = publish(data)

                thread = threading.Thread(target=checkevents, args=('signed',), daemon=True)
                thread.start()
                loading = True

                return render_template('sign_template.html', eventid=eventid, loading=loading)
            else:
                print("PSBT signing failed.")
        else:
            print("PSBT validation failed.")
    else:
        print("Unsigned PSBT not found.")

    return render_template('sign_template.html', eventid=None, loading=False)


@app.route('/final', methods=['GET'])
def broadcast():

    psbt_list = session.get('round_psbt_list')
    print(psbt_list)
    combinedtx = combinetx(psbt_list)
    finalizedtx = finalizetx(combinedtx)

    txid = sendtx(finalizedtx)  

    return render_template('final_template.html', txid = txid)

@app.route('/check-status/<event_type>')
def check_status(event_type):
    if event_type == 'input':
        session['round_input_list'] = round_input_list
        session['round_amt_list'] = [float(i) for i in round_amt_list]
        list_to_check = round_input_list
    elif event_type == 'output':
        session['round_output_list'] = round_output_list
        list_to_check = round_output_list
    elif event_type == 'signed':
        session['round_psbt_list'] = round_psbt_list
        list_to_check = round_psbt_list

    if len(list_to_check) == 5:
        print("true")
        return 'true'
    else:
        print("false")
        return 'false'

