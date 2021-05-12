#!/usr/bin/env python

import time
from mininet.net import Mininet
from mininet.log import setLogLevel


def run():
    setLogLevel('info')
    net = Mininet()

    r1 = net.addHost('r1', ip='192.168.0.1/24')
    r2 = net.addHost('r2', ip='192.168.0.2/24')

    h1 = net.addHost('h1', ip='192.168.1.1/24')
    h2 = net.addHost('h2', ip='192.168.1.2/24')
    h3 = net.addHost('h3', ip='192.168.1.3/24')
    h4 = net.addHost('h4', ip='192.168.1.4/24')

    net.addLink(r1, r2)
    net.addLink(r1, h1)
    net.addLink(r1, h2)
    net.addLink(r2, h3)
    net.addLink(r2, h4)

    r1.cmd('ip link add vxlan0 type vxlan id 100 remote 192.168.0.2 '
           'dstport 4789 dev r1-eth0')
    r2.cmd('ip link add vxlan0 type vxlan id 100 remote 192.168.0.1 '
           'dstport 4789 dev r2-eth0')

    r1.cmd('ip link add br0 type bridge')
    r1.cmd('ip link set dev vxlan0 master br0')
    r1.cmd('ip link set dev r1-eth1 master br0')
    r1.cmd('ip link set dev r1-eth2 master br0')

    r2.cmd('ip link add br0 type bridge')
    r2.cmd('ip link set dev vxlan0 master br0')
    r2.cmd('ip link set dev r2-eth2 master br0')
    r2.cmd('ip link set dev r2-eth1 master br0')

    r1.cmd('ip link set vxlan0 up')
    r2.cmd('ip link set vxlan0 up')
    r1.cmd('ip link set br0 up')
    r2.cmd('ip link set br0 up')

    net.start()

    r2.cmd('tcpdump -i r2-eth0 -w vxlan.pcap &')
    time.sleep(1)

    h1.cmdPrint('ping 192.168.1.4 -c 1')  # send ping in the overlay network
    time.sleep(1)

    r2.cmd('pkill tcpdump')
    time.sleep(1)

    r2.cmdPrint('tshark -Y "icmp && ip.src==192.168.1.1" -r ./vxlan.pcap  -V')
    r2.cmdPrint('rm vxlan.pcap')

    loss_rate = net.ping(hosts=[h1, h2, h3, h4])
    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
