"""
MUSIC app local override of base.serve.twist (Twisted interface)

This silences the logs and avoids gzipping (makes no sense in localhost context).
"""

from twisted.application import internet
from twisted.web import server
from twisted.python.log import ILogObserver, FileLogObserver
from twisted.python.logfile import DailyLogFile

from base.serve import Dispatcher
from base.serve.twist import LongSession, EvokeResource, application

class SilentSite(server.Site):
    def log(self, request):
        pass

def start(application, apps=[]):
    "start a twisted instance"
    dispatcher = Dispatcher(apps)  # we only want one instance
    # attach the service to its parent application
    resource = EvokeResource()
    resource.evokeDispatcher = dispatcher
    # set up our server
    fileServer = SilentSite(resource)
    # use long session
    fileServer.sessionFactory = LongSession 
    # start the service
    port = int(list(dispatcher.apps.values())[0]['Config'].port)
    evokeService = internet.TCPServer(port, fileServer)
    evokeService.setServiceParent(application)

    # logging
    logfile = DailyLogFile("twistd.log", "../logs")
    application.setComponent(ILogObserver, FileLogObserver(logfile).emit)
