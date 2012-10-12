'''
Created on 11 Eki 2012

@author: cem.guler
'''

from twisted.internet import reactor, protocol, task
from twisted.protocols import basic



class PubSubProto(basic.LineReceiver):
    def __init__(self, factory):
        self.factory = factory
        self.tc = 0
        self.task_id = None
    
    def wait_timeout(self):
        self.sendLine("Timeout")
    
    def timer_event(self):
        self.tc = self.tc + 1
        self.sendLine("%d" % len(self.factory.clients))
        if self.tc == 5:
            self.task.stop()
            
    
    def connectionMade(self):
        self.factory.clients.add(self);
        #self.task = task.LoopingCall(self.timer_event)
        #self.task.start(1, 0)
        self.task_id = task.deferLater(reactor, 5, self.wait_timeout)
        
        
    def connectionLost(self, reason = ""):
        self.factory.clients.remove(self)
    
    def lineReceived(self, line):
        if line.strip() == "CANCEL":
            self.task_id.cancel()
            self.sendLine("OK");
        for c in self.factory.clients:
            if c != self:
                c.sendLine(line)

class PubSubFactory(protocol.Factory):
    def __init__(self):
        self.clients = set()
        
    def buildProtocol(self, addr):
        return PubSubProto(self)
    
reactor.listenTCP(1025, PubSubFactory()) #@UndefinedVariable
reactor.run() #@UndefinedVariable

