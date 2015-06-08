'''
Created on May 28, 2015

@author: local
'''
import requests
import json
import os
import sys



def setupSensor(sensorConfigName):
    configFile = open(sensorConfigName)
    configStr = configFile.read()
    #confg = eval(configStr)
    sensorConfig = json.loads(configStr)
    SensorDb.addSensor(sensorConfig)
    
def setupConfig():
    configuration = Config.parse_local_config_file("Config.unittest.txt")
    Config.setSystemConfig(configuration)
    
    
if __name__ == "__main__":
    
    if os.environ.get("SPECTRUM_BROWSER_HOME") == None:
        print "SpectrumBrowserHome is not set -- exitting"
        os._exit(0)
    if os.environ.get("TEST_DATA_LOCATION") == None:
        print "please specify test data location TEST_DATA_LOCATION -- exitting"
        os._exit(0)
    testDataLocation = os.environ.get("TEST_DATA_LOCATION")
    sys.path.append(os.environ.get("SPECTRUM_BROWSER_HOME") + "/flask")
    import SensorDb
    import os  
    import Config
    import populate_db
    
    setupConfig()
    
    setupSensor("E6R16W5XS.config.json")
    setupSensor("ECR16W4XS.config.json")
    setupSensor("Norfolk.config.json")
    
    if not os.path.exists(testDataLocation):
        print "Please put the test data at ", testDataLocation
        os._exit(0)
        
    if not os.path.exists(testDataLocation + "/FS0714_173_7236.dat"):
        print ("File not found " + testDataLocation +"/FS0714_173_7236.dat")
        os._exit(0)
        
    if not os.path.exists(testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p1.dat"):
        print ("File not found " + testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p1.dat")
        os._exit(0)
        
    if not os.path.exists(testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p2.dat"):
        print ("File not found " + testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p1\2.dat")
        os._exit(0)
    if not os.path.exists(testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p3.dat"):
        print ("File not found "+testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p3.dat" )
        os._exit(0)
    
    
    populate_db.put_data_from_file(testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p1.dat")
    populate_db.put_data_from_file(testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p2.dat")
    populate_db.put_data_from_file(testDataLocation + "/LTE_UL_DL_bc17_bc13_ts109_p3.dat")
    populate_db.put_data_from_file(testDataLocation + "/FS0714_173_7236.dat")
    
    
    
      