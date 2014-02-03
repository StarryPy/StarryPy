import io
import json
import logging
import inspect
import sys
from utility_functions import recursive_dictionary_update


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args,
                                                                 **kwargs)
        return cls._instances[cls]


class ConfigurationManager(object):
    __metaclass__ = Singleton
    logger = logging.getLogger("starrypy.config.ConfigurationManager")

    def __init__(self, config_path):
        try:
            with open(config_path+".default", "r") as default_config:
                default = json.load(default_config)
        except IOError:
            self.logger.critical("The configuration defaults file (config.json.default) doesn't exist! Shutting down.")
            sys.exit()
        except ValueError:
            self.logger.critical("The configuration defaults file (config.json.default) contains invalid JSON. Please run it against a JSON linter, such as http://jsonlint.com. Shutting down." )
            sys.exit()
        try:
            with open(config_path, "r") as c:
                config = json.load(c)
                self.config = recursive_dictionary_update(default, config)
        except IOError:
            self.logger.warning("The configuration file (config.json) doesn't exist! Creating one from defaults.")
            try:
                with open("config/config.json", "w") as f:
                    json.dump(default, f, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii = False)
            except IOError:
                self.logger.critical("Couldn't write a default configuration file. Please check that StarryPy has write access in the config/ directory.")
                self.logger.critical("Exiting...")
                sys.exit()
            self.logger.warning("StarryPy will now exit. Please examine config.json and adjust the variables appropriately.")
            sys.exit()
        except ValueError:
            self.logger.critical("The configuration file (config.json) contains invalid JSON. Please run it against a JSON linter, such as http://jsonlint.com. Shutting down.")
            sys.exit()
        self.logger.debug("Created configuration manager.")
        self.config_path = config_path
        self.save()

    def save(self):
        try:
            with io.open(self.config_path, "w", encoding="utf-8") as config:
                self.logger.debug("Writing configuration file.")
                config.write(json.dumps(self.config, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii = False))
        except Exception as e:
            self.logger.critical("Tried to save the configuration file, failed.\n%s", str(e))
            raise

    def __getattr__(self, item):
        if item == "config":
            return super(ConfigurationManager, self).__getattribute__(item)


        elif item == "plugin_config":
            caller = inspect.stack()[1][0].f_locals["self"].__class__.name
            if caller in self.config["plugin_config"]:
                return self.config["plugin_config"][caller]
            else:
                return {}

        else:
            if item in self.config:
                return self.config[item]
            else:
                self.logger.error("Couldn't find configuration option %s in configuration file.", item)
                raise AttributeError

    def __setattr__(self, key, value):
        if key == "config":
            super(ConfigurationManager, self).__setattr__(key, value)
        elif key == "plugin_config":
            caller = inspect.stack()[1][0].f_locals["self"].__class__.name
            self.config["plugin_config"][caller] = value
        else:
            self.config[key] = value
        self.save()
