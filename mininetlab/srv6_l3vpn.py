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
    with open("./tmp", mode="w") as f:
        f.write(content.format(**kwargs))
    host.cmdPrint("cp ./tmp " + file_name)


def run():
    setLogLevel('info')
    net = Mininet()

    privateDirs = ['/etc/frr', '/var/run/frr', '/tmp']

    r1 = net.addHost('r1', privateDirs=privateDirs, asnum=65001, router_id='203.0.113.1',
                     locator='2001:db8:1:1::/64')
    r2 = net.addHost('r2', privateDirs=privateDirs, asnum=65002, router_id='203.0.113.2',
                     locator='2001:db8:2:2::/64')
    # tenant #10
    c11 = net.addHost('c11', ip='192.168.1.1/24', privateDirs=privateDirs)
    c21 = net.addHost('c21', ip='192.168.2.1/24', privateDirs=privateDirs)
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
        # refs: https://onvox.net/2022/06/27/srv6-frr/
        r.cmd('sysctl -w net.ipv4.conf.default.rp_filter=0')
        r.cmd('sysctl -w net.ipv4.conf.all.rp_filter=0')
        r.cmd('sysctl -w net.ipv6.seg6_flowlabel=1')
        r.cmd('sysctl -w net.vrf.strict_mode=1')
        r.cmd('sysctl -w net.ipv4.ip_forward=1')
        r.cmd('sysctl -w net.ipv6.ip_forward=1')
        r.cmd('sysctl -w net.ipv6.conf.default.autoconf=0')
        r.cmd('sysctl -w net.ipv6.conf.all.autoconf=0')
        r.cmd('sysctl -w net.ipv6.conf.all.addr_gen_mode=0')
        r.cmd('sysctl -w net.ipv6.conf.default.addr_gen_mode=0')
        r.cmd('sysctl -w net.ipv6.conf.all.seg6_enabled=1')
        r.cmd('sysctl -w net.ipv6.conf.default.seg6_enabled=1')
        r.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')
        r.cmd('sysctl -w net.ipv6.conf.default.forwarding=1')

    # set up underlay
    for r in [r1, r2]:
        if r.name == 'r1':
            r.cmd('ip -6 addr add 2001:db8:1:1::1/128 dev lo')
        else:
            r.cmd('ip -6 addr add 2001:db8:2:2::1/128 dev lo')

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

    for c in [c11,c21]:
        put_file(c, "/tmp/index.html", c.name + "\n")
        c.cmd("cd /tmp; python3 -m http.server 80 >/dev/null 2>&1 &")

    for r in [r1, r2]:
        put_file(r, "/etc/frr/daemons", daemons)
        put_file(r, "/etc/frr/vtysh.conf", vtysh_conf)
        put_file(r, "/etc/frr/frr.conf", frr_conf, name=r.name,
                 router_id=r.params["router_id"], asnum=r.params['asnum'],
                 locator=r.params["locator"])
        r.cmd("/usr/lib/frr/frrinit.sh start")

    time.sleep(5)
    r1.cmdPrint('vtysh -c "show bgp summary"')
    r1.cmdPrint('vtysh -c "show segment-routing srv6 locator"')
    r1.cmdPrint('vtysh -c "show ipv6 route"')
    r1.cmdPrint('vtysh -c "show bgp ipv4 vpn summary"')
    r1.cmdPrint('vtysh -c "show ip bgp vrf all"')
    r1.cmdPrint('vtysh -c "show bgp segment-routing srv6"')

    # assert "100% packet loss" in host1.cmd('ping -c 1 10.0.3.2')
    assert "0% packet loss" in c11.cmd('ping -c 1 192.168.1.1')
    assert "0% packet loss" in c11.cmd('ping -c 1 192.168.2.1')
    assert "c11" in c11.cmd('curl 192.168.1.1')
    assert "c21" in c11.cmd('curl 192.168.2.1')

    loss_rate = net.ping(hosts=[c11, c21])

    for h in [r1, r2]:
        h.cmd("/usr/lib/frr/frrinit.sh stop")

    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
