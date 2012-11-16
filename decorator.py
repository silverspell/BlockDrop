'''
Created on 15 Eki 2012

@author: Cem.Guler
'''

class LoginDecorator():
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        
    def __call__(self, func):
        def new_f(*args, **kwargs):
            slf = args[0]
            if getattr(slf, "is_logged_in"):
                ret = func(*args, **kwargs)
            else:
                ret = slf.nope()
            return ret
        new_f.__doc__ = func.__doc__
        return new_f


class Test:
    
    def __init__(self):
        self.is_logged_in = True
    
    @LoginDecorator()
    def test(self):
        print self.is_logged_in
        print "Yihhu"
    
    def nope(self):
        print "Nope"
    
    
t = Test()
t.test()