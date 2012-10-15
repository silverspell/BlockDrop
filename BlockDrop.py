# -*- coding: utf8 -*- 
'''
Created on 12 Eki 2012

@author: Cem.Guler
'''

import json
import uuid
import redis
from twisted.python import log
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import Factory
import hashlib
from twisted.internet import task, reactor
from random import choice


class RedisConnection:
    pool = redis.ConnectionPool(host = "perch.redistogo.com", password="b3d485112308118171792b4dc1e5b4d5", port=9281, db=0)
    
    @staticmethod
    def get_connection():
        return redis.Redis(connection_pool=RedisConnection.pool)


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

    @staticmethod
    def new_user(user_dict):
        u = BlockDropUser()
        u.email = user_dict["email"]
        r = RedisConnection.get_connection()
        if r.sismember("users", u.email):
            log.msg("Duplicate user: %s" % u.email)
            return False
        
        u.password =  hashlib.sha1(u.password).hexdigest()
        u.facebook_id = user_dict["facebook_id"] if user_dict.has_key("facebook_id") else ""
        u.key = hashlib.sha1("%s:%s" % (u.email, u.password))
        
        d = {"email": u.email, "password": u.password, "facebook_id": u.facebook_id, "score": u.score, "key": u.key}
        r.sadd("users", u.email)
        r.set("users:%s"%u.email, Utils.to_json(d))
        return u
    

    @staticmethod
    def get_user(email, password):
        r = RedisConnection.get_connection()
        if Utils.is_valid_member(r, email):
            u_json = r.get("users:%s"%email)
            u = Utils.from_json(u_json)
            if u["password"] == hashlib.sha1(password).hexdigest():
                log.msg("Found user: %s"%email)
                return u
            log.msg("Password incorrect: %s"%email)
            return False
        else:
            log.msg("No user found: %s"%email)
            return False    


    @staticmethod
    def is_valid_member(r, email):
        return r.sismember("users", email)
        
    @staticmethod
    def update_user(user_dict):
        r = RedisConnection.get_connection()
        u = Utils.get_user(user_dict["email"], user_dict["password"])
        if u:
            u["email"] = user_dict["email"]
            u["password"] = hashlib.sha1(user_dict["password"]).hexdigest()
            u["facebook_id"] = user_dict["facebook_id"]
            r.set("users:%s"%u["email"], Utils.to_json(u))
            return u
        else:
            return False

    @staticmethod
    def get_friends(email_list):
        r = RedisConnection.get_connection()
        existing = []
        for friend in email_list:
            if r.sismember("users", friend):
                u = Utils.from_json(r.get("users:%s"%friend))
                existing.append({"friend": friend, "score": u["score"]})
        return existing
    
    @staticmethod
    def generate_game():
        l = {"x": 0, "y": 0, "z": 0, "o": 0}
        la = ["x", "y", "z", "o"]
        for i in range(1000):
            sel = choice(la)
            l[sel] = l[sel] + 1
        return l
    
    
class BlockDropUser:
    def __init__(self):
        self.email = ""
        self.password = ""
        self.facebook_id = ""
        self.score = 0
        self.key = ""
    
    @staticmethod
    def from_dict(d):
        u = BlockDropUser()
        u.email = d["email"] if d.has_key("email") else ""
        u.facebook_id = d["facebook_id"] if d.has_key("facebook_id") else ""
        u.password = d["password"] if d.has_key("password") else ""
        u.score = d["score"] if d.has_key("score") else 0
        u.key = d["key"] if d.has_key("key") else ""
        return u



class BlockDropProto(LineReceiver):
    def __init__(self, factory):
        self.factory = factory
        self.user = None
        self.commands = {"subscribe": self.subscribe, "get_friends": self.get_friends, 
                         "login": self.login, "create_room": self.create_room, 
                         "ready": self.ready, "score_send": self.send_score,
                         "end_game": self.end_game}
        
        self.task_id = None
        self.room_key = None
        
    def connectionMade(self):
        self.factory.players.add(self)
        
    def connectionLost(self, reason = ""):
        self.factory.players.remove(self)
        
    
    def lineReceived(self, line):
        line = line.strip()
        message = json.loads(line)
        result_dict = self.commands[message["action"]](message["data"])
        self.sendLine(Utils.to_json(result_dict))
    
    
    def room_time_out(self):
        td = {"status": "FAIL", "data": {"reason": "friend not responded"}}    
        del self.factory.rooms[self.room_key]
        self.sendLine(Utils.to_json(td))
        self.room_key = None
        
    def score_timer(self):
        score = (self.factory.rooms[self.room_key]["score"]["p1"] 
                 if self.factory.rooms[self.room_key]["p1"] == self.user.email 
                 else self.factory.rooms[self.room_key]["score"]["p2"])
                
        j = {"status": "OK", "data": {"opponent_score": score}}
        self.sendLine(Utils.to_json(j))
    
    def subscribe(self, data):
        if Utils.new_user(data):
            return {"status": "OK"}
        else:
            return {"status": "FAIL"}

    
    def login(self, data):
        u = Utils.get_user(data["email"], data["password"])
        if u:
            self.user = BlockDropUser.from_dict(u)
            return {"status": "OK", "data": {"score": self.user.score}}

        return {"status": "FAIL"}
            

    def get_friends(self, data=None):
        friends = Utils.get_friends(data["email_list"])
        return {"status": "OK", "data": friends}
        
    def create_room(self, data = None):
        room = {"p1": self.user.email, "p1_ready": False, "p2": "", "p2_ready": False, "score": {"p1": 0, "p2": 0}}
        self.room_key = Utils.get_uuid()
        self.factory.rooms[self.room_key] = room
        self.task_id = task.deferLater(reactor, 30, self.room_time_out)
    
    
    
    def join_room(self, data = None):
        """When opponent enters the room.
        1. find your opponent, cancel the timer
        2. Start timer for request ready signal
        Params: 
        data - holds the key for the room
        """
        self.room_key = data["key"]
        self.factory.rooms[self.room_key]["p2"] = self.user.email
        opponent = self.factory.rooms[self.room_key]["p1"]
        for u in self.factory.players:
            if u.user.email == opponent:
                j = {"status": "OK", "data": {"action": "send_ready"}}
                u.task_id.cancel()
                u.sendLine(Utils.to_json(j))
                u.task_id = task.deferLater(reactor, 10, self.room_time_out)
                break
        
        j = {"status": "OK", "data": {"action": "send_ready"}}
        self.task_id = task.deferLater(reactor, 10, self.room_time_out)
        return j
    
    def ready(self, data = None):
        
        if self.factory.rooms[self.room_key]["p1"] == self.user.email:
            self.factory.rooms[self.room_key]["p1_ready"] = True
        else:
            self.factory.rooms[self.room_key]["p2_ready"] = True
        
        
        if self.factory.rooms[self.room_key]["p1_ready"] and self.factory.rooms[self.room_key]["p2_ready"]:
            self.task_id.cancel()
            for u in self.factory.players:
                if u != self and (u.user.email == self.factory.rooms[self.room_key]["p1"] or u.user.email == self.factory.rooms[self.room_key]["p2"]):
                    j = {"status": "OK", "data": {"action": "start", "game": Utils.generate_game()}}
                    u.task_id.cancel()
                    u.sendLine(Utils.to_json(j))
                    u.task_id = task.LoopingCall(self.score_timer)
                    u.task_id.start(3, True)
                    break
            return {"status": "OK", "data": {"action": "start", "game": Utils.generate_game()}}
        
        return {"status": "OK", "data": {"action": "wait"}}
        
            
    def send_score(self, data = None):
        """Collects score"""
        if self.factory.rooms[self.room_key]["p1"] == self.user.email:
            self.factory.rooms[self.room_key]["score"]["p1"] = data["score"]
        else:
            self.factory.rooms[self.room_key]["score"]["p2"] = data["score"]
        
        return {"status": "OK"}
        

    def end_game(self, data = None):
        pass

class BlockDropFactory(Factory):
    def __init__(self):
        self.players = set()
        self.rooms = {}
        
    def buildProtocol(self, addr):
        return BlockDropProto(self)
    


