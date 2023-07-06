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
router bgp {asnum}
 bgp router-id  {router_id}
 bgp bestpath as-path multipath-relax
 no bgp network import-check
 no bpp ebgp-requires-policy
 bgp default ipv6-unicast
 bgp default ipv4-vpn
 neighbor {name}-eth0 interface remote-as external
 neighbor {name}-eth0 interface capability extended-nexthop
 !
 segment-routing srv6
   locator default
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
                     locator='2001:db8:1:1::/64', gw_in_vrf='192.168.1.254/24')
    r2 = net.addHost('r2', privateDirs=privateDirs, asnum=65002, router_id='203.0.113.2',
                     locator='2001:db8:2:2::/64', gw_in_vrf='192.168.2.254/24')
    # Tenant #10.
    c11 = net.addHost('c11', ip='192.168.1.1/24', privateDirs=privateDirs)
    c21 = net.addHost('c21', ip='192.168.2.1/24', privateDirs=privateDirs)

    net.addLink(r1, r2)
    net.addLink(r1, c11)
    net.addLink(r2, c21)

    net.start()

    # Setup Underlay.
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

        # Add SID anchor?
        if r.name == 'r1':
            r.cmd('ip -6 addr add 2001:db8:1:1::1/128 dev lo')
        else:
            r.cmd('ip -6 addr add 2001:db8:2:2::1/128 dev lo')

        # Add VRF 10.
        r.cmd('ip link add vrf10 type vrf table 10')
        r.cmd('ip link set vrf10 up')
        r.cmd('ip link set {}-eth1 master vrf10'.format(r.name))
        r.cmd('ip link set {}-eth1 up'.format(r.name))
        r.cmd('ip addr add {} dev {}-eth1'.format(r.params['gw_in_vrf'], r.name))

    for r in [r1, r2]:
        put_file(r, "/etc/frr/daemons", daemons)
        put_file(r, "/etc/frr/vtysh.conf", vtysh_conf)
        put_file(r, "/etc/frr/frr.conf", frr_conf, name=r.name,
                 router_id=r.params["router_id"], asnum=r.params['asnum'],
                 locator=r.params["locator"])
        r.cmd("/usr/lib/frr/frrinit.sh start")

    # Setup Overlay.
    c11.cmd('ip route add default via 192.168.1.254')
    c21.cmd('ip route add default via 192.168.2.254')
    for c in [c11, c21]:
        put_file(c, "/tmp/index.html", c.name + "\n")
        c.cmd("cd /tmp; python3 -m http.server 80 >/dev/null 2>&1 &")

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
