"""
Defines a common manager for plugins, which provide the bulk of the
functionality in StarryPy.
"""
import inspect
import logging
import sys

from twisted.internet import reactor
from twisted.internet.task import deferLater

from base_plugin import BasePlugin
from config import ConfigurationManager
from utility_functions import path


class DuplicatePluginError(Exception):
    """
    Raised when there is a plugin of the same name/class already instantiated.
    """


class PluginNotFound(Exception):
    """
    Raised whenever a plugin can't be found from a given name.
    """


class MissingDependency(PluginNotFound):
    """
    Raised whenever there is a missing dependency during the loading
    of a plugin.
    """


class UnresolvedOrCircularDependencyError(Exception):
    """
    Raised whenever there is a circular dependency detected in the loading
    of of plugins.
    """


class PluginManager(object):
    logger = logging.getLogger('starrypy.plugin_manager.PluginManager')

    def __init__(self, factory, base_class=BasePlugin):
        """
        Initializes the plugin manager. When called, with will first attempt
        to get the `ConfigurationManager` singleton and extract the core plugin
        path. After loading the core plugins with `self.load_plugins` it will
        do the same for plugins that may or may not have dependencies.

        :param base_class: The base class to use while searching for plugins.
        """
        self.packets = {}
        self.plugins = {}
        self.plugin_classes = {}
        self.plugins_waiting_to_load = {}

        self.load_order = []

        self.config = ConfigurationManager()
        self.base_class = base_class
        self.factory = factory

        self.plugin_dir = path.child(self.config.plugin_path)
        sys.path.append(self.plugin_dir.path)

    def prepare(self):
        self.load_plugins(
            [
                'core.admin_commands_plugin',
                'core.colored_names',
                'core.command_plugin',
                'core.player_manager_plugin',
                'core.starbound_config_manager'
            ]
        )
        self.load_plugins(self.config.config['initial_plugins'])
        self.logger.info(
            'Loaded plugins:\n\n%s\n',
            '\n'.join(
                [
                    '\t{}'.format(plugin.name)
                    for plugin in self.plugins.itervalues()
                ]
            )
        )

    def installed_plugins(self):
        """
        Returns list of all plugins in the plugin_dir.
        """
        return filter(
            lambda name: not (name is None or name == 'core'),
            (
                self.get_plugin_name_from_file(plugin_file)
                for plugin_file in self.plugin_dir.globChildren('*')
            )
        )

    @staticmethod
    def get_plugin_name_from_file(f):
        if f.isdir():
            return f.basename()
        else:
            return

    def import_plugin(self, name):
        """
        Import plugin that has the given name, and is a subclass of base_class.

        :param name: The name of the plugin to import.
        """
        try:
            mod = __import__(name, globals(), locals(), [], 0)
            for _, plugin in inspect.getmembers(mod, inspect.isclass):
                if (
                        issubclass(plugin, self.base_class) and
                        (plugin is not self.base_class) and
                        (plugin not in self.plugin_classes.iterkeys())
                ):
                    plugin.config = self.config
                    plugin.factory = self.factory
                    plugin.active = False
                    plugin.protocol = None
                    plugin.plugins = {}
                    plugin.logger = logging.getLogger(
                        'starrypy.plugins.{}'.format(plugin.name)
                    )
                    self.plugin_classes[plugin.name] = plugin

        except ImportError:
            self.logger.critical('Import error for %s\n', name)

    def resolve_dependencies(self, dependency_hash):
        """
        Resolves plugin dependency chain.

        :param dependency_hash: Dictionary of dependencies.
        :return: None
        """
        self.plugins_waiting_to_load = {}
        self.load_order = []

        try:
            while len(dependency_hash) > 0:
                ready = [
                    x for x, d in dependency_hash.iteritems() if len(d) == 0
                ]
                if not ready:
                    ex = []
                    for n, d in dependency_hash.iteritems():
                        for dep in d:
                            ex.append(
                                'Dependency of {} on {} not met\n'.format(
                                    n, dep
                                )
                            )
                    raise UnresolvedOrCircularDependencyError(
                        'Unresolved or circular dependencies'
                        ' found:\n{}'.format('\n'.join(ex))
                    )
                for name in ready:
                    self.plugins_waiting_to_load[name] = (
                        self.plugin_classes[name]
                    )
                    self.load_order.append(name)
                    del dependency_hash[name]
                for name, depends in dependency_hash.iteritems():
                    plugin_set = set(
                        self.plugins.iterkeys()
                    ).union(
                        set(self.plugins_waiting_to_load.iterkeys())
                    )
                    dependency_hash[name] = dependency_hash[name].difference(
                        plugin_set
                    )

        except UnresolvedOrCircularDependencyError as e:
            self.logger.critical(str(e))

    def load_plugins(self, plugins_to_load):
        """
        Loads and instantiates plugins that it is asked to.

        :param plugins_to_load: List of plugin names to import.
                                Names must match a folder in plugin_dir.
        :return: None
        """
        for plugin in plugins_to_load:
            self.import_plugin(plugin)

        dependencies = {
            plugin.name: set(plugin.depends)
            for plugin in self.plugin_classes.itervalues()
        }

        self.resolve_dependencies(dependencies.copy())

        new_plugins = []
        for plugin_name in self.load_order:
            if not self.plugins.get(plugin_name, False):
                new_plugins.append(plugin_name)

        self.activate_plugins(new_plugins, dependencies)

    def activate_plugins(self, plugins, dependencies):
        for plugin in (self.plugins_waiting_to_load[x] for x in plugins):
            try:
                self.plugins[plugin.name] = plugin()
                self.logger.debug('Instantiated plugin "%s"', plugin.name)
                if len(plugin.depends) > 0:
                    plugin_deps = (
                        self.plugins[x] for x in dependencies[plugin.name]
                    )
                    for p in plugin_deps:
                        self.plugin_classes[plugin.name].plugins[p.name] = p
                self.plugins[plugin.name].activate()
                self.map_plugin_packets(plugin)
            except FatalPluginError as e:
                self.logger.critical(
                    'A plugin reported a fatal error. Error: %s', str(e)
                )
                raise

    def deactivate_plugins(self):
        for plugin in (self.plugins[x] for x in reversed(self.load_order)):
            try:
                plugin.deactivate()
            except FatalPluginError as e:
                self.logger.critical(
                    'A plugin reported a fatal error. Error: %s', str(e)
                )
                raise
            self.de_map_plugin_packets(plugin)

    def do(self, protocol, when, data):
        """
        Runs a command across all currently loaded plugins.

        :param protocol: The protocol to insert into the plugin.
        :param command: The function name to run, passed as a string.
        :param data: The data to send to the function.

        :return: Whether or not all plugins returned True or None.
        :rtype: bool
        """
        if protocol is None:
            return True

        return_values = []
        packets = self.packets.get(data.id, {}).get(when, {}).itervalues()
        for plugin, packet_method in packets:
            try:
                plugin.protocol = protocol
                res = packet_method(data)
                if res is False:
                    return False
                elif res is None:
                    res = True

                return_values.append(res)
            except:
                self.logger.exception(
                    'Error in plugin %s with function %s.',
                    str(plugin), packet_method.__name__
                )
        return all(return_values)

    def die(self):
        self.deactivate_plugins()

    def map_plugin_packets(self, plugin):
        """
        Maps plugin overridden packets ready to use in do method.
        """
        for packet_id, when_dict in plugin.overridden_methods.iteritems():
            for when, packet_method in when_dict.iteritems():
                self.packets.setdefault(
                    packet_id, {}
                ).setdefault(
                    when, {}
                )[plugin.name] = (plugin, packet_method)

    def de_map_plugin_packets(self, plugin):
        """
        Removes plugin overridden packets method from packets dictionary.
        """
        for packet_id, when_dict in self.packets.iteritems():
            for when, plugins in when_dict.iteritems():
                if plugin.name in plugins:
                    plugins.pop(plugin.name)


def route(func):
    """
    This decorator is used to map methods to appropriate plugin calls.
    """
    logger = logging.getLogger('starrypy.plugin_manager.route')

    def wrapped_function(self, data):
        res = self.plugin_manager.do(self, 'on', data)
        if res:
            res = func(self, data)
            d = deferLater(
                reactor,
                .01,
                self.plugin_manager.do,
                self,
                'after',
                data
            )
            d.addErrback(print_this_defered_failure)
        return res

    def print_this_defered_failure(f):
        logger.error('Deferred function failure. %s', f)

    return wrapped_function


class FatalPluginError(Exception):
    pass
