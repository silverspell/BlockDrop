'''
Created on 12 Eki 2012

@author: Cem.Guler
'''
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import Factory
import json
import uuid




class Utils:
    @staticmethod
    def to_json(d):
        return json.dumps(d)
    
    @staticmethod
    def from_json(s):
        return json.loads(s)

    @staticmethod
    def get_uuid():
        return str(uuid.uuid4())

    


class BlockDropUser:
    def __init__(self):
        self.email = ""
        self.password = ""
        self.facebook_id = ""


class BlockDropProto(LineReceiver):
    def __init__(self, factory):
        self.factory = factory
        self.user = None
        self.commands = {"subscribe": self.subscribe, "get_friends": self.get_friends}
        
    def connectionMade(self):
        self.factory.players.add(self)
        
    def connectionLost(self, reason = ""):
        self.factory.players.remove(self)
        
    
    def lineReceived(self, line):
        line = line.strip()
        message = json.loads(line)
        result_dict = self.commands[message["action"]](message["data"])
        self.sendLine(Utils.to_json(result_dict))
        

    
    def subscribe(self, data):
        pass


    def get_friends(self, data=None):
        pass
    

class BlockDropFactory(Factory):
    def __init__(self):
        self.players = set()
        
    def buildProtocol(self, addr):
        return BlockDropProto(self)
    



