import struct
from io import BytesIO
import binascii
from bson.json_util import dumps
import util
import authentication
import json
import time
import gevent
import memcache
from Queue import Queue
import populate_db
import numpy as np
import threading
import sys
import traceback
import socket
import ssl
from flaskr import jsonify
from Defines import MAX_HOLD
from Defines import SYS
from Defines import LOC
from Defines import DATA
from Defines import TYPE
from Defines import SENSOR_ID
from Defines import SENSOR_KEY
import SensorDb
import DataMessage
from multiprocessing import Process
import Config
import copy
from pubsub import pub
from bitarray import bitarray




isSecure = True
memCache = None

lastDataMessage={}
lastDataMessageInsertedAt={}
lastDataMessageReceivedAt={}
lastDataMessageOriginalTimeStamp={}
WAITING_FOR_NEXT_INTERVAL = 1
BUFFERING = 2
POSTING = 3
APPLY_DRIFT_CORRECTION = True


class MyByteBuffer:

    def __init__(self, ws):
        self.ws = ws
        self.queue = Queue()
        self.buf = BytesIO()



    def readFromWebSocket(self):
        dataAscii = self.ws.receive()
        if dataAscii != None:
            data = binascii.a2b_base64(dataAscii)
            # print data
            if data != None:
                bio = BytesIO(data)
                bio.seek(0)
                self.queue.put(bio)
        return

    def read(self, size):
        val = self.buf.read(size)
        if val == "" :
            if self.queue.empty():
                self.readFromWebSocket()
                self.buf = self.queue.get()
                val = self.buf.read(size)
            else:
                self.buf = self.queue.get()
                val = self.buf.read(size)
        return val

    def readByte(self):
        val = self.read(1)
        retval = struct.unpack(">b", val)[0]
        return retval

    def readChar(self):
        val = self.read(1)
        return val
    
    def close(self):
        self.buf.close()

class OccupancyWorker(threading.Thread):   
    def __init__(self,conn):
        threading.Thread.__init__(self)
        self.conn = conn
        
    def listener(self,arg1,arg2=None):
        try:
            occupancyArray = arg1
            occupancyBitArray = bitarray(endian="big")
            for bit in occupancyArray:
                occupancyBitArray.append(bit)
            self.conn.write(occupancyBitArray.tobytes())
        except:
            pub.unsubscribe(self.listener, self.sensorId)         

        
    def run(self):
        c = ""
        jsonStr = ""
        while c != "}":
            c= self.conn.recv(1)
            jsonStr  = jsonStr + c
        jsonObj = json.loads(jsonStr)
        print "subscription received for " + jsonObj["SensorID"]
        sensorId = jsonObj["SensorID"]
        self.sensorId = sensorId
        pub.subscribe(self.listener,sensorId)  

 

class OccupancyServer(threading.Thread):
    def __init__(self,socket):
        threading.Thread.__init__(self)
        self.socket = socket
              
        
    def run(self):
        while True:
            try :
                print "OccupancyServer: Accepting connections"
                (conn,addr) = self.socket.accept()
                if isSecure:
                    try :
                        cert = Config.getCertFile()
                        c = ssl.wrap_socket(conn,server_side = True, certfile = cert, ssl_version=ssl.PROTOCOL_SSLv3  )
                        t = OccupancyWorker(c)
                    except:
                        traceback.print_exc()
                        conn.close()
                        print "DataStreaming: Unexpected error"
                        return
                else:
                    t = OccupancyWorker(conn)
                util.debugPrint("MySocketServer Accepted a connection from "+str(addr))
                t.start()
            except:
                traceback.print_exc()  
                
                

        


# Socket IO for reading from sensor. TODO : make this a secure socket.
class MySocketServer(threading.Thread):
    def __init__(self,socket,port):
        threading.Thread.__init__(self)
        self.socket = socket
        self.streamingPort = port
        
    def run(self):
        while True:
            util.debugPrint("Starting socket server on "+ str(self.streamingPort))
            (conn,addr) = self.socket.accept()
            if isSecure:
                try :
                    cert = Config.getCertFile()
                    c = ssl.wrap_socket(conn,server_side = True, certfile = cert, ssl_version=ssl.PROTOCOL_SSLv3  )
                    t = Worker(c)  
                    t.start()
                except:
                    traceback.print_exc()
                    conn.close()
                    util.debugPrint( "DataStreaming: Unexpected error")
                    return
            else:
                t = Worker(conn)
                util.debugPrint("MySocketServer Accepted a connection from "+str(addr))
                t.start()
        
        

class Worker(threading.Thread):
    def __init__(self,conn):
        try:
            threading.Thread.__init__(self)
            self.conn = conn
            self.buf = BytesIO()
          
        except:
            traceback.print_exc()
            self.conn.close()
            return
        
    def run(self):
        try:
            readFromInput(self,False)
        except:
            print "error reading sensor socket:", sys.exc_info()[0]
            traceback.print_exc()
            self.conn.close()
            return


    def read(self):
        try:
            val = self.buf.read(1)
            if val == "" or val == None :
                data = self.conn.recv(64)
                #max queue size - put this in config
                self.buf = BytesIO(data)
                val =  self.buf.read(1)
            return val
        except:
            print "Unexpected error:", sys.exc_info()[0]
            print sys.exc_info()
            traceback.print_exc()
            raise
        
    def close(self):
        self.buf.close()



    def readChar(self):
        val = self.read()
        return val

    def readByte(self):
        val = self.read()
        try:
            if val != None:
                retval = struct.unpack(">b", val)[0]
                return retval
            else:
                return None
        except:
            print "Unexpected error:", sys.exc_info()[0]
            print sys.exc_info()
            traceback.print_exc()
            print "val = ", str(val)
            raise
        
    
        


class MemCache:
    """
    Keeps a memory map of the data pushed by the sensor so it is accessible
    by any of the flask worker processes.
    """
    def acquire(self):
        while True:
            key = "lockCounter"
            counter = self.mc.gets(key)
            assert counter is not None, 'Uninitialized counter'
            if self.mc.cas(key, counter+1):
                break

    def release(self):
        self.mc.decr("lockCounter")

    def __init__(self):
        #self.mc = memcache.Client(['127.0.0.1:11211'], debug=0,cache_cas=True)
        self.mc = memcache.Client(['127.0.0.1:11211'], debug=0)
        self.lastDataMessage = {}
        self.lastdataseen = {}
        self.sensordata = {}
        self.dataCounter = {}
        self.dataProducedCounter = {}
        self.dataConsumedCounter = {}
        self.mc.set("dataCounter",self.dataCounter)
        self.mc.set("lockCounter", 0)
        
    def setSocketServerPort(self,port):
        self.acquire()
        socketServerPort = self.mc.get("socketServerPort")
        if socketServerPort == None:
            socketServerPort = []
        socketServerPort.append(port)
        self.mc.set("socketServerPort",socketServerPort)
        self.release()
        
    def getNumberOfWorkers(self):
        socketServerPort = self.mc.get("socketServerPort")
        if socketServerPort == None:
            return 0
        else :
            return len(socketServerPort)
    
    def getSocketServerPorts(self):
        return self.mc.get("socketServerPort")


    def loadLastDataMessage(self,sensorId):
        key = str("lastDataMessage_"+sensorId).encode("UTF-8")
        lastDataMessage = self.mc.get(key)
        if lastDataMessage != None:
            self.lastDataMessage[sensorId] = lastDataMessage
        return self.lastDataMessage

    def setLastDataMessage(self,sensorId,message):
        key = str("lastDataMessage_"+sensorId).encode("UTF-8")
        print "Key = ",key
        self.lastDataMessage[sensorId] = message
        self.mc.set(key,message)

    def loadSensorData(self,sensorId):
        key = str("sensordata_"+sensorId).encode("UTF-8")
        sensordata = self.mc.get(key)
        if sensordata != None:
            self.sensordata[sensorId] = sensordata
        return self.sensordata

    def setSensorData(self,sensorId,data):
        key = str("sensordata_"+sensorId).encode("UTF-8")
        self.sensordata[sensorId] = data
        self.mc.set(key,data)


    def incrementDataProducedCounter(self,sensorId):
        if sensorId in self.dataProducedCounter:
            newCount = self.dataProducedCounter[sensorId]+1
        else:
            newCount = 1
        self.dataProducedCounter[sensorId] = newCount


    def incrementDataConsumedCounter(self,sensorId):
        if sensorId in self.dataConsumedCounter:
            newCount = self.dataConsumedCounter[sensorId]+1
        else:
            newCount = 1
        self.dataConsumedCounter[sensorId] = newCount

    #def incrementDataProducedCounter(self,sensorId):
    #    self.acquire()
    #    try:
    #        key = str("dataCounter_"+ sensorId).encode("UTF-8")
    #        count = self.mc.get(key)
    #        if count != None:
    #            count = count+1
    #        else:
    #            count = 1
    #        self.dataCounter[sensorId] = count
    #        self.mc.set(key,count)
    #    finally:
    #        self.release()

    #def decrementDataProducedCounter(self,sensorId):
    #    self.acquire()
    #    try:
    #        key = str("dataCounter_"+ sensorId).encode("UTF-8")
    #        count = self.mc.get(key)
    #        if count != None:
    #            count = count - 1
    #        else:
    #            count = 0
    #        self.mc.set(key,count)
    #        print "Data counter value for ",sensorId, count
    #    finally:
    #        self.release()



    def setLastDataSeenTimeStamp(self,sensorId,timestamp):
        key = str("lastdataseen_"+ sensorId).encode("UTF-8")
        self.mc.set(key,timestamp)

    def loadLastDataSeenTimeStamp(self,sensorId):
        key = str("lastdataseen_"+sensorId).encode("UTF-8")
        lastdataseen = self.mc.get(key)
        if lastdataseen != None:
            self.lastdataseen[sensorId] = lastdataseen
        return self.lastdataseen



def getSensorData(ws):
    """

    Handle sensor data streaming requests from the web browser.

    """
    try :
        util.debugPrint( "DataStreamng:getSensorData")
        global memCache
        if memCache == None:
            memCache = MemCache()
        token = ws.receive()
        print "token = " , token
        parts = token.split(":")
        sessionId = parts[0]
        if not authentication.checkSessionId(sessionId,"user"):
            ws.close()
            return
        sensorId = parts[1]
        util.debugPrint("sensorId " + sensorId )
        sensorObj = SensorDb.getSensorObj(sensorId)
        util.debugPrint("isStreamingEnabled = " + str(sensorObj.isStreamingEnabled()))
        lastDataMessage = memCache.loadLastDataMessage(sensorId)
        if not sensorId in lastDataMessage or not sensorObj.isStreamingEnabled() :
            ws.send(dumps({"status":"NO_DATA"}))
        else:
            ws.send(dumps({"status":"OK"}))
            ws.send(lastDataMessage[sensorId])
            lastdatatime = -1
            lastdatasent = time.time()
            drift = 0
            while True:
                secondsPerFrame = sensorObj.getStreamingSecondsPerFrame()
                lastdataseen = memCache.loadLastDataSeenTimeStamp(sensorId)
                if sensorId in lastdataseen and lastdatatime != lastdataseen[sensorId]:
                    lastdatatime = lastdataseen[sensorId]
                    sensordata = memCache.loadSensorData(sensorId)
                    memCache.incrementDataConsumedCounter(sensorId)
                    currentTime = time.time()
                    drift = drift + (currentTime - lastdatasent) - secondsPerFrame
                    ws.send(sensordata[sensorId])
                    # If we drifted, send the last reading again to fill in.
                    if drift < 0:
                        drift = 0
                    if drift > secondsPerFrame:
                        if APPLY_DRIFT_CORRECTION:
                            util.debugPrint("Drift detected")
                            ws.send(sensordata[sensorId])
                        drift = 0
                    lastdatasent = currentTime
                gevent.sleep(secondsPerFrame*0.25)
    except:
        traceback.print_exc()
        ws.close()
        util.debugPrint("Error writing to websocket")



def readFromInput(bbuf,isWebSocket):
     util.debugPrint("DataStreaming:readFromInput")
     while True:
         lengthString = ""
         while True:
            lastChar = bbuf.readChar()
            if lastChar == None:
               time.sleep(0.1)
               return
            if len(lengthString) > 1000:
               raise Exception("Formatting error")
            if lastChar == '{':
               headerLength = int(lengthString.rstrip())
               break
            else:
               lengthString += str(lastChar)
         jsonStringBytes = "{"
         while len(jsonStringBytes) < headerLength:
             jsonStringBytes += str(bbuf.readChar())

         jsonData = json.loads(jsonStringBytes)
         if not TYPE in jsonData or not SENSOR_ID in jsonData or not SENSOR_KEY in jsonData:
             util.errorPrint("Invalid message -- closing connection")
             raise Exception("Invalid messag")
             return
         sensorId = jsonData[SENSOR_ID]
         sensorKey = jsonData[SENSOR_KEY]
         if not authentication.authenticateSensor(sensorId, sensorKey):
             util.errorPrint("Sensor authentication failed: " + sensorId)
             raise Exception("Authentication failure")
             return
             
         print dumps(jsonData, sort_keys=True, indent=4)
         
         sensorObj = SensorDb.getSensorObj(sensorId)
         if not sensorObj.isStreamingEnabled():
             raise Exception("Streaming is not enabled")
             return
         # the last time a data message was inserted
         if jsonData[TYPE] == DATA:
              # BUGBUG -- remove this
             if not "Sys2Detect" in jsonData:
                jsonData["Sys2Detect"] = "LTE"
             DataMessage.init(jsonData)
             cutoff = DataMessage.getThreshold(jsonData)
             try:
                state = BUFFERING
                n = DataMessage.getNumberOfFrequencyBins(jsonData)
                sensorId = DataMessage.getSensorId(jsonData)
                lastDataMessageReceivedAt[sensorId] = time.time()
                lastDataMessageOriginalTimeStamp[sensorId] = DataMessage.getTime(jsonData)
                #TODO New parameter should be added to data message.
                timePerMeasurement = DataMessage.getTimePerMeasurement(jsonData)
                samplesPerCapture = int(sensorObj.getStreamingCaptureSampleSizeSeconds()/timePerMeasurement*n)
                isStreamingCaptureEnabled = sensorObj.isStreamingCaptureEnabled()
                sensorData = [0 for i in range(0,samplesPerCapture)]
                spectrumsPerFrame = int(sensorObj.getStreamingSecondsPerFrame() / timePerMeasurement)
                measurementsPerFrame = spectrumsPerFrame * n
                jsonData["_spectrumsPerFrame"] = spectrumsPerFrame
                jsonData["_StreamingFilter"] = sensorObj.getStreamingFilter()
               
                # Keep a copy of the last data message for periodic insertion into the db
                
                memCache.setLastDataMessage(sensorId,json.dumps(jsonData))
                util.debugPrint("DataStreaming: measurementsPerFrame : " + str(measurementsPerFrame) + " n = " + str(n) + " spectrumsPerFrame = " + str(spectrumsPerFrame))
                bufferCounter = 0
                globalCounter = 0
                prevOccupancyArray = [0 for i in range(0,n)]
                occupancyArray = [0 for i in range(0,n)]
                while True:
                    startTime = time.time()
                    if sensorObj.getStreamingFilter() == MAX_HOLD:
                        powerVal = [-100 for i in range(0, n)]
                    else:
                        powerVal = [0 for i in range(0, n)]
                    for i in range(0, measurementsPerFrame):
                        data = bbuf.readByte()
                        globalCounter = globalCounter + 1
                        if not sensorId in lastDataMessage:
                           lastDataMessage[sensorId] = jsonData
                        if state == BUFFERING :
                            sensorData[bufferCounter] = data
                            bufferCounter = bufferCounter + 1
                            if bufferCounter == samplesPerCapture:
                                state = POSTING
                        elif state == POSTING:
                            # Buffer is full so push the data into mongod.
                            util.debugPrint("Inserting Data message")
                            bufferCounter = 0
                            # Time offset since the last data message was received.
                            timeOffset = time.time() - lastDataMessageReceivedAt[sensorId]
                            # Offset the capture by the time since the DataMessage header was received.
                            lastDataMessage[sensorId]["t"] = lastDataMessageOriginalTimeStamp[sensorId] +\
                                                                int(timeOffset)
                            nM = sensorObj.getStreamingCaptureSampleSizeSeconds()/timePerMeasurement
                            lastDataMessage[sensorId]["nM"] = nM
                            lastDataMessage[sensorId]["mPar"]["td"] = int(sensorObj.getStreamingCaptureSampleSizeSeconds())
                            headerStr = json.dumps(lastDataMessage[sensorId],indent=4)
                            headerLength = len(headerStr)
                            if isStreamingCaptureEnabled:
                                # Start the db operation in a seperate process
                                thread = Process(target=populate_db.put_data, \
                                                          args=(headerStr,headerLength),\
                                                kwargs={"filedesc":None,"powers":sensorData})
                                thread.start()
                           
                            lastDataMessageInsertedAt[sensorId] = time.time()
                            state = WAITING_FOR_NEXT_INTERVAL
                        elif state == WAITING_FOR_NEXT_INTERVAL :
                            now = time.time()
                            delta = now - lastDataMessageInsertedAt[sensorId]
                            # Only buffer data when we are at a boundary.
                            if delta > sensorObj.getStreamingSamplingIntervalSeconds() \
                               and globalCounter % n == 0 :
                               state = BUFFERING
                        if data > cutoff:
                            occupancyArray[i%n] = 1
                        else:
                            occupancyArray[i%n] = 0
                        if sensorObj.getStreamingFilter() == MAX_HOLD:
                            powerVal[i % n] = np.maximum(powerVal[i % n], data)
                        else:
                            powerVal[i % n] += data
                        if globalCounter%n == 0 :
                            for j in range(0,len(occupancyArray)):
                                if occupancyArray[j] != prevOccupancyArray[j]:
                                    pub.sendMessage(sensorId,arg1= occupancyArray)
                                    break
                            prevOccupancyArray = copy.copy(occupancyArray)
                    if sensorObj.getStreamingFilter() !=  MAX_HOLD:
                        for i in range(0, len(powerVal)):
                            powerVal[i] = powerVal[i] / spectrumsPerFrame
                    # sending data as CSV values.
                    sensordata = str(powerVal)[1:-1].replace(" ", "")
                    memCache.setSensorData(sensorId,sensordata)
                    lastdataseen  = time.time()
                    memCache.setLastDataSeenTimeStamp(sensorId,lastdataseen)
                    memCache.incrementDataProducedCounter(sensorId)
                    endTime = time.time()
                    if isWebSocket:
                        delta = 0.7 * sensorObj.getStreamingSecondsPerFrame() - endTime + startTime
                        if delta > 0:
                            gevent.sleep(delta)
                        else:
                            gevent.sleep(0.7 * sensorObj.getStreamingSecondsPerFrame())
                       
                                
             except:
                print "Unexpected error:", sys.exc_info()[0]
                print sys.exc_info()
                traceback.print_exc()
                util.logStackTrace(sys.exc_info())
                raise

         elif jsonData[TYPE] == SYS:
            util.debugPrint("DataStreaming: Got a System message -- adding to the database")
            populate_db.put_data(jsonStringBytes, headerLength)
         elif jsonData[TYPE] == LOC:
            util.debugPrint("DataStreaming: Got a Location Message -- adding to the database")
            populate_db.put_data(jsonStringBytes, headerLength)




def dataStream(ws):
    """
    Handle the data stream from a sensor.
    """
    print "Got a connection"
    bbuf = MyByteBuffer(ws)
    global memCache
    if memCache == None :
         memCache = MemCache()
    readFromInput(bbuf,True)

def getSocketServerPort(sensorId):
    
    retval = {}
    global memCache
    if memCache == None:
        memCache = MemCache()
    numberOfWorkers = memCache.getNumberOfWorkers()
    if numberOfWorkers == 0:
        retval["port"] = -1
    else :
        index = hash(sensorId) % numberOfWorkers
        retval["port"] = memCache.getSocketServerPorts()[index]
    return jsonify(retval),200

def getSpectrumMonitoringPort(sensorId):
    retval = {}
    global memCache
    if memCache == None:
        memCache = MemCache()
    numberOfWorkers = memCache.getNumberOfWorkers()
    index = hash(sensorId) % numberOfWorkers
    retval["port"] = memCache.getSocketServerPorts()[index]+1
    return jsonify(retval),200


def startStreamingServer():
    # The following code fragment is executed when the module is loaded.
    if Config.isStreamingSocketEnabled():
        print "Starting streaming server"
        global memCache
        if memCache == None :
            memCache = MemCache()
        port = Config.getStreamingServerPort()
        soc = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        occupancySock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        portAssigned = False
        for p in range(port,port+10,2):
            try :
                print 'Trying port ',p
                soc.bind(('0.0.0.0',p))
                soc.listen(10)
                socketServerPort = p
                occupancyServerPort = p + 1
                occupancySock.bind(('0.0.0.0',occupancyServerPort))
                occupancySock.listen(10)
                memCache.setSocketServerPort(p)
                portAssigned = True
                util.debugPrint( "DataStreaming: Bound to port "+ str(p))
                break
            except:
                print sys.exc_info()
                traceback.print_exc()
                util.debugPrint( "DataStreaming: Bind failed - retry")
        if portAssigned:
            socketServer = MySocketServer(soc,socketServerPort)
            occupancyServer = OccupancyServer(occupancySock)
            occupancyServer.start()
            socketServer.start()
        else:
            util.errorPrint( "DataStreaming: Streaming disabled on worker - no port found.")
    else:
        print "Streaming is not started"

if __name__ == '__main__':
    startStreamingServer()
