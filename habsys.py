#!/usr/bin/python
#
# Flight computer for HAB.
# 
# Dialectify TM
#
# Author: JG
#
import threading
import time
import socket
import serial
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BOARD)

gpsDelay = 2
pictureDelay = 10
count = 20
lock = None
lockIO = None
stopLock = None
stop = False
gpsReader = None 
picReader = None

gpsPin = 16
picPin = 18

sim = 5

GPIO.setup(gpsPin, GPIO.OUT)
GPIO.setup(picPin, GPIO.OUT)

def gpsSerialConnection():
	return serial.Serial('/dev/ttyAMA0', 9600, timeout=1) 

def writeToLog(operation,data):
	lock.acquire()
	print "[%s] [%s] %s" % (time.ctime(time.time()), operation, data)
	lock.release()

def disableSentences():
    gps = gpsSerialConnection()
 
    gps.write("$PUBX,40,GLL,0,0,0,0*5C\r\n")
    gps.write("$PUBX,40,GSA,0,0,0,0*4E\r\n")
    gps.write("$PUBX,40,RMC,0,0,0,0*47\r\n")
    gps.write("$PUBX,40,GSV,0,0,0,0*59\r\n")
    gps.write("$PUBX,40,VTG,0,0,0,0*5E\r\n")
    gps.write("$PUBX,40,GGA,0,0,0,0*5A\r\n")
    
    gps.close()

def parseGPSData(gpsData):
    if gpsData.startswith("$PUBX"): # while we don't have a sentence
        data = gpsData.split(",") # split sentence into individual fields

        if data[18] == "0": # if it does start with a valid sentence but with no fix
            print "No Lock"
            pass
    
        else: # if it does start with a valid sentence and has a fix
    
        # parsing required telemetry fields
            satellites = data[18]
            lats = data[3]
            northsouth = data[4]
            lngs = data[5]
            westeast = data[6]
            altitude = int(float(data[7]))
       
         
            time = data[2]
        
        
 
            time = float(time) # ensuring that python knows time is a float
            string = "%06i" % time # creating a string out of time (this format ensures 0 is included at start if any)
            hours = string[0:2]
            minutes = string[2:4]
            seconds = string[4:6]
            time = str(str(hours) + ':' + str(minutes) + ':' + str(seconds)) # the final time string in form 'hh:mm:ss'
        
            latitude = convert(lats, northsouth)
            longitude = convert(lngs, westeast)
    
            callsign = "NORB_Test"
        
        
            string = str(callsign + ',' + time + ',' + str(counter) + ',' + str(latitude) + ',' + str(longitude) + ',' + satellites + ',' + str(trigger) + ',' + str(altitude)) # the data string
            csum = str(hex(crc16f(string))).upper()[2:] # running the CRC-CCITT checksum
            csum = csum.zfill(4) # creating the checksum data
            datastring = str("$$" + string + "*" + csum + "\n") # appending the datastring as per the UKHAS communication protocol
            counter += 1 # increment the sentence ID for next transmission
            print "now sending the following:", datastring

def readGPS():
	lockIO.acquire()
	gps = gpsSerialConnection()
    gps.write("$PUBX,00*33\n")
    data = gps.readline() 
    gps.close()
    lockIO.release()

    return data

# function to send both telemetry and packets
def sendData(data):
	lockIO.acquire()
	NTX2 = serial.Serial('/dev/ttyAMA0', 300, serial.EIGHTBITS, serial.PARITY_NONE, serial.STOPBITS_TWO) # opening serial at 300 baud for radio transmission with 8 character bits, no parity and two stop bits
	NTX2.write(data) # write final datastring to the serial port
	NTX2.close()
	lockIO.release()

# Reads the GPS component
class GpsThreadClass(threading.Thread):

	CLASSTYPE = "Admin GPS"

	def __init__(self):
		threading.Thread.__init__(self)

	def run(self):
		global stop

		while True:
			try:
				stopLock.acquire()
				if stop:
					break
			finally:
				stopLock.release()

			dataToSend = parseGPSData(readGPS())
			writeToLog(CLASSTYPE, dataToSend) # Ensure we keep a log of this data
			sendData(dataToSend)
			
			time.sleep(gpsDelay)

		writeToLog(CLASSTYPE, "Ending gps thread")

# Controls the pictures on the pi
class PicThreadClass(threading.Thread):

	CLASSTYPE = "Admin Pic"

	def __init__(self):
		threading.Thread.__init__(self)

	def run(self):
		global stop
		global sim
			

		while True:
			try:
				stopLock.acquire()
				if stop:
					# We received the kill command, shutdown threads.
					break
			finally:
				stopLock.release()

			# With the pi camara mod, we can take pictures like this
			# raspistill -vf -hf -o /home/pi/camera/$DATE.jpg
			writeToLog(CLASSTYPE,"we got a pic")
			
			time.sleep(pictureDelay)	
			if sim == 10:
				break
			sim = sim + 1

		writeToLog(CLASSTYPE,"Ending pic thread")

# We monitor the status of the gps thread and pic threads.
# 
# All Threads Good = green light
# Any Thread Issues = red light
class MonitorThreadClass(threading.Thread):

	CLASSTYPE = "Admin Monitor"

	def __init__(self):
		threading.Thread.__init__( self )

	def run(self):
		while True:		
			global stop

			try:
		 		stopLock.acquire()
				if stop:
					# We received the kill command, shutdown threads.
					break
			finally:
				stopLock.release()
			
			if gpsReader.is_alive():
				GPIO.output(gpsPin, True)
			else:
				GPIO.output(gpsPin, False)
				writeToLog(CLASSTYPE,"Warning: Gps thread issue")
			
			if picReader.is_alive():
				GPIO.output(picPin, True)
			else:
				GPIO.output(picPin, False)
				writeToLog(CLASSTYPE,"Warning; Pic thread issue")

			time.sleep(2)		

		writeToLog(CLASSTYPE,"Ending monitor thread")
		GPIO.cleanup()

class AdminSocket(threading.Thread):

	CLASSTYPE = "Admin Socket"

	def __init__(self):
		threading.Thread.__init__(self)

	def run(self):
		global stop
		stopKey = "stop"

		serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serversocket.bind(("localhost", 1421))
		serversocket.listen(5)
		writeToLog(CLASSTYPE,"Listening for stop command on port 1421")

		while True:
			(clientsocket, address) = serversocket.accept()

			chunk = clientsocket.recv(len(stopKey))

			writeToLog(CLASSTYPE,chunk)

			if chunk == stopKey:
				stopLock.acquire()
				stop = True
				stopLock.release()

				clientsocket.send("success")
				break
			else:
				clientsocket.send("Invalid command")

			clientsocket.close()

		writeToLog(CLASSTYPE,"Ending admin socket")


if __name__ == '__main__':

	lock = threading.Lock()
	lockIO = threading.Lock()
	stopLock = threading.Lock()

	adminSocket = AdminSocket()
	adminSocket.start()

	gpsReader = GpsThreadClass()
	gpsReader.start()

	picReader = PicThreadClass()
	picReader.start()

	# After starting up modules we need to monitor the threads.
	monitor = MonitorThreadClass()
	monitor.start()



