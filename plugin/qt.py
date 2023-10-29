import json
import ssl
import time
import random
import string
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QTabWidget, QWidget, QMessageBox, QVBoxLayout, QLineEdit, QPushButton, QLabel, QHBoxLayout, QFormLayout, QListWidget, QListWidgetItem
from electrum.i18n import _
from electrum.gui.qt.util import WindowModalDialog
from electrum.plugin import BasePlugin, hook
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from electrum.transaction import Transaction, PartialTransaction, PartialTxInput, PartialTxOutput
from nostr.event import Event
from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.filter import Filter, Filters
from nostr.key import PrivateKey
import threading

class SignalEmitter(QObject):
    show_inputlist_signal = pyqtSignal(QWidget, QWidget, object, QLabel)

class Plugin(BasePlugin):

    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)
        self.signal_emitter = SignalEmitter()
        self.address_text_fields = {}

    def requires_settings(self):
        return True

    def settings_widget(self, window):
        btn = QtWidgets.QPushButton(_("Settings"))
        btn.clicked.connect(lambda: self.settings_dialog(window))
        return btn

    def settings_dialog(self, window):
        saved_relay = self.config.get('nostr_relay', '')
        d = WindowModalDialog(window, _("joinstr config"))
        self.d = d
        layout = QtWidgets.QVBoxLayout(d)
        relay_label = QtWidgets.QLabel(_("Nostr Relay:"))
        relay_edit = QtWidgets.QLineEdit()
        relay_edit.setText(saved_relay)
        relay_edit.setFixedWidth(300)
        layout.addWidget(relay_label)
        layout.addWidget(relay_edit)
        ok_button = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok, d)
        layout.addWidget(ok_button)
        ok_button.accepted.connect(lambda: self.ok_clicked(relay_edit.text()))
        d.exec_()

    def ok_clicked(self, relay):
        self.config.set_key('nostr_relay', relay, True)
        self.d.accept()


    @hook
    def load_wallet(self, wallet, window):
        if not self.is_enabled():
            return

        tab_widget = QTabWidget()
        tab_widget.setObjectName("coinjoin_tab")

        widget = QWidget()
        layout = QVBoxLayout(widget)

        form_layout = QFormLayout()

        label = QLabel("Enter a new address:")
        self.address_text_fields[wallet] = QLineEdit()
        self.address_text_fields[wallet].setFixedWidth(500)
        submit_button = QPushButton("Register")
        submit_button.setFixedWidth(100)

        field_button_layout = QHBoxLayout()
        field_button_layout.addWidget(self.address_text_fields[wallet])
        field_button_layout.addWidget(submit_button)

        form_layout.addRow(label, field_button_layout)

        layout.addStretch(1)
        layout.addLayout(form_layout)
        layout.addStretch(1)

        tab_widget.addTab(widget, _("Output Registration"))

        window.tabs.addTab(tab_widget, _("Coinjoin"))

        submit_button.clicked.connect(lambda: self.register_output(wallet, self.address_text_fields[wallet].text(), tab_widget))

        self.signal_emitter = SignalEmitter()
        
        self.signal_emitter.show_inputlist_signal.connect(self.show_inputlist)


    def publish_event(self, data, wallet):
        self.saved_relay = self.config.get('nostr_relay', 0)

        relay_manager = RelayManager()
        relay_manager.add_relay(self.saved_relay)
        relay_manager.open_connections({"cert_reqs": ssl.CERT_NONE}) 
        
        time.sleep(1.25) 

        private_key = PrivateKey()

        event = Event(private_key.public_key.hex(), content=json.dumps(data), kind=9194)
        private_key.sign_event(event)

        relay_manager.publish_event(event)
        time.sleep(1)

        if data["type"] == 'output':
            print(f"[joinstr plugin] Output registered for coinjoin. Event ID: {event.id}")
            QMessageBox.information(self.address_text_fields[wallet].parent(), "Output Registration", f"Output registered for coinjoin.\nEvent ID: {event.id}")

        else:
            print(f"[joinstr plugin] Signed input registered for coinjoin. Event ID: {event.id}")
            QMessageBox.information(self.address_text_fields[wallet].parent(), "Input Registration", f"Signed input registered for coinjoin.\nEvent ID: {event.id}")

        relay_manager.close_connections()

    def getevents(self,event_type):

        letters = string.ascii_lowercase
        random_id = ''.join(random.choice(letters) for i in range(10))

        self.saved_relay = self.config.get('nostr_relay', 0)

        filters = Filters([Filter(kinds=[9194])])
        subscription_id = random_id
        request = [ClientMessageType.REQUEST, subscription_id]
        request.extend(filters.to_json_array())

        relay_manager = RelayManager()
        relay_manager.add_relay(self.saved_relay)
        relay_manager.add_subscription(subscription_id, filters)
        relay_manager.open_connections()
        time.sleep(1.25)

        message = json.dumps(request)
        relay_manager.publish_message(message)
        time.sleep(1)

        output_list = []
        input_list = []
  
        i = 0


        while relay_manager.message_pool.has_events():
            event_msg = relay_manager.message_pool.get_event()
            event = json.loads(event_msg.event.content)
            if event_type == 'output':
                try:
                    output_list.append(event['address'])
                except:
                    continue
            elif event_type == 'input':
                try:
                    input_list.append(event['hex'])
                except:
                    continue

            i = i + 1

        relay_manager.close_connections()

        return output_list,input_list,i

    def checkevents(self, event_type):

        '''
        TODO: Remove duplicates and incorrect bitcoin addresses from round_output_list
        ''' 

        time.sleep(30)

        output_list,input_list,num_i = self.getevents(event_type)

        if num_i % 5 !=0 or num_i == 0:
            self.checkevents(event_type)
        else:
            if event_type == 'output':
                self.round_output_list =[]
                for k in range(len(output_list) - 5, len(output_list)):
                    self.round_output_list.append(output_list[k])
            elif event_type == 'input':
                self.round_input_list = []
                for k in range(len(input_list) - 5, len(input_list)):
                    self.round_input_list.append(input_list[k])
            
            if event_type == 'output':
                return self.round_output_list
            elif event_type == 'input':
                return self.round_input_list

    def show_inputlist(self, tab_widget, input_registration_widget, wallet, label):

        layout = input_registration_widget.layout()

        label.setVisible(False)

        select_label = QLabel("Select an input from the list:")
        select_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(select_label)

        input_list = QListWidget()

        for utxo in wallet.get_utxos():
            item = QListWidgetItem(str(utxo.prevout.txid.hex() + ":" + str(utxo.prevout.out_idx)))
            item.setData(Qt.UserRole, utxo)
            input_list.addItem(item)
        layout.addWidget(input_list)

        register_button = QPushButton("Register")
        layout.addWidget(register_button)
        register_button.setFixedWidth(100)

        layout.setAlignment(register_button, Qt.AlignCenter)

        def on_register_button_clicked():
            selected_items = input_list.selectedItems()
            if selected_items:
                selected_item = selected_items[0]
                selected_input = selected_item.data(Qt.UserRole)
                self.register_input(wallet, selected_input, tab_widget)

        register_button.clicked.connect(on_register_button_clicked)

        tab_widget.update()


    def register_output(self, wallet, address, tab_widget):

        event_type ='output'

        address = self.address_text_fields[wallet].text()
        data = {"address": address, "type": "output"}
        self.publish_event(data, wallet)

        self.address_text_fields[wallet].setEnabled(False)

        input_registration_widget = QWidget()
        layout = QVBoxLayout(input_registration_widget)

        label = QLabel("Waiting for other users to register outputs...")
        label.setAlignment(Qt.AlignCenter)

        layout.addWidget(label)

        tab_widget.addTab(input_registration_widget, "Input Registration")

        thread = threading.Thread(target=self.run_checkevents, args=(event_type, tab_widget, input_registration_widget, wallet, label))
        thread.start()
    
    def run_checkevents(self, event_type, tab_widget, input_registration_widget, wallet, label):

        
        if event_type == 'output':
            output_list = self.checkevents('output')
            self.signal_emitter.show_inputlist_signal.emit(tab_widget, input_registration_widget, wallet, label)
        else:
            input_list = self.checkevents('input')

    
    def register_input(self, wallet, selected_input, tab_widget):

        event_type = 'input'

        sighash_type = 0x01 | 0x80  

        '''
        Create PSBT with our input and all registered outputs
        '''
        prevout = selected_input.prevout
        txin = PartialTxInput(prevout=prevout)
        txin._trusted_value_sats = selected_input.value_sats()

        '''
        TODO: Output amount will be based on pool denomination
        '''

        outputs = []
        amount = 1000000

        for address in self.round_output_list:
            outputs.append((address, amount))

        txout = [PartialTxOutput.from_address_and_value(address, int(amount_btc)) for address, amount_btc in outputs]

        self.tx = PartialTransaction.from_io([txin], txout)

        for txin in self.tx.inputs():
            txin.sighash = sighash_type

        signed_tx = wallet.sign_transaction(self.tx, None)

        data = {"hex": str(signed_tx), "type": "input"}
        self.publish_event(data, wallet)

        finalization_widget = QWidget()
        layout = QVBoxLayout(finalization_widget)

        label = QLabel("Waiting for other users to register signed inputs...")
        label.setAlignment(Qt.AlignCenter)

        layout.addWidget(label)

        tab_widget.addTab(finalization_widget, "Finalization")

        thread = threading.Thread(target=self.run_checkevents, args=(event_type, tab_widget, finalization_widget, wallet, label))
        thread.start()

        return signed_tx