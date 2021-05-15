#!/usr/bin/env python

from mininet.net import Mininet
from mininet.log import setLogLevel
import time

frr_conf = '''
frr defaults datacenter
!
hostname {name}
password zebra
!
vrf vrf100
 vni 100
exit-vrf
!
vrf vrf200
 vni 200
exit-vrf
!
router bgp {asnum}
 bgp router-id  {router_id}
 bgp bestpath as-path multipath-relax
 no bgp network import-check
 neighbor fabric peer-group
 neighbor fabric remote-as external
 neighbor {name}-eth0 interface peer-group fabric
 neighbor {name}-eth1 interface peer-group fabric
 neighbor {name}-eth2 interface peer-group fabric
 address-family ipv4 unicast
  network {router_id}/32
 exit-address-family
 address-family l2vpn evpn
  neighbor fabric activate
  advertise-all-vni
 exit-address-family
!
router bgp {asnum} vrf vrf100
 no bgp network import-check
 address-family l2vpn evpn
  advertise ipv4 unicast
 exit-address-family
!
router bgp {asnum} vrf vrf200
 no bgp network import-check
 address-family l2vpn evpn
  advertise ipv4 unicast
 exit-address-family
!
line vty
!
end
'''

vtysh_conf = '''
service integrated-vtysh-config
'''

daemons = '''
bgpd=yes

vtysh_enable=yes
zebra_options="  -A 127.0.0.1 -s 90000000"
bgpd_options="   -A 127.0.0.1"
'''


def put_file(host, file_name, content, **kwargs):
    with open("/tmp/tmp", mode="w") as f:
        f.write(content.format(**kwargs))
    host.cmdPrint("cp /tmp/tmp " + file_name)


def run():
    setLogLevel('info')
    net = Mininet()

    privateDirs = ['/etc/frr', '/var/run/frr']

    spine = net.addHost('spine', ip='192.168.0.1/32',
                        privateDirs=privateDirs, asnum=65001)
    leaf1 = net.addHost('leaf1', ip='192.168.0.2/32',
                        privateDirs=privateDirs, asnum=65002)
    leaf2 = net.addHost('leaf2', ip='192.168.0.3/32',
                        privateDirs=privateDirs, asnum=65003)

    # tenant #100, subnet #1
    host1 = net.addHost('host1', ip='10.100.1.2/24', mac='00:00:00:01:01:02')
    host2 = net.addHost('host2', ip='10.100.1.3/24', mac='00:00:00:01:01:03')

    # tenant #100, subnet #2
    host3 = net.addHost('host3', ip='10.100.2.2/24', mac='00:00:00:01:02:02')
    host4 = net.addHost('host4', ip='10.100.2.3/24', mac='00:00:00:01:02:03')

    # tenant #200, subnet #1
    host5 = net.addHost('host5', ip='10.200.1.2/24', mac='00:00:00:02:01:02')
    host6 = net.addHost('host6', ip='10.200.1.3/24', mac='00:00:00:02:01:03')

    # tenant #200, subnet #2
    host7 = net.addHost('host7', ip='10.200.2.2/24', mac='00:00:00:02:02:02')
    host8 = net.addHost('host8', ip='10.200.2.3/24', mac='00:00:00:02:02:03')

    net.addLink(spine, leaf1)
    net.addLink(spine, leaf2)
    net.addLink(leaf1, host1)
    net.addLink(leaf2, host2)
    net.addLink(leaf1, host3)
    net.addLink(leaf2, host4)
    net.addLink(leaf1, host5)
    net.addLink(leaf2, host6)
    net.addLink(leaf1, host7)
    net.addLink(leaf2, host8)

    net.start()

    host1.cmd('ip route add default via 10.100.1.1 dev host1-eth0')
    host2.cmd('ip route add default via 10.100.1.1 dev host2-eth0')
    host3.cmd('ip route add default via 10.100.2.1 dev host3-eth0')
    host4.cmd('ip route add default via 10.100.2.1 dev host4-eth0')
    host5.cmd('ip route add default via 10.200.1.1 dev host5-eth0')
    host6.cmd('ip route add default via 10.200.1.1 dev host6-eth0')
    host7.cmd('ip route add default via 10.200.2.1 dev host7-eth0')
    host8.cmd('ip route add default via 10.200.2.1 dev host8-eth0')

    # setup tenant #100
    for h in [leaf1, leaf2]:
        # br101 for l2vni(tenant #100, subnet #1)
        h.cmd('ip link add br101 type bridge')
        h.cmd('ip link set br101 up')
        h.cmd('ip link add vxlan101 type vxlan id 101 local {} dstport 4789 '
              'nolearning'.format(h.IP()))
        h.cmd('ip link set vxlan101 up')
        h.cmd('ip link set vxlan101 master br101')
        h.cmd('ip link set {}-eth1 master br101'.format(h.name))
        h.cmd('ip addr add 10.100.1.1/24 dev br101')

        # br102 for l2vni(tenant #100, subnet #2)
        h.cmd('ip link add br102 type bridge')
        h.cmd('ip link set br102 up')
        h.cmd('ip link add vxlan102 type vxlan id 102 local {} dstport 4789 '
              'nolearning'.format(h.IP()))
        h.cmd('ip link set vxlan102 up')
        h.cmd('ip link set vxlan102 master br102')
        h.cmd('ip link set {}-eth2 master br102'.format(h.name))
        h.cmd('ip addr add 10.100.2.1/24 dev br102')

        # br100 for l3vni(tenant #100)
        h.cmd('ip link add br100 type bridge')
        h.cmd('ip link set br100 up')
        h.cmd('ip link add vxlan100 type vxlan id 100 local {} dstport 4789 '
              'nolearning'.format(h.IP()))
        h.cmd('ip link set vxlan100 up')
        h.cmd('ip link set vxlan100 master br100')

        # vrf100(tenant #100)
        h.cmd('ip link add vrf100 type vrf table 100')
        h.cmd('ip route add table 100 unreachable default metric 4278198272')
        h.cmd('sysctl -w net.ipv4.conf.vrf100.rp_filter=0')
        h.cmd('ip link set vrf100 up')
        h.cmd('ip link set br100 master vrf100')  # l3vni
        h.cmd('ip link set br101 master vrf100')  # l2vni
        h.cmd('ip link set br102 master vrf100')  # l2vni

    # setup tenant #200
    for h in [leaf1, leaf2]:
        # br201 for l2vni(tenant #200, subnet #1)
        h.cmd('ip link add br201 type bridge')
        h.cmd('ip link set br201 up')
        h.cmd('ip link add vxlan201 type vxlan id 201 local {} dstport 4789 '
              'nolearning'.format(h.IP()))
        h.cmd('ip link set vxlan201 up')
        h.cmd('ip link set vxlan201 master br201')
        h.cmd('ip link set {}-eth3 master br201'.format(h.name))
        h.cmd('ip addr add 10.200.1.1/24 dev br201')

        # br202 for l2vni(tenant #200, subnet #2)
        h.cmd('ip link add br202 type bridge')
        h.cmd('ip link set br202 up')
        h.cmd('ip link add vxlan202 type vxlan id 202 local {} dstport 4789 '
              'nolearning'.format(h.IP()))
        h.cmd('ip link set vxlan202 up')
        h.cmd('ip link set vxlan202 master br202')
        h.cmd('ip link set {}-eth4 master br202'.format(h.name))
        h.cmd('ip addr add 10.200.2.1/24 dev br202')

        # br200 for l3vni(tenant #200)
        h.cmd('ip link add br200 type bridge')
        h.cmd('ip link set br200 up')
        h.cmd('ip link add vxlan200 type vxlan id 200 local {} dstport 4789 '
              'nolearning'.format(h.IP()))
        h.cmd('ip link set vxlan200 up')
        h.cmd('ip link set vxlan200 master br200')

        # vrf200(tenant #200)
        h.cmd('ip link add vrf200 type vrf table 200')
        h.cmd('ip route add table 200 unreachable default metric 4278198272')
        h.cmd('sysctl -w net.ipv4.conf.vrf200.rp_filter=0')
        h.cmd('ip link set vrf200 up')
        h.cmd('ip link set br200 master vrf200')  # l3vni
        h.cmd('ip link set br201 master vrf200')  # l2vni
        h.cmd('ip link set br202 master vrf200')  # l2vni

    for h in [spine, leaf1, leaf2]:
        h.cmd('sysctl -w net.ipv4.ip_forward=1')
        h.cmd('sysctl -w net.ipv4.tcp_l3mdev_accept=1')
        h.cmd('sysctl -w net.ipv4.udp_l3mdev_accept=1')
        h.cmd('sysctl -w net.ipv4.conf.default.rp_filter=0')
        h.cmd('sysctl -w net.ipv4.conf.all.rp_filter=0')
        h.cmd('sysctl -w net.ipv4.conf.default.arp_accept=0')
        h.cmd('sysctl -w net.ipv4.conf.default.arp_announce=2')
        h.cmd('sysctl -w net.ipv4.conf.default.arp_filter=0')
        h.cmd('sysctl -w net.ipv4.conf.default.arp_ignore=1')
        h.cmd('sysctl -w net.ipv4.conf.default.arp_notify=1')
        put_file(h, "/etc/frr/daemons", daemons)
        put_file(h, "/etc/frr/vtysh.conf", vtysh_conf)
        put_file(h, "/etc/frr/frr.conf", frr_conf, name=h.name,
                 router_id=h.IP(), asnum=h.params['asnum'])
        h.cmd("/usr/lib/frr/frrinit.sh start")

    time.sleep(5)
    leaf1.cmdPrint('vtysh -c "show bgp summary"')
    leaf1.cmdPrint('vtysh -c "show ip bgp"')
    leaf1.cmdPrint('vtysh -c "show ip bgp l2vpn evpn"')
    leaf1.cmdPrint('vtysh -c "show evpn vni"')
    leaf1.cmdPrint('vtysh -c "show evpn mac vni all"')
    leaf1.cmdPrint('ip route')
    leaf1.cmdPrint('ip route show table 100')
    leaf1.cmdPrint('ip route show table 200')

    loss_rate = net.ping(hosts=[host1, host2, host3, host4]) \
        + net.ping(hosts=[host5, host6, host7, host8])

    assert net.ping(hosts=[host1, host5]) == 100.0

    for h in [spine, leaf1, leaf2]:
        h.cmd("/usr/lib/frr/frrinit.sh stop")

    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
