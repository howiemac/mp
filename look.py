# Add auto-completion and a stored history file of commands to your Python
# interactive interpreter. Requires Python 2.0+, readline. Autocomplete is
# bound to the Esc key by default (you can change it - see readline docs).
#
# Store the file in ~/.pystartup, and set an environment variable to point
# to it:  "export PYTHONSTARTUP=~/.pystartup" in bash.

import atexit
import os
import sys
import readline
import rlcompleter

readline.parse_and_bind('tab: complete')

historyPath = os.path.expanduser("~/.pyhistory")


def save_history(historyPath=historyPath):
    import readline
    readline.write_history_file(historyPath)

if os.path.exists(historyPath):
    print ("reading history file", historyPath)
    readline.read_history_file(historyPath)

atexit.register(save_history)
del atexit, readline, rlcompleter, save_history, historyPath


# fix the path
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(1, os.path.abspath('../..'))

# and do the evoke imports
from config_site import domains
from evoke.serve import Req, Dispatcher

req = Req()
req.cookies = {}

# start up
dispatcher = Dispatcher()
globals().update(dispatcher.apps[domains[0]])

for clsname, cls in dispatcher.apps[domains[0]].items():
    setattr(req, clsname, cls)
