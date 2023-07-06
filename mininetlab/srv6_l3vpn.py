#!/usr/bin/env python

from mininet.net import Mininet
from mininet.log import setLogLevel
from mininet.cli import CLI
import time

frr_conf = '''
frr defaults datacenter
log file /tmp/frr-{name}.log
debug zebra kernel
debug zebra rib detail
!
hostname {name}
password zebra
!
segment-routing
  srv6
    locators
      locator default
        prefix {locator}
      !
    !
  !
!
!
router bgp {asnum}
 bgp router-id  {router_id}
 bgp bestpath as-path multipath-relax
 no bgp network import-check
 no bpp ebgp-requires-policy
 ! https://docs.frrouting.org/en/latest/bgp.html
 !  IPv6 unicast address family is enabled by default for all new neighbors.
 bgp default ipv6-unicast
 bgp default ipv4-vpn
 neighbor {name}-eth0 interface remote-as external
 neighbor {name}-eth0 interface capability extended-nexthop
 !
 segment-routing srv6
   locator default
 !
 !address-family ipv4 vpn
  ! neighbor {name}-eth0 interface activate
  !
 !exit-address-family
 !
 address-family ipv6 unicast
   network {locator}
 exit-address-family
!
router bgp {asnum} vrf vrf10
 bgp router-id  {router_id}
 address-family ipv4 unicast
  redistribute connected
  ! 16 = 0x10
  sid vpn export 16
  rd vpn export {asnum}:10
  rt vpn both 0:10
  import vpn
  export vpn
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
zebra=yes

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

    r1 = net.addHost('r1', ip='fc00:beef::1/64',
                     privateDirs=privateDirs, asnum=65001, router_id='203.0.113.1',
                     locator='2001:db8:1:1::/64', neighbor='fc00:beef::2', remote_asnum=65002)
    r2 = net.addHost('r2', ip='fc00:beef::2/64',
                     privateDirs=privateDirs, asnum=65002, router_id='203.0.113.2',
                     locator='2001:db8:2:2::/64', neighbor='fc00:beef::1', remote_asnum=65001)

    # tenant #10
    c11 = net.addHost('c11', ip='192.168.1.1/24')
    c21 = net.addHost('c21', ip='192.168.2.1/24')
    # host2 = net.addHost('host2', ip='10.0.1.3/24', mac='10:00:10:00:01:03')

    # # tenant #100, subnet #2
    # host3 = net.addHost('host3', ip='10.0.2.2/24', mac='10:00:10:00:02:02')
    # host4 = net.addHost('host4', ip='10.0.2.3/24', mac='10:00:10:00:02:03')

    # # tenant #200, subnet #1
    # host5 = net.addHost('host5', ip='10.0.1.2/24', mac='20:00:10:00:01:02')
    # host6 = net.addHost('host6', ip='10.0.1.3/24', mac='20:00:10:00:01:03')

    # # tenant #200, subnet #3
    # host7 = net.addHost('host7', ip='10.0.3.2/24', mac='20:00:10:00:03:02')
    # host8 = net.addHost('host8', ip='10.0.3.3/24', mac='20:00:10:00:03:03')

    # net.addLink(spine, leaf1)
    # net.addLink(spine, leaf2)
    # net.addLink(leaf1, host1)
    # net.addLink(leaf2, host2)
    # net.addLink(leaf1, host3)
    # net.addLink(leaf2, host4)
    # net.addLink(leaf1, host5)
    # net.addLink(leaf2, host6)
    # net.addLink(leaf1, host7)
    # net.addLink(leaf2, host8)
    net.addLink(r1, r2)
    net.addLink(r1, c11)
    net.addLink(r2, c21)

    net.start()

    for r in [r1, r2]:
        # h.cmd('sysctl -w net.ipv4.tcp_l3mdev_accept=1')
        # h.cmd('sysctl -w net.ipv4.udp_l3mdev_accept=1')
        r.cmd('sysctl -w net.ipv4.conf.default.rp_filter=0')
        r.cmd('sysctl -w net.ipv4.conf.all.rp_filter=0')
        # h.cmd('sysctl -w net.ipv4.conf.default.arp_accept=0')
        # h.cmd('sysctl -w net.ipv4.conf.default.arp_announce=2')
        # h.cmd('sysctl -w net.ipv4.conf.default.arp_filter=0')
        # h.cmd('sysctl -w net.ipv4.conf.default.arp_ignore=1')
        # h.cmd('sysctl -w net.ipv4.conf.default.arp_notify=1')

        # refs: https://onvox.net/2022/06/27/srv6-frr/
        r.cmd('sysctl -w net.ipv6.seg6_flowlabel=1')
        r.cmd('sysctl -w net.vrf.strict_mode=1')
        r.cmd('sysctl -w net.ipv4.ip_forward=1')
        r.cmd('sysctl -w net.ipv6.ip_forward=1')
        r.cmd('sysctl -w net.ipv6.conf.default.autoconf=0')
        r.cmd('sysctl -w net.ipv6.conf.all.autoconf=0')
        # https://ktaka.blog.ccmp.jp/2020/05/linuxslaac-ipv6.html
        r.cmd('sysctl -w net.ipv6.conf.all.addr_gen_mode=0')
        r.cmd('sysctl -w net.ipv6.conf.default.addr_gen_mode=0')
        r.cmd('sysctl -w net.ipv6.conf.all.seg6_enabled=1')
        r.cmd('sysctl -w net.ipv6.conf.default.seg6_enabled=1')
        r.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')
        r.cmd('sysctl -w net.ipv6.conf.default.forwarding=1')

    # host1.cmd('ip route add default via 10.0.1.1 dev host1-eth0')
    # host2.cmd('ip route add default via 10.0.1.1 dev host2-eth0')
    # host3.cmd('ip route add default via 10.0.2.1 dev host3-eth0')
    # host4.cmd('ip route add default via 10.0.2.1 dev host4-eth0')
    # host5.cmd('ip route add default via 10.0.1.1 dev host5-eth0')
    # host6.cmd('ip route add default via 10.0.1.1 dev host6-eth0')
    # host7.cmd('ip route add default via 10.0.3.1 dev host7-eth0')
    # host8.cmd('ip route add default via 10.0.3.1 dev host8-eth0')

    # set up underlay
    for r in [r1, r2]:
        # add ipv6 address and SID/BGP route.
        # r.cmd('ip -6 addr add {} dev {}-eth0'.format(r.params['ip'], r.name))
        if r.name == 'r1':
            r.cmd('ip -6 addr add 2001:db8:1:1::1/128 dev lo')
            # r.cmd('ip -6 route add 2001:db8:2:2::/64 via fc00:beef::2')
            # r.cmd('ip -6 route add 2001:db8::2/128 dev r1-eth0 src 2001:db8::1')
        else:
            r.cmd('ip -6 addr add 2001:db8:2:2::1/128 dev lo')
            # r.cmd('ip -6 route add 2001:db8:1:1::/64 via fc00:beef::1')
            # r.cmd('ip -6 route add 2001:db8::1/128 dev r2-eth0 src 2001:db8::2')

    # setup tenant #10
    c11.cmd('ip route add default via 192.168.1.254')
    c21.cmd('ip route add default via 192.168.2.254')
    for r in [r1, r2]:
        # add vrf
        r.cmd('ip link add vrf10 type vrf table 10')
        r.cmd('ip link set vrf10 up')
        # add GW
        r.cmd('ip link set {}-eth1 master vrf10'.format(r.name))
        r.cmd('ip link set {}-eth1 up'.format(r.name))
        if r.name == "r1":
            r.cmd('ip addr add 192.168.1.254/24 dev {}-eth1'.format(r.name))
        else:
            r.cmd('ip addr add 192.168.2.254/24 dev {}-eth1'.format(r.name))

    # # setup tenant #100
    # for h in [leaf1, leaf2]:
    #     # br101 for l2vni(tenant #100, subnet #1)
    #     h.cmd('ip link add br101 type bridge')
    #     h.cmd('ip link set br101 up')
    #     h.cmd('ip link add vxlan101 type vxlan id 101 local {} dstport 4789 '
    #           'nolearning'.format(h.IP()))
    #     h.cmd('ip link set vxlan101 up')
    #     h.cmd('ip link set vxlan101 master br101')
    #     h.cmd('ip link set {}-eth1 master br101'.format(h.name))
    #     h.cmd('ip addr add 10.0.1.1/24 dev br101')

    #     # br102 for l2vni(tenant #100, subnet #2)
    #     h.cmd('ip link add br102 type bridge')
    #     h.cmd('ip link set br102 up')
    #     h.cmd('ip link add vxlan102 type vxlan id 102 local {} dstport 4789 '
    #           'nolearning'.format(h.IP()))
    #     h.cmd('ip link set vxlan102 up')
    #     h.cmd('ip link set vxlan102 master br102')
    #     h.cmd('ip link set {}-eth2 master br102'.format(h.name))
    #     h.cmd('ip addr add 10.0.2.1/24 dev br102')

    #     # br100 for l3vni(tenant #100)
    #     h.cmd('ip link add br100 type bridge')
    #     h.cmd('ip link set br100 up')
    #     h.cmd('ip link add vxlan100 type vxlan id 100 local {} dstport 4789 '
    #           'nolearning'.format(h.IP()))
    #     h.cmd('ip link set vxlan100 up')
    #     h.cmd('ip link set vxlan100 master br100')

    #     # vrf100(tenant #100)
    #     h.cmd('ip link add vrf100 type vrf table 100')
    #     h.cmd('ip route add table 100 unreachable default metric 4278198272')
    #     h.cmd('sysctl -w net.ipv4.conf.vrf100.rp_filter=0')
    #     h.cmd('ip link set vrf100 up')
    #     h.cmd('ip link set br100 master vrf100')  # l3vni
    #     h.cmd('ip link set br101 master vrf100')  # l2vni
    #     h.cmd('ip link set br102 master vrf100')  # l2vni

    # # setup tenant #200
    # for h in [leaf1, leaf2]:
    #     # br201 for l2vni(tenant #200, subnet #1)
    #     h.cmd('ip link add br201 type bridge')
    #     h.cmd('ip link set br201 up')
    #     h.cmd('ip link add vxlan201 type vxlan id 201 local {} dstport 4789 '
    #           'nolearning'.format(h.IP()))
    #     h.cmd('ip link set vxlan201 up')
    #     h.cmd('ip link set vxlan201 master br201')
    #     h.cmd('ip link set {}-eth3 master br201'.format(h.name))
    #     h.cmd('ip addr add 10.0.1.1/24 dev br201')

    #     # br203 for l2vni(tenant #200, subnet #3)
    #     h.cmd('ip link add br203 type bridge')
    #     h.cmd('ip link set br203 up')
    #     h.cmd('ip link add vxlan203 type vxlan id 203 local {} dstport 4789 '
    #           'nolearning'.format(h.IP()))
    #     h.cmd('ip link set vxlan203 up')
    #     h.cmd('ip link set vxlan203 master br203')
    #     h.cmd('ip link set {}-eth4 master br203'.format(h.name))
    #     h.cmd('ip addr add 10.0.3.1/24 dev br203')

    #     # br200 for l3vni(tenant #200)
    #     h.cmd('ip link add br200 type bridge')
    #     h.cmd('ip link set br200 up')
    #     h.cmd('ip link add vxlan200 type vxlan id 200 local {} dstport 4789 '
    #           'nolearning'.format(h.IP()))
    #     h.cmd('ip link set vxlan200 up')
    #     h.cmd('ip link set vxlan200 master br200')

    #     # vrf200(tenant #200)
    #     h.cmd('ip link add vrf200 type vrf table 200')
    #     h.cmd('ip route add table 200 unreachable default metric 4278198272')
    #     h.cmd('sysctl -w net.ipv4.conf.vrf200.rp_filter=0')
    #     h.cmd('ip link set vrf200 up')
    #     h.cmd('ip link set br200 master vrf200')  # l3vni
    #     h.cmd('ip link set br201 master vrf200')  # l2vni
    #     h.cmd('ip link set br203 master vrf200')  # l2vni

    time.sleep(2)
    for r in [r1, r2]:
        put_file(r, "/etc/frr/daemons", daemons)
        put_file(r, "/etc/frr/vtysh.conf", vtysh_conf)
        put_file(r, "/etc/frr/frr.conf", frr_conf, name=r.name,
                 router_id=r.params["router_id"], asnum=r.params['asnum'],
                 locator=r.params["locator"], neighbor=r.params['neighbor'],
                 remote_asnum=r.params["remote_asnum"])
        r.cmd("/usr/lib/frr/frrinit.sh start")

    time.sleep(5)
    r1.cmdPrint('vtysh -c "show bgp summary"')
    r1.cmdPrint('vtysh -c "show segment-routing srv6 locator"')
    # r1.cmdPrint('vtysh -c "show bgp ipv4 vpn"')
    r1.cmdPrint('vtysh -c "show ipv6 route"')
    r1.cmdPrint('vtysh -c "show bgp ipv4 vpn summary"')
    r1.cmdPrint('vtysh -c "show ip bgp vrf all"')
    r1.cmdPrint('vtysh -c "show bgp segment-routing srv6"')
    # r1.cmdPrint('vtysh -c "show ip route vrf vrf10"')
    # r2.cmdPrint('vtysh -c "show ip route vrf vrf10"')
    CLI(net)
    # leaf1.cmdPrint('vtysh -c "show ip bgp"')
    # leaf1.cmdPrint('vtysh -c "show ip bgp l2vpn evpn"')
    # leaf1.cmdPrint('vtysh -c "show evpn vni"')
    # leaf1.cmdPrint('vtysh -c "show evpn mac vni all"')
    # leaf1.cmdPrint('ip route')

    # assert "100% packet loss" in host1.cmd('ping -c 1 10.0.3.2')
    # assert "0% packet loss" in host1.cmd('ping -c 1 10.0.2.2')

    # loss_rate = net.ping(hosts=[host1, host2, host3, host4]) \
        # + net.ping(hosts=[host5, host6, host7, host8])
    loss_rate = 0.0

    for h in [r1, r2]:
        h.cmd("/usr/lib/frr/frrinit.sh stop")

    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
