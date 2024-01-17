#!/usr/bin/env python

import time

from mininet.net import Mininet
from mininet.log import setLogLevel


def run():
    setLogLevel('info')
    net = Mininet()

    # In h1, overlay1: 192.168.1.1/32, underlay: 10.0.0.1/24
    # In h2, overlay2: 192.168.2.1/32, underlay: 10.0.0.2/24
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')

    net.addLink(h1, h2)

    net.start()

    h1.cmd('ip tunnel add tun0 mode ipip remote 10.0.0.2 local 10.0.0.1')
    h1.cmd('ip link set dev lo up')
    h1.cmd('ip link set dev tun0 up')
    h1.cmd('ip addr add 192.168.1.1/32 dev lo')
    h1.cmd('ip route add 192.168.2.1/32 dev tun0')

    h2.cmd('ip tunnel add tun0 mode ipip remote 10.0.0.1 local 10.0.0.2')
    h2.cmd('ip link set dev lo up')
    h2.cmd('ip link set dev tun0 up')
    h2.cmd('ip addr add 192.168.2.1/32 dev lo')
    h2.cmd('ip route add 192.168.1.1/32 dev tun0')

    h2.cmd('tcpdump -i tun0 -w ipip.pcap icmp &')
    time.sleep(1)

    # Underlay.
    assert "1 received" in h1.cmd('ping -c 1 -W 1 10.0.0.2')
    # Overlay.
    assert "1 received" in h1.cmd('ping -c 1 -W 1 192.168.2.1')
    time.sleep(1)

    h2.cmd('pkill tcpdump')
    time.sleep(1)

    cmd = 'tshark -V -Y "icmp" -r ./ipip.pcap'
    assert "Encapsulation type: Raw IP (7)" in h2.cmd(cmd)
    h2.cmdPrint(cmd)
    h2.cmdPrint('rm ipip.pcap')

    net.stop()
    return 0.0


if __name__ == '__main__':
    run()
