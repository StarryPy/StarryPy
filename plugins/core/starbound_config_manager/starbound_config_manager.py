import json
from twisted.python.filepath import FilePath
from base_plugin import SimpleCommandPlugin
from plugin_manager import FatalPluginError
from plugins.core import permissions, UserLevels


class StarboundConfigManager(SimpleCommandPlugin):
    name = "starbound_config_manager"
    depends = ['command_dispatcher', 'warpy_plugin']
    commands = ["spawn"]

    def activate(self):
        super(StarboundConfigManager, self).activate()
        try:
            configuration_file = FilePath(self.config.starbound_path).child('starbound.config')
            if not configuration_file.exists():
                raise FatalPluginError(
                    "Could not open starbound configuration file. Tried path: %s" % configuration_file)
        except AttributeError:
            raise FatalPluginError("The starbound path (starbound_path) is not set in the configuration.")
        try:
            with configuration_file.open() as f:
                starbound_config = json.load(f)
        except Exception as e:
            raise FatalPluginError(
                "Could not parse the starbound configuration file as JSON. Error given from JSON decoder: %s" % str(
                    e))
        if self.config.upstream_port != starbound_config['gamePort']:
            raise FatalPluginError(
                "The starbound gamePort option (%d) does not match the config.json upstream_port (%d)." % (
                    starbound_config['gamePort'], self.config.upstream_port))
        self._spawn = starbound_config['defaultWorldCoordinate'].split(":")

    @permissions(UserLevels.GUEST)
    def spawn(self, data):
        """Moves your ship to spawn. Syntax: /move_ship_to_spawn"""
        self.plugins['warpy_plugin'].move_player_ship(self.protocol, [x for x in self._spawn])
        self.protocol.send_chat_message("Moving your ship to spawn.")