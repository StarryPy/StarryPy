import collections
import logging

from construct import Container

import packets


logger = logging.getLogger("starrypy.utility_functions")


def give_item_to_player(player_protocol, item, count=1):
    logger.debug("Giving item %s (count: %s) to %s", item, count, player_protocol.player.name)
    item_count = int(count)
    maximum = 1000
    while item_count > 0:
        x = item_count
        if x > maximum:
            x = maximum
        item_packet = build_packet(packets.Packets.GIVE_ITEM, packets.give_item_write(item, x + 1))
        player_protocol.transport.write(item_packet)
        item_count -= x


def recursive_dictionary_update(d, u):
    for k, v in u.iteritems():
        if isinstance(v, collections.Mapping):
            r = recursive_dictionary_update(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


def build_packet(packet_type, data):
    """
    Convenience method to build packets for sending.
    :param packet_type: An integer 1 <= packet_type <= 48
    :param data: Data to send.
    :return: The build packet.
    :rtype : str
    """
    length = len(data)
    return packets.packet().build(
        Container(id=packet_type, payload_size=length, data=data))


class Planet(object):
    def __init__(self, sector, x, y, z, planet, satellite):
        self.sector = sector
        self.x = x
        self.y = y
        self.z = z
        self.planet = planet
        self.satellite = satellite

    def __str__(self):
        return "%s:%d:%d:%d:%d:%d" % (self.sector, self.x, self.y, self.z, self.planet, self.satellite)


def move_ship_to_coords(protocol, sector, x, y, z, planet, satellite):
    logger.info("Moving %s's ship to coordinates: %s", protocol.player.name,
                ":".join((sector, str(x), str(y), str(z), str(planet), str(satellite))))
    x, y, z, planet, satellite = map(int, (x, y, z, planet, satellite))
    warp_packet = build_packet(packets.Packets.WARP_COMMAND,
                               packets.warp_command_write(t="MOVE_SHIP", sector=sector, x=x, y=y, z=z,
                                                          planet=planet,
                                                          satellite=satellite, player="".encode('utf-8')))
    protocol.client_protocol.transport.write(warp_packet)


def extract_name(l):
    name = []
    if l[0][0] not in ["'", '"']:
        return l[0], l[1:]
    name.append(l[0][1:])
    terminator = l[0][0]
    for idx, s in enumerate(l[1:]):
        if s[-1] == terminator:
            name.append(s[:-1])
            if idx + 2 != len(l):
                return " ".join(name), l[idx + 2:]
            else:
                return " ".join(name), None
        else:
            name.append(s)
    raise ValueError("Final terminator character of <%s> not found" %
                     terminator)