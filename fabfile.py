'''
Created on 13 Kas 2012

@author: Cem.Guler
'''

from __future__ import with_statement
from fabric.api import run, local
from fabric.context_managers import cd
from fabric.contrib.files import exists
from fabric.operations import sudo
from fabric.state import env



def push():
    local("git add *")
    local("git commit")
    local("git push origin master")
    
def pull():
    local("git pull")
    
def development():
    env.user = "cemg"
    env.hosts = ["developer.rpfusion.com"]
    
def production():
    env.user = "cemg"
    env.hosts = []
    
def deploy():
    sudo("pip install twisted redis apns")
    if exists("/etc/init/blockdrop.conf"):
        sudo("stop blockdrop")
    
    sudo("mkdir -p /opt/blockdrop")
    with cd("/opt/blockdrop"):
        if exists("BlockDrop.py"):
            sudo("git pull")
        else:
            sudo("git clone https://silverspell@bitbucket.org/silverspell/blockdrop.git .")
            sudo("cp blockdrop.conf /etc/init/")
            sudo("chmod 644 /etc/init/blockdrop.conf")
        
        sudo("start blockdrop")
    