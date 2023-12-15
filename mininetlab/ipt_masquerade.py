#!/usr/bin/env python

import time

from mininet.net import Mininet
from mininet.log import setLogLevel


def run():
    setLogLevel('info')
    net = Mininet()

    h1 = net.addHost('h1', ip='192.168.0.1/24')
    natbox = net.addHost('natbox', ip='192.168.0.254/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')

    net.addLink(h1, natbox)
    net.addLink(h2, natbox)

    net.start()

    # Add default route in h2.
    h2.cmd('ip route add default via 10.0.0.1')

    # Set up natbox.
    natbox.cmd('sysctl net.ipv4.ip_forward=1')
    natbox.cmd('ip addr add 10.0.0.1/24 dev natbox-eth1')
    with open("/tmp/natconfig", "w") as f:
        f.write('*nat\n')
        f.write(('-A POSTROUTING -s 10.0.0.0/24 -o natbox-eth0 -j' +
                 ' SNAT --to-source 192.168.0.254\n'))
        f.write('COMMIT\n')

    natbox.cmd('iptables-restore -c < /tmp/natconfig')
    natbox.cmd('iptables-restore < /tmp/natconfig')
    natbox.cmdPrint('iptables -vL -t nat | grep -B 1 SNAT')

    loss_rate = net.ping(hosts=[h1, natbox])
    loss_rate += net.ping(hosts=[h2, natbox])
    loss_rate += net.ping(hosts=[h1, h2]) - 50

    h1.cmd('tcpdump -i any -w ipt_masquerade.pcap icmp &')
    time.sleep(1)

    h2.cmd('ping 192.168.0.1 -c 3 -i 0.1')
    time.sleep(1)

    h1.cmd('pkill tcpdump')
    time.sleep(1)

    h1.cmdPrint('tshark -Y "icmp" -r ./ipt_masquerade.pcap')
    h1.cmdPrint('rm ipt_masquerade.pcap')

    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
