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
import sys


class CheckAuth():
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        
    def __call__(self, func):
        def new_f(*args, **kwargs):
            slf = args[0]
            if getattr(slf, "is_logged_in"):
                ret = func(*args, **kwargs)
            else:
                ret = {"action": "authenticate"}
            return ret
        new_f.__doc__ = func.__doc__
        return new_f


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
        
        u.password =  hashlib.sha1(user_dict["password"]).hexdigest()
        u.facebook_id = user_dict["facebook_id"] if user_dict.has_key("facebook_id") else ""
        
        d = {"email": u.email, "password": u.password, "facebook_id": u.facebook_id, "score": u.score, "status": "offline"}
        log.msg(d)
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
    def find_user_by_email(email):
        r = RedisConnection.get_connection()
        u_json = r.get("users:%s"%email)
        return Utils.from_json(u_json)
        
        

    @staticmethod
    def is_valid_member(r, email):
        return r.sismember("users", email)
        
    @staticmethod
    def update_user(user_dict):
        r = RedisConnection.get_connection()
        u = Utils.get_user(user_dict["email"], user_dict["password"])
        if u:
            u["email"] = user_dict["email"]
            if user_dict.has_key("password"):
                u["password"] = hashlib.sha1(user_dict["password"]).hexdigest()
                
            if user_dict.has_key("score"):
                u["score"] = user_dict["score"]

            u["facebook_id"] = user_dict["facebook_id"]
            u["udid"] = user_dict["udid"] if user_dict["udid"] else u["udid"]
            u["dev_token"] = user_dict["dev_token"] if user_dict["dev_token"] else u["dev_token"]
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
                #u = Utils.from_json(r.get("users:%s"%friend))
                u = Utils.find_user_by_email(friend)
                existing.append({"friend": friend, "score": u["score"], "status": u["status"]})
        return existing
    
    @staticmethod
    def generate_game():
        l = {"x": 0, "y": 0, "z": 0, "o": 0}
        la = ["x", "y", "z", "o"]
        for i in range(1000):
            sel = choice(la)
            l[sel] = l[sel] + 1
        return l
    
    @staticmethod
    def change_user_status(email, status):
        r = RedisConnection.get_connection()
        u = Utils.find_user_by_email(email)
        if u:
            u["status"] = status
            r.set("users:%s"%u["email"], Utils.to_json(u))
        
    
    
class BlockDropUser:
    def __init__(self):
        self.email = ""
        self.password = ""
        self.facebook_id = ""
        self.score = 0
    
    @staticmethod
    def from_dict(d):
        u = BlockDropUser()
        u.email = d["email"] if d.has_key("email") else ""
        u.facebook_id = d["facebook_id"] if d.has_key("facebook_id") else ""
        u.password = d["password"] if d.has_key("password") else ""
        u.score = d["score"] if d.has_key("score") else 0
        return u



class BlockDropProto(LineReceiver):
    def __init__(self, factory):
        self.factory = factory
        self.user = None
        self.commands = {"subscribe": self.subscribe, "get_friends": self.get_friends, 
                         "login": self.login, "create_room": self.create_room, 
                         "ready": self.ready, "score_send": self.send_score,
                         "finish": self.finish, "quit": self.quit, "prefs": self.get_prefs,
                         "join": self.join_room}
        
        self.is_logged_in = False
        self.task_id = None
        self.room_key = None
        
    def connectionMade(self):
        """Called when a client opens a connection"""
        self.factory.players.add(self)
        j = {"action": "authenticate"}
        self.sendLine(Utils.to_json(j))
        
    def connectionLost(self, reason = ""):
        """Called when a client closes a connection """
        """TO-DO: remove any ongoing games from this."""
        Utils.change_user_status(self.user.email, "offline")
        self.factory.players.remove(self)
        
    
    def lineReceived(self, line):
        """Called when server receives a command"""
        line = line.strip()
        message = json.loads(line)
        if not message.has_key("data"):
            message["data"] = None
        result_dict = self.commands[message["action"]](message["data"])
        if result_dict:
            result_dict["last_cmd"] = message["action"]
            self.sendLine(Utils.to_json(result_dict))
    
    
    def room_time_out(self):
        """General timeout function"""
        td = {"status": "FAIL", "data": {"reason": "friend not responded"}}    
        del self.factory.rooms[self.room_key]
        self.sendLine(Utils.to_json(td))
        self.room_key = None
        Utils.change_user_status(self.user.email, "online")
        
    def score_timer(self):
        """Score sending timeout function"""
        score = (self.factory.rooms[self.room_key]["score"]["p1"] 
                 if self.factory.rooms[self.room_key]["p1"] == self.user.email 
                 else self.factory.rooms[self.room_key]["score"]["p2"])
                
        j = {"status": "OK", "data": {"opponent_score": score}}
        self.sendLine(Utils.to_json(j))
    
    def subscribe(self, data):
        """Called when client sends a subscribe command"""
        if self.user != None:
            return {"status": "FAIL", "reason": "Logoff before new subscription"}
        
        if Utils.new_user(data):
            return {"status": "OK"}
        else:
            return {"status": "FAIL", "reason": "Email already taken"}

    
    def login(self, data):
        """Login command"""
        u = Utils.get_user(data["email"], data["password"])
        if u:
            self.user = BlockDropUser.from_dict(u)
            self.is_logged_in = True
            u["udid"] = data["udid"]
            u["dev_token"] = data["dev_token"]
            r = RedisConnection.get_connection()
            u["udid"] = data["udid"] if data["udid"] else u["udid"]
            u["dev_token"] = data["dev_token"] if data["dev_token"] else u["dev_token"]
            u["status"] = "online" 
            r.set("users:%s"%u["email"], Utils.to_json(u))
            return {"status": "OK", "data": {"score": self.user.score}}
        self.is_logged_in = False
        return {"status": "FAIL"}
            
    @CheckAuth()
    def get_friends(self, data=None):
        """Gets a list of friend email addresses and returns if they are valid subscribers"""
        friends = Utils.get_friends(data["email_list"])
        return {"status": "OK", "data": friends}
    
    @CheckAuth()    
    def create_room(self, data = None):
        """Creates a room"""
        room = {"p1": self.user.email, "p1_ready": False, "p2": data["p2"], "p2_ready": False, "score": {"p1": 0, "p2": 0}}
        self.room_key = Utils.get_uuid()
        self.factory.rooms[self.room_key] = room
        note_sent = False
        for u in self.factory.players:
            if u.user.email == data["p2"]:
                j = {"status": "OK", "data": {"action": "join", "room": self.room_key}}
                u.sendLine(Utils.to_json(j))
                note_sent = True
        if not note_sent:
            log.msg("PUSH should be sent here")
        
        Utils.change_user_status(self.user.email, "ingame")
        self.task_id = task.deferLater(reactor, 45, self.room_time_out)
        return {"status": "OK", "data": {"room_key": self.room_key}}
        
    
    @CheckAuth()
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
        Utils.change_user_status(self.user.email, "ingame")
        j = {"status": "OK", "data": {"action": "send_ready"}}
        self.task_id = task.deferLater(reactor, 10, self.room_time_out)
        return j
    
    @CheckAuth()
    def ready(self, data = None):
        """After both players joined the room, server needs a ready command (for keepalive)"""
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
                self.task_id = task.LoopingCall(self.score_timer)
                self.task_id.start(3, True)
            return {"status": "OK", "data": {"action": "start", "game": Utils.generate_game()}}
        return {"status": "OK", "data": {"action": "wait"}}
        
    @CheckAuth()
    def send_score(self, data = None):
        """Collects score"""
        if self.factory.rooms[self.room_key]["p1"] == self.user.email:
            self.factory.rooms[self.room_key]["score"]["p1"] = data["score"]
        else:
            self.factory.rooms[self.room_key]["score"]["p2"] = data["score"]
        
        return {"status": "OK"}
        
    @CheckAuth()
    def finish(self, data = None):
        """Users call finish after they are finished."""
        self.task_id.cancel()
        
        won = False
        if not self.factory.rooms[self.room_key]["locked"]:
            won = True
            self.factory.rooms[self.room_key]["locked"] = True
        
        
        if self.factory.rooms[self.room_key]["p1"] == self.user.email:
            self.factory.rooms[self.room_key]["score"]["p1"] = data["score"]
            self.factory.rooms[self.room_key]["p1"] = ""
            opponent_score = self.factory.rooms[self.room_key]["score"]["p2"]
        else:
            self.factory.rooms[self.room_key]["score"]["p2"] = data["score"]
            self.factory.rooms[self.room_key]["p2"] = ""
            opponent_score = self.factory.rooms[self.room_key]["score"]["p1"]
                
        if self.factory.rooms[self.room_key]["p1"] == self.factory.rooms[self.room_key]["p2"] == "":
            del self.factory.rooms[self.room_key]
        
        
        self.room_key = ""
        self.user.score = self.user.score + data["score"]
        Utils.update_user({"email": self.user.email, "score": self.user.score, "facebook_id": self.user.facebook_id})
        Utils.change_user_status(self.user.email, "online")        
        
        return {"status": "OK", "data": {"score": self.user.score, "winner": won, "opponent_score": opponent_score}}
    
    def quit(self, data = None):
        log.msg("Graceful close")
        Utils.change_user_status(self.user.email, "offline")
        self.transport.loseConnection()

    @CheckAuth()
    def get_prefs(self, data = None):
        return {"status": "OK", "score": self.user.score}

class BlockDropFactory(Factory):
    def __init__(self):
        self.players = set()
        self.rooms = {}
        
    def buildProtocol(self, addr):
        return BlockDropProto(self)
    
log.startLogging(sys.stdout)
reactor.listenTCP(1025, BlockDropFactory()) #@UndefinedVariable
reactor.run() #@UndefinedVariable
