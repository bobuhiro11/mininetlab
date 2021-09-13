#!/usr/bin/env python

from mininet.net import Mininet
from mininet.log import setLogLevel
from p4_mininet import P4Switch, P4Host
from future import standard_library
standard_library.install_aliases()

from subprocess import call  # noqa: E402

# Referring to P4's explanatory blog post as below:
# https://opennetworking.org/news-and-events/blog/getting-started-with-p4/
test_p4 = """
#include <core.p4>
#include <v1model.p4>

typedef bit<48> EthernetAddress;
typedef bit<32> IPv4Address;

header ethernet_t {
    EthernetAddress dst_addr;
    EthernetAddress src_addr;
    bit<16>         ether_type;
}

header ipv4_t {
    bit<4>      version;
    bit<4>      ihl;
    bit<8>      diffserv;
    bit<16>     total_len;
    bit<16>     identification;
    bit<3>      flags;
    bit<13>     frag_offset;
    bit<8>      ttl;
    bit<8>      protocol;
    bit<16>     hdr_checksum;
    IPv4Address src_addr;
    IPv4Address dst_addr;
}

struct headers_t {
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

struct metadata_t {
}

error {
    IPv4IncorrectVersion,
    IPv4OptionsNotSupported
}

parser my_parser(packet_in packet,
                out headers_t hd,
                inout metadata_t meta,
                inout standard_metadata_t standard_meta)
{
    state start {
        packet.extract(hd.ethernet);
        transition select(hd.ethernet.ether_type) {
            0x0800:  parse_ipv4;
            default: accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hd.ipv4);
        verify(hd.ipv4.version == 4w4, error.IPv4IncorrectVersion);
        verify(hd.ipv4.ihl == 4w5, error.IPv4OptionsNotSupported);
        transition accept;
    }
}

control my_deparser(packet_out packet,
                   in headers_t hdr)
{
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

control my_verify_checksum(inout headers_t hdr,
                         inout metadata_t meta)
{
    apply { }
}

control my_compute_checksum(inout headers_t hdr,
                          inout metadata_t meta)
{
    apply { }
}

control my_ingress(inout headers_t hdr,
                  inout metadata_t meta,
                  inout standard_metadata_t standard_metadata)
{
    bool dropped = false;

    action drop_action() {
        mark_to_drop(standard_metadata);
        dropped = true;
    }

    action to_port_action(bit<9> port) {
        // hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
        standard_metadata.egress_spec = port;
    }

    table ipv4_match {
        key = {
            hdr.ipv4.dst_addr: lpm;
        }
        actions = {
            drop_action;
            to_port_action;
        }
        size = 1024;
        default_action = drop_action;
    }

    apply {
        ipv4_match.apply();
        if (dropped) return;
    }
}

control my_egress(inout headers_t hdr,
                 inout metadata_t meta,
                 inout standard_metadata_t standard_metadata)
{
    apply { }
}

V1Switch(my_parser(),
         my_verify_checksum(),
         my_ingress(),
         my_egress(),
         my_compute_checksum(),
         my_deparser()) main;
"""


def run():
    setLogLevel('info')
    with open("mininetlab/test.p4", mode="w") as f:
        f.write(test_p4)
    call('p4c --target bmv2 --arch v1model --std p4-16 ' +
         'mininetlab/test.p4 -o mininetlab/',
         shell=True)

    net = Mininet(switch=P4Switch, host=P4Host)
    s1 = net.addSwitch('s1',
                       sw_path='/usr/bin/simple_switch',
                       json_path='mininetlab/test.json',
                       thrift_port=9090,
                       pcap_dump=False)
    h1 = net.addHost('h1', ip='192.168.0.1/24', mac='10:00:00:00:00:01')
    h2 = net.addHost('h2', ip='192.168.0.2/24', mac='10:00:00:00:00:02')
    net.addLink(s1, h1)
    net.addLink(s1, h2)
    net.start()

    h1.cmd('arp -s 192.168.0.2 10:00:00:00:00:02')
    h2.cmd('arp -s 192.168.0.1 10:00:00:00:00:01')

    s1.cmdPrint('echo "table_info ipv4_match" | simple_switch_CLI')
    s1.cmdPrint(
            'echo "table_add ipv4_match to_port_action 192.168.0.1/32 => 1" ' +
            '| simple_switch_CLI')
    s1.cmdPrint(
            'echo "table_add ipv4_match to_port_action 192.168.0.2/32 => 2" ' +
            '| simple_switch_CLI')
    s1.cmdPrint('echo "table_dump ipv4_match" | simple_switch_CLI')

    loss_rate = net.ping(hosts=[h1, h2])
    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
