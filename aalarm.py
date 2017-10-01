import binascii
import sys
import codecs

from time import sleep

import threading
from collections import deque

from threading import Timer

from flask import Flask


import time

from LcdControl import LcdControl
from MenuControl import MenuControl
from Sensors import GpioSensor
from Nfc import NfcReader
from ConfigLoader import ConfigLoader
from PlayControl import PlayControl
from Alerts import Alerts

class Alarm(object):
    state = False
    dStatusAlarm = {0: 'nominal', 1: 'breach', 2: 'warning', 3: 'alert'}
    status = 0
    TIMEOUT_WARNING = 5
    TIMEOUT_ALERT = 10
    timerWarning = None
    timerAlert = None

    running = None
    queue = None
    lock = None

    def __init__(self, running, queue, lock):
        self.running = running
        self.queue = queue
        self.lock = lock

    def toggleState(self):
        print('Toggle before [%s]' % self.state)
        self.state = not self.state
        print('Toggle after [%s]' % self.state)
        if not self.state:
            print('Online')
            self.status = 0
            #callDomoticz(configDomoticzSceneLeaveUrl)
        else:
            print('Offline')
            #callDomoticz(configDomoticzSceneEnterUrl)

    def setOnline(self):
        self.state = 1

    def setOffline(self):
        self.state = 0
        self.startTimers()

    def reportBreach(self, channel):
        #todo use channel
        self.escaladeState()

    def startTimers(self):
        if not self.timerWarning:
            self.timerWarning = Timer(self.TIMEOUT_WARNING,self.callbackEscalade,args=['warning'])
            self.timerWarning.start()
            self.timerAlert = Timer(self.TIMEOUT_ALERT,self.callbackEscalade,args=['alert'])
            self.timerAlert.start()

    def stopTimers(self):
        print('stop timers')

        if self.timerWarning is not None:
            print('stop warning')
            self.timerWarning.cancel()
        if self.timerAlert is not None:
            print('stop alert')
            self.timerAlert.cancel()

    def callbackEscalade(self, timerName):
        self.escaladeState()

        if timerName == 'warning':
            print('reached warning, warning expired')
            self.timerWarning = None
        if timerName == 'alert':
            print('reached alert, alert expired')
            self.timerAlert = None

    def escaladeState(self):
        if self.state:
            #breach
            if self.status == 0:
                self.status = 1;
                self.startTimers();
            #warning
            elif self.status == 1:
                self.status = 2;
            #alert
            elif self.status == 2:
                self.status = 3;
            print('Escaladed to state ' + self.currentStatus())
            with self.lock:
                self.queue.append('SENSOR_ESCALADE')

    def currentState(self):
        if self.state:
            return 'online'
        else:
            return 'offline'

    def currentStatus(self):
        return self.dStatusAlarm[self.status]



#Threading queues and locks
queue_alarm = deque()
lock_alarm = threading.Lock()

queue_sensors = deque()
lock_sensors = threading.Lock()

queue_nfc = deque()
lock_nfc = threading.Lock()

queue_buttons = deque()
lock_buttons = threading.Lock()

running = True

#ConfigParser
config = ConfigLoader()
validUid = config.getValidUid()

def main_loop():
    while True:
        if queue_buttons:
            with lock_buttons:
                button = queue_buttons.popleft()
                print('button ' + button)
                lcdControl.menuButton(button)

        if queue_sensors:
            with lock_sensors:
                sensor = queue_sensors.popleft()
                #if (alarm.currentState() == 'online'):
                if sensor == 'SENSOR_BREACH':
                    #todo provide channel
                    alarm.reportBreach('sensor')
                # elif sensor == 'SENSOR_ESCALADE':
                #     alarm.sensorBreach()
                lcdControl.displayState(alarm.currentState(), alarm.currentStatus())

        if queue_alarm:
            with lock_alarm:
                queue_alarm.popleft()
                lcdControl.displayState(alarm.currentState(), alarm.currentStatus())

        if queue_nfc:
            with lock_nfc:
                cardUid = queue_nfc.popleft().decode("utf-8")
                print('CARD uid [%s]' % cardUid)
                if cardUid in validUid.values():
                    print ('REQ TOOGLE')
                    alarm.toggleState()
                else :
                    print ('NO VALID')
                lcdControl.displayState(alarm.currentState(), alarm.currentStatus())
                #print('DISPLAY state [%s]' % alarm.currentState())
                #print('DISPLAY status [%s]' % alarm.currentStatus())
                #continue
        sleep(.9)


# LCD
lcdControl = LcdControl()
lcdControl.display('Startup...')

# Controls
menuControl = MenuControl(running, queue_buttons, lock_buttons)

# Alarm status
alarm = Alarm(running, queue_alarm, lock_alarm)

# Alarm sensors
sensors = GpioSensor(running, queue_sensors, lock_sensors)

lcdControl.displayState(alarm.currentState(), alarm.currentStatus())

# NFC Thread
nfc = NfcReader(running, queue_nfc, lock_nfc)
nfc_thread = threading.Thread(target=nfc.nfc_reader)
nfc_thread.start()

#Run mainloop instead of threading it
#main_loop()

#Main thread
main_thread = threading.Thread(target=main_loop)
main_thread.start()

#Flask
app = Flask(__name__)

@app.route("/")
def home():
    return alarm.currentState() + alarm.currentStatus()

@app.route("/status/setOnline")
def setOnline():
    alarm.setOnline()
    lcdControl.displayState(alarm.currentState(), alarm.currentStatus())
    return 'ok'

@app.route("/status/setOffline")
def setOffline():
    alarm.setOffline()
    lcdControl.displayState(alarm.currentState(), alarm.currentStatus())
    return 'ok'

app.run()
