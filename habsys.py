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
ntx2Lock = None
stopLock = None
stop = False
gpsReader = None 
picReader = None

gpsPin = 16
picPin = 18

sim = 5

GPIO.setup(gpsPin, GPIO.OUT)
GPIO.setup(picPin, GPIO.OUT)

def writeToLog(data):
	lock.acquire()
	print "[%s] %s" % (time.ctime(time.time()), data)
	lock.release()

# function to send both telemetry and packets
def sendData(data):
	ntx2Lock.acquire()
	NTX2 = serial.Serial('/dev/ttyAMA0', 300, serial.EIGHTBITS, serial.PARITY_NONE, serial.STOPBITS_TWO) # opening serial at 300 baud for radio transmission with 8 character bits, no parity and two stop bits
	NTX2.write(data) # write final datastring to the serial port
	NTX2.close()
	ntx2Lock.release()

	writeToLog( data )

# Reads the GPS component
class GpsThreadClass(threading.Thread):
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

			writeToLog( "read data" )
			
			time.sleep(gpsDelay)

		writeToLog("Ending gps thread")

# Controls the pictures on the pi
class PicThreadClass(threading.Thread):
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
			writeToLog( "take a pic" )
			
			time.sleep(pictureDelay)	
			if sim == 10:
				break
			sim = sim + 1

		writeToLog("Ending pic thread")

# We monitor the status of the gps thread and pic threads.
# 
# All Threads Good = green light
# Any Thread Issues = red light
class MonitorThreadClass(threading.Thread):
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
			
			gpsMessage = None
			if gpsReader.is_alive():
				GPIO.output(gpsPin, True)
				gpsMessage = "Gps is good"
			else:
				GPIO.output(gpsPin, False)
				gpsMessage = "Warning: Gps thread issue"

			writeToLog( gpsMessage )
			
			picMessage = None
			if picReader.is_alive():
				GPIO.output(picPin, True)
				picMessage = "Pic is good"
			else:
				GPIO.output(picPin, False)
				picMessage = "Warning; Pic thread issue"

			writeToLog( picMessage )

			time.sleep(2)		

		writeToLog("Ending monitor thread")
		GPIO.cleanup()

class AdminSocket(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)

	def run(self):
		global stop

		serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serversocket.bind(("localhost", 1421))
		serversocket.listen(5)
		writeToLog( "Listening for stop command on port 1421")

		while True:
			(clientsocket, address) = serversocket.accept()

			chunk = clientsocket.recv(4)

			writeToLog(chunk)

			if chunk == "stop":
				stopLock.acquire()
				stop = True
				stopLock.release()

				clientsocket.send("success")
				break
			else:
				clientsocket.send("Invalid command")

			clientsocket.close()

		writeToLog("Ending admin socket")


if __name__ == '__main__':

	lock = threading.Lock()
	ntx2Lock = threading.Lock()
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



