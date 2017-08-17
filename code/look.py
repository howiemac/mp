#fix the path
import os, sys
#sys.path.append(os.path.abspath('.'))
#sys.path.append(os.path.abspath('../..'))
sys.path.insert(0,os.path.abspath('.')) 
sys.path.insert(1,os.path.abspath('../..'))

from .config_site import domains

#start up
from base.serve import Dispatcher
dispatcher = Dispatcher()
globals().update(dispatcher.apps[domains[0]])
