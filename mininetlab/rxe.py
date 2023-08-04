#!/usr/bin/env python

from mininet.net import Mininet
from mininet.log import setLogLevel


def run():
    setLogLevel('info')

    net = Mininet()

    h1 = net.addHost('h1', ip='192.168.0.1/24')
    h2 = net.addHost('h2', ip='192.168.0.2/24')

    net.addLink(h1, h2)

    h1.cmd("rdma link add rxe1 type rxe netdev h1-eth0")
    h2.cmd("rdma link add rxe2 type rxe netdev h2-eth0")

    for h in [h1, h2]:
        # noqa: E501, refs: https://github.com/linux-rdma/rdma-core/blob/master/Documentation/librdmacm.md
        h.cmd("modprobe ib_umad")
        h.cmd('sysctl -w net.ipv4.conf.all.arp_ignore=2')
        h.cmd('sysctl -w net.ipv4.conf.all.accept_local=1')
        h.cmdPrint("rdma link")

    net.start()
    # TODO: Use rping or ibping.
    # NOTE: IB Subnet Manger may be needed. e.g., opensm.
    loss_rate = net.pingAll()
    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
