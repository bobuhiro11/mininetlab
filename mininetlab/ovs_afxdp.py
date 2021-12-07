#!/usr/bin/env python

from mininet.net import Mininet
from mininet.log import setLogLevel
from future import standard_library
standard_library.install_aliases()

from subprocess import call  # noqa: E402


def run():
    setLogLevel('info')
    net = Mininet()

    h1 = net.addHost('h1')
    h2 = net.addHost('h2')

    net.start()

    # add veth pairs
    h1.cmdPrint('ip link add p0 type veth peer name afxdp-p0')
    h2.cmdPrint('ip link add p1 type veth peer name afxdp-p1')
    h1.cmdPrint('ip link set afxdp-p0 netns 1')
    h2.cmdPrint('ip link set afxdp-p1 netns 1')

    # attach afxdp-p[01] to ovs
    call(
        'ovs-vsctl -- add-br br0 -- set Bridge br0 ' +
        'protocols=OpenFlow10,OpenFlow11,OpenFlow12,OpenFlow13,OpenFlow14 ' +
        'fail-mode=secure datapath_type=netdev', shell=True)
    call(
        'ovs-vsctl add-port br0 afxdp-p0 -- set interface afxdp-p0 ' +
        'external-ids:iface-id="p0" type="afxdp"', shell=True)
    call(
        'ovs-vsctl add-port br0 afxdp-p1 -- set interface afxdp-p1 ' +
        'external-ids:iface-id="p1" type="afxdp"', shell=True)
    call('ovs-ofctl add-flow br0 actions=normal', shell=True)

    # set up interfaces
    call('ip link set afxdp-p0 up', shell=True)
    call('ip link set afxdp-p1 up', shell=True)
    h1.cmdPrint('ip addr add "10.1.1.1/24" dev p0')
    h2.cmdPrint('ip addr add "10.1.1.2/24" dev p1')
    h1.cmdPrint('ip link set dev p0 up')
    h2.cmdPrint('ip link set dev p1 up')

    # testing
    call('ovs-vsctl show', shell=True)
    h1.cmdPrint('ip -br a')
    h2.cmdPrint('ip -br a')
    assert "0% packet loss" in h1.cmdPrint('ping -c 1 10.1.1.2')
    assert "0% packet loss" in h2.cmdPrint('ping -c 1 10.1.1.1')

    # clean up
    h1.cmdPrint('ovs-vsctl del-br br0')
    net.stop()

    return 0.0


if __name__ == '__main__':
    run()
