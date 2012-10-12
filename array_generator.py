'''
Created on 11 Eki 2012

@author: cem.guler
'''

from random import choice
import json

l = dict(x = 0, y = 0, o = 0, i = 0)
la = ["x", "y", "o", "i"]


for i in range(1000):
    sel = choice(la)
    l[sel] = l[sel] + 1

print json.dumps(l)


