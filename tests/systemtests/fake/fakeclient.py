from twisted.test import proto_helpers
from server import *
from utility_functions import build_packet


class SBFake(object):
    def __init__(self):
        # Monkey patching the connectionMade method to not create a protocol to the gameserver
        setattr(StarryPyServerProtocol, "connect_to_upstream", lambda x: None)

        # Monkey patching abortConnection onto our fake transports
        setattr(proto_helpers.StringTransport, "abortConnection", lambda x: None)

    def send_packet(self, packet_type, payload):
        self.protocol.dataReceived(build_packet(packet_type, payload.replace(" ", "").decode("hex")))


class SBFakeClient(SBFake):
    def __init__(self, config_path):
        super(SBFakeClient, self).__init__()
        global config
        global logger
        setup(config_path)

        # this creates a fake transport (think tcp connection) which has an API similiar to String
        self.tr = proto_helpers.StringTransport()
        self.factory = StarryPyServerFactory()
        self.protocol = self.factory.buildProtocol("127.0.0.1")
        self.tr.protocol = self.protocol

        # Making a connection as a client to the proxy
        self.protocol.makeConnection(self.tr)

    def make_sure_evething_is_stopped(self):
        self.protocol.connectionLost()
        for reactor_user in self.factory.registered_reactor_users:
            if hasattr(reactor_user, "cancel"):
                reactor_user.cancel()
            else:
                reactor_user.stop()


class SBFakeServer(SBFake):
    def __init__(self, client_side_protocol):
        self.tr = proto_helpers.StringTransport()
        self.factory = StarboundClientFactory(client_side_protocol)
        self.protocol = self.factory.buildProtocol("127.0.0.1")
        self.tr.protocol = self.protocol

        # Hence the monkey patch the proxy does not automatically connect to the game server
        # so we do this manually here:
        self.protocol.makeConnection(self.tr)
