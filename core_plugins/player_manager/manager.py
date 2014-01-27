import datetime
import json
from functools import wraps
import inspect

from enum import Enum

from sqlalchemy.orm import Session, relationship, backref, object_session
from sqlalchemy import create_engine, Column, Integer, String, DateTime, \
    ForeignKey, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from twisted.python import log
from twisted.words.ewords import AlreadyLoggedIn


Base = declarative_base()


class Banned(Exception):
    pass


class IntEnum(int, Enum):
    pass


class UserLevels(IntEnum):
    GUEST = 0
    REGISTERED = 1
    MODERATOR = 10
    ADMIN = 100
    OWNER = 1000


class Player(Base):
    __tablename__ = 'players'

    uuid = Column(String, primary_key=True)
    name = Column(String)
    last_seen = Column(DateTime)
    access_level = Column(Integer)
    logged_in = Column(Boolean)
    protocol = Column(String)
    client_id = Column(Integer)
    ip = Column(String)
    plugin_storage = Column(String)
    ips = relationship("IPAddress", order_by="IPAddress.id", backref="players")

    def colored_name(self, colors):
        color = colors[str(UserLevels(self.access_level)).split(".")[1].lower()]
        return color + self.name + colors["default"]

    def storage(self,store=None):
        caller = inspect.stack()[1][0].f_locals["self"].__class__.name
        try:
            plugin_storage = json.loads(self.plugin_storage)
        except (ValueError, TypeError):
            plugin_storage = {}

        if store != None:
            plugin_storage[caller] = store
            self.plugin_storage = json.dumps(plugin_storage)
            object_session(self).commit()
        else:
            try:
                return plugin_storage[caller]
            except (ValueError, KeyError, TypeError):
                return {}

class IPAddress(Base):
    __tablename__ = 'ips'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ip = Column(String(16))
    uuid = Column(String, ForeignKey('players.uuid'))
    player = relationship("Player", backref=backref('players', order_by=id))


class Ban(Base):
    __tablename__ = 'bans'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ip = Column(String, unique=True)
    reason = Column(String)


class PlayerManager(object):
    def __init__(self, config):
        self.config = config
        self.engine = create_engine('sqlite:///%s' % self.config.player_db)
        self.session = Session(self.engine)
        Base.metadata.create_all(self.engine)
        for player in self.session.query(Player).all():
            player.logged_in = False

    def fetch_or_create(self, uuid, name, ip, protocol=None):
        if self.session.query(Player).filter_by(uuid=uuid, logged_in=True).first():
            raise AlreadyLoggedIn
        if self.check_bans(ip):
            raise Banned
        while self.whois(name):
            log.msg("Got a duplicate player, affixing _ to name")
            name += "_"
        player = self.session.query(Player).filter_by(uuid=uuid).first()
        if player:
            if player.name != name:
                log.msg("Detected username change.")
                player.name = name
            if ip not in player.ips:
                player.ips.append(IPAddress(ip=ip))
                player.ip = ip
            player.protocol = protocol
        else:
            log.msg("Adding new player with name: %s" % name)
            player = Player(uuid=uuid, name=name,
                            last_seen=datetime.datetime.now(),
                            access_level=int(UserLevels.GUEST),
                            logged_in=False,
                            protocol=protocol,
                            client_id=-1,
                            ip=ip)
            player.ips = [IPAddress(ip=ip)]
            self.session.add(player)
        if uuid == self.config.owner_uuid:
            player.access_level = int(UserLevels.OWNER)
        self.session.commit()
        return player

    def who(self):
        return self.session.query(Player).filter_by(logged_in=True).all()

    def whois(self, name):
        return self.session.query(Player).filter(Player.logged_in == True,
                                                 func.lower(Player.name) == func.lower(name)).first()

    def __del__(self):
        self.session.commit()
        self.session.close()

    def check_bans(self, ip):
        return self.session.query(Ban).filter_by(ip=ip).first() is not None

    def ban(self, ip):
        self.session.add(Ban(ip=ip))
        self.session.commit()

    def get_by_name(self, name):
        return self.session.query(Player).filter(Player.logged_in == True,
                                                 func.lower(Player.name) == func.lower(name)).first()


def permissions(level=UserLevels.OWNER):
    """Provides a decorator to enable/disable permissions based on user level."""

    def wrapper(func):
        func.level = level

        @wraps(func)
        def wrapped_function(self, *args, **kwargs):
            if self.protocol.player.access_level >= level:
                return func(self, *args, **kwargs)
            else:
                self.protocol.send_chat_message("You are not an admin.")
                return False

        return wrapped_function

    return wrapper