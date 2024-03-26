#!/usr/bin/env python

import time
from mininet.net import Mininet
from mininet.log import setLogLevel
from future import standard_library
standard_library.install_aliases()
from subprocess import call as subprocess_call  # noqa: E402


def call(args):
    subprocess_call(args, shell=True)


def clean():
    call('rm -f p2.pcap')
    call('rm -f p1.pcap')
    call('ovs-vsctl --if-exists del-br br1')
    call('ovs-vsctl --if-exists del-br br2')


def run():
    setLogLevel('info')
    net = Mininet()

    h1 = net.addHost('h1')
    h2 = net.addHost('h2')

    net.start()
    clean()

    # Add veth pairs.
    # p1 <-> ovs-p1
    # p2 <-> ovs-p2
    h1.cmd('ip link add p1 type veth peer name ovs-p1')
    h2.cmd('ip link add p2 type veth peer name ovs-p2')
    h1.cmd('ip link set ovs-p1 netns 1')
    h2.cmd('ip link set ovs-p2 netns 1')

    # Add bridges.
    opts = 'protocols=OpenFlow10 fail-mode=secure datapath_type=netdev'
    call('ovs-vsctl -- add-br br1 -- set Bridge br1 ' + opts)
    call('ovs-vsctl -- add-br br2 -- set Bridge br2 ' + opts)
    call('ovs-vsctl set bridge br2 other_config:hwaddr=aa:55:aa:55:00:00')

    # Assign interfaces to bridges.
    # br1: ovs-p1, srv6_0 for overlay
    # br2: ovs-p2 for underlay
    call('ovs-vsctl add-port br1 ovs-p1 -- set interface ovs-p1 type="afxdp"')
    call('ovs-vsctl add-port br1 srv6_0 -- set interface srv6_0 type=srv6 ' +
         'options:local_ip=fc00:100::100 options:remote_ip=fc00:100::1')
    call('ovs-vsctl add-port br2 ovs-p2 -- set interface ovs-p2 type="afxdp"')

    # Add flows to overlay bridge.
    call('ovs-ofctl add-flow br1 in_port=ovs-p1,actions=output:srv6_0')
    call('ovs-ofctl add-flow br1 in_port=srv6_0,actions=output:ovs-p1')

    # Add flows to underlay bridge.
    call('ovs-ofctl add-flow br2 in_port=LOCAL,actions=output:ovs-p2')
    call('ovs-ofctl add-flow br2 in_port=ovs-p2,actions=output:LOCAL')

    # Set all interfaces up.
    call('ip link set ovs-p1 up')
    call('ip link set ovs-p2 up')
    call('ip link set br1 up')
    call('ip link set br2 up')
    h1.cmd('ip link set dev p1 up')
    h2.cmd('ip link set dev p2 up')

    # Assign local SID to br2.
    call('ip -6 addr add fc00:100::100/64 dev br2')

    # Add the route and neighbor entry for remote SID.
    call('ovs-appctl tnl/arp/set br2 fc00:100::1 aa:55:aa:55:00:01')

    # Check SRv6 encapsulation.
    h2.cmd('tcpdump -i p2 -w p2.pcap &')
    time.sleep(1)
    h1.cmd('''
        python3 -c "from scapy.all import *; \
            pkt=Ether(dst='aa:55:aa:55:00:ff',src='aa:55:aa:55:00:ee') \
                /IP(dst='192.168.1.1',src='192.168.3.3')/ICMP(); \
            sendp(pkt, iface='p1')"
''')

    time.sleep(3)
    h2.cmd('pkill tcpdump')
    time.sleep(1)
    out = h2.cmd('tshark -V -r p2.pcap icmp')
    assert 'Routing Header for IPv6 (Segment Routing)' in out

    # Check SRv6 decapsulation.
    h1.cmd('tcpdump -i p1 -w p1.pcap &')
    time.sleep(1)
    h2.cmd('''
        python3 -c "from scapy.all import *; \
            pkt=Ether(src='aa:55:aa:55:00:01',dst='aa:55:aa:55:00:00') \
                /IPv6(src='fc00:100::1', dst='fc00:100::100') \
                /IPv6ExtHdrSegmentRouting(addresses=['fc00:100::100']) \
                /IP(dst='192.168.5.5',src='192.168.5.6')/ICMP(); \
            sendp(pkt, iface='p2')"
''')
    time.sleep(3)
    h1.cmd('pkill tcpdump')
    time.sleep(1)
    out = h1.cmd('tshark -r p1.pcap')
    out = h1.cmd('tshark -r p1.pcap')
    out = h1.cmd('tshark -r p1.pcap')
    assert '192.168.5.5  ICMP 42 Echo (ping) request' in out

    clean()
    net.stop()

    return 0.0


if __name__ == '__main__':
    run()
