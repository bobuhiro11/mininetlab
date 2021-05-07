#!/usr/bin/env python

import time
from mininet.net import Mininet
from mininet.log import setLogLevel


def run():
    setLogLevel('info')
    net = Mininet()

    h1 = net.addHost('h1', ip='192.168.0.1/24')
    h2 = net.addHost('h2', ip='192.168.0.2/24')

    net.addLink(h1, h2)

    h1.cmd('ip link add vxlan0 type vxlan id 100 remote 192.168.0.2 '
           'dstport 4789 dev h1-eth0')
    h2.cmd('ip link add vxlan0 type vxlan id 100 remote 192.168.0.1 '
           'dstport 4789 dev h2-eth0')

    h1.cmd('ip link set vxlan0 up')
    h2.cmd('ip link set vxlan0 up')

    h1.cmd('ip address add 192.168.1.1/24 dev vxlan0')
    h2.cmd('ip address add 192.168.1.2/24 dev vxlan0')

    net.start()

    h2.cmd('tcpdump -i h2-eth0 -w vxlan.pcap &')
    time.sleep(1)

    h1.cmdPrint('ping 192.168.1.2 -c 1')  # send ping in the overlay network
    time.sleep(1)

    h2.cmd('pkill tcpdump')
    time.sleep(1)

    h2.cmdPrint('tshark -Y "icmp && ip.src==192.168.1.1" -r ./vxlan.pcap  -V')
    h2.cmdPrint('rm vxlan.pcap')
    net.stop()
    return 0


if __name__ == '__main__':
    run()
