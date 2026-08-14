#!/usr/bin/env python

import struct
import time

from mininet.net import Mininet
from mininet.log import setLogLevel

COMMON_H = """
#ifndef XDP_MIRROR_COMMON_H
#define XDP_MIRROR_COMMON_H

struct five_tuple {
    __u32 saddr;
    __u32 daddr;
    __u16 sport;
    __u16 dport;
    __u8  proto;
} __attribute__((packed));

#endif
"""

FILTER_KERN_C = """
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/in.h>
#include <linux/ip.h>
#include <linux/udp.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#include "common.h"

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 8);
    __type(key, struct five_tuple);
    __type(value, __u8);
} mirror_targets SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_DEVMAP);
    __uint(max_entries, 2);
    __type(key, __u32);
    __type(value, struct bpf_devmap_val);
} tx_port SEC(".maps");

SEC("xdp")
int xdp_filter(struct xdp_md *ctx)
{
    void *data = (void *)(long)ctx->data;
    void *data_end = (void *)(long)ctx->data_end;
    struct ethhdr *eth = data;

    if ((void *)(eth + 1) > data_end)
        return XDP_DROP;
    if (eth->h_proto != bpf_htons(ETH_P_IP))
        return bpf_redirect_map(&tx_port, 0, 0);

    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end)
        return bpf_redirect_map(&tx_port, 0, 0);
    if (ip->protocol != IPPROTO_UDP)
        return bpf_redirect_map(&tx_port, 0, 0);

    struct udphdr *udp = (void *)((char *)ip + (ip->ihl * 4));
    if ((void *)(udp + 1) > data_end)
        return bpf_redirect_map(&tx_port, 0, 0);

    struct five_tuple key = {
        .saddr = ip->saddr,
        .daddr = ip->daddr,
        .sport = udp->source,
        .dport = udp->dest,
        .proto = ip->protocol,
    };

    if (bpf_map_lookup_elem(&mirror_targets, &key))
        return bpf_redirect_map(&tx_port, 0, BPF_F_BROADCAST);

    return bpf_redirect_map(&tx_port, 0, 0);
}

char _license[] SEC("license") = "GPL";
"""

MIRROR_KERN_C = """
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/in.h>
#include <linux/ip.h>
#include <linux/udp.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#define VXLAN_PORT 4789
#define VNI 100

struct vxlanhdr {
    __u8 flags;
    __u8 reserved1[3];
    __u8 vni[3];
    __u8 reserved2;
};

static __always_inline __u16 csum_fold(__u32 sum)
{
    sum = (sum & 0xffff) + (sum >> 16);
    sum = (sum & 0xffff) + (sum >> 16);
    return ~sum;
}

static __always_inline __u16 ip_csum(struct iphdr *ip)
{
    __u32 sum = 0;
    __u16 *p = (__u16 *)ip;
    int i;

    ip->check = 0;
#pragma clang loop unroll(full)
    for (i = 0; i < (int)(sizeof(*ip) / 2); i++)
        sum += p[i];
    return csum_fold(sum);
}

/* The "xdp_devmap/" prefix makes libbpf set expected_attach_type to
 * BPF_XDP_DEVMAP at load time; the kernel rejects attaching a program
 * to a devmap entry (__dev_map_alloc_node in devmap.c) unless that's
 * set, regardless of the program's actual behavior. */
SEC("xdp_devmap/mirror")
int xdp_mirror(struct xdp_md *ctx)
{
    int extra = (int)(sizeof(struct ethhdr) + sizeof(struct iphdr) +
                       sizeof(struct udphdr) + sizeof(struct vxlanhdr));

    if (bpf_xdp_adjust_head(ctx, -extra))
        return XDP_DROP;

    void *data = (void *)(long)ctx->data;
    void *data_end = (void *)(long)ctx->data_end;

    struct ethhdr *eth = data;
    struct iphdr *ip = (void *)(eth + 1);
    struct udphdr *udp = (void *)(ip + 1);
    struct vxlanhdr *vxlan = (void *)(udp + 1);

    if ((void *)(vxlan + 1) > data_end)
        return XDP_DROP;

    __builtin_memset(eth->h_dest, 0xff, ETH_ALEN);
    __builtin_memset(eth->h_source, 0x02, ETH_ALEN);
    eth->h_proto = bpf_htons(ETH_P_IP);

    __u16 payload_len = (__u16)((char *)data_end - (char *)ip);

    ip->version = 4;
    ip->ihl = 5;
    ip->tos = 0;
    ip->tot_len = bpf_htons(payload_len);
    ip->id = 0;
    ip->frag_off = 0;
    ip->ttl = 64;
    ip->protocol = IPPROTO_UDP;
    ip->saddr = bpf_htonl(0xC0000201);
    ip->daddr = bpf_htonl(0xC0000202);
    ip->check = ip_csum(ip);

    udp->source = bpf_htons(12345);
    udp->dest = bpf_htons(VXLAN_PORT);
    udp->len = bpf_htons((__u16)((char *)data_end - (char *)udp));
    udp->check = 0;

    vxlan->flags = 0x08;
    __builtin_memset(vxlan->reserved1, 0, sizeof(vxlan->reserved1));
    vxlan->vni[0] = (VNI >> 16) & 0xff;
    vxlan->vni[1] = (VNI >> 8) & 0xff;
    vxlan->vni[2] = VNI & 0xff;
    vxlan->reserved2 = 0;

    return XDP_PASS;
}

char _license[] SEC("license") = "GPL";
"""

PASS_KERN_C = """
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

struct {
    __uint(type, BPF_MAP_TYPE_DEVMAP);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct bpf_devmap_val);
} pass_tx_port SEC(".maps");

SEC("xdp")
int xdp_pass_fwd(struct xdp_md *ctx)
{
    return bpf_redirect_map(&pass_tx_port, 0, 0);
}

char _license[] SEC("license") = "GPL";
"""

# devmap/XDP_REDIRECT can only deliver a frame into a veth peer whose
# OWN device has an XDP program attached: that's what makes the
# kernel set up its NAPI/xdp_ring (see veth_open()/veth_enable_xdp()
# in drivers/net/veth.c), which the eventual ndo_xdp_xmit() requires
# as its delivery target. h1/h2/h3 have no program of their own, so
# every redirect from gw toward them was silently dropped -- no
# counter, no error, the frame just never arrives. A trivial
# pass-through program on each host interface is enough to fix it.
HOSTPASS_KERN_C = """
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

SEC("xdp")
int xdp_passthrough(struct xdp_md *ctx)
{
    return XDP_PASS;
}

char _license[] SEC("license") = "GPL";
"""

# bpftool's CLI has no syntax for setting a devmap entry's attached-program
# field: struct bpf_devmap_val.bpf_prog.fd expects a *live fd* in the
# calling process, not a persisted prog id, and bpftool's value parser only
# special-cases that for map-of-maps/map-of-progs, never for devmap. So we
# do the two syscalls (bpf_obj_get + bpf_map_update_elem) ourselves here.
SET_DEVMAP_PROG_C = """
#include <bpf/bpf.h>
#include <linux/bpf.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    if (argc < 4) {
        fprintf(stderr,
                "usage: %s <devmap_pin> <key> <ifindex> [prog_pin]\\n",
                argv[0]);
        return 1;
    }

    int map_fd = bpf_obj_get(argv[1]);
    if (map_fd < 0) {
        fprintf(stderr, "bpf_obj_get(%s) failed: %d\\n", argv[1], map_fd);
        return 1;
    }

    __u32 key = strtoul(argv[2], NULL, 0);
    struct bpf_devmap_val val = { .ifindex = strtoul(argv[3], NULL, 0) };

    if (argc >= 5) {
        int prog_fd = bpf_obj_get(argv[4]);
        if (prog_fd < 0) {
            fprintf(stderr, "bpf_obj_get(%s) failed: %d\\n", argv[4],
                    prog_fd);
            return 1;
        }
        val.bpf_prog.fd = prog_fd;
    }

    int err = bpf_map_update_elem(map_fd, &key, &val, 0);
    if (err) {
        fprintf(stderr, "bpf_map_update_elem failed: %d\\n", err);
        return 1;
    }
    return 0;
}
"""

SOURCES = (
    ('common.h', COMMON_H),
    ('filter.c', FILTER_KERN_C),
    ('mirror.c', MIRROR_KERN_C),
    ('pass.c', PASS_KERN_C),
    ('hostpass.c', HOSTPASS_KERN_C),
)

NATIVE_SOURCES = (
    ('set_devmap_prog.c', SET_DEVMAP_PROG_C),
)

SET_DEVMAP_PROG_BIN = 'mininetlab/set_devmap_prog'

BPF_DIR = '/sys/fs/bpf/xdp_mirror'

# The 5-tuple that gets mirrored to h3, VXLAN-encapsulated. A second flow
# (OTHER_FLOW) exercises the non-matching path: it must reach h2 untouched
# and must never show up at h3.
#
# Ports are picked with no entry in tshark's port->dissector table
# (checked via `tshark -G decodes`) -- 9999/5555/6666 would collide with
# registered dissectors (tplink-smarthome, sigcomp), see the h2_out/
# h3_out comment below for why that matters.
FLOW = dict(saddr='10.0.0.1', daddr='10.0.0.2', sport=54321, dport=55501,
            proto=17)
OTHER_FLOW = dict(saddr='10.0.0.1', daddr='10.0.0.2', sport=54321,
                  dport=55502, proto=17)


def ip_to_int(addr):
    a, b, c, d = (int(x) for x in addr.split('.'))
    return (a << 24) | (b << 16) | (c << 8) | d


def as_bpftool_bytes(data):
    return ' '.join(str(b) for b in bytearray(data))


def five_tuple_key_bytes(flow):
    return struct.pack(
        '!IIHHB', ip_to_int(flow['saddr']), ip_to_int(flow['daddr']),
        flow['sport'], flow['dport'], flow['proto'])


def ifindex_of(host, iface):
    return int(host.cmd('cat /sys/class/net/%s/ifindex' % iface).strip())


def ifindex_bytes(idx):
    return as_bpftool_bytes(struct.pack('<I', idx))


def mac_of(host, iface):
    return host.cmd('cat /sys/class/net/%s/address' % iface).strip()


def write_sources():
    for name, content in SOURCES + NATIVE_SOURCES:
        with open('mininetlab/%s' % name, mode='w') as f:
            f.write(content)


def compile_sources(gw):
    for name, _ in SOURCES:
        if not name.endswith('.c'):
            continue
        obj = name[:-2] + '.o'
        gw.cmdPrint(
            'clang -O2 -Wall -g -target bpf -c mininetlab/%s '
            '-o mininetlab/%s -I mininetlab '
            '-idirafter /usr/include/x86_64-linux-gnu' % (name, obj))


def compile_native(gw):
    for name, _ in NATIVE_SOURCES:
        bin_path = 'mininetlab/%s' % name[:-2]
        gw.cmdPrint('cc -O2 -Wall -g mininetlab/%s -o %s -lbpf'
                    % (name, bin_path))


def load_programs(gw):
    gw.cmd('mount bpffs /sys/fs/bpf -t bpf')
    gw.cmd('rm -rf %s' % BPF_DIR)
    gw.cmd('mkdir -p %s' % BPF_DIR)

    gw.cmdPrint('bpftool prog load mininetlab/mirror.o '
                '%s/mirror_prog' % BPF_DIR)
    gw.cmdPrint('bpftool prog load mininetlab/filter.o '
                '%s/filter_prog pinmaps %s/filter_maps' % (BPF_DIR, BPF_DIR))
    gw.cmdPrint('bpftool prog load mininetlab/pass.o '
                '%s/pass_prog pinmaps %s/pass_maps' % (BPF_DIR, BPF_DIR))


def configure_maps(gw):
    tx_port = '%s/filter_maps/tx_port' % BPF_DIR
    pass_tx_port = '%s/pass_maps/pass_tx_port' % BPF_DIR
    mirror_targets = '%s/filter_maps/mirror_targets' % BPF_DIR
    mirror_prog = '%s/mirror_prog' % BPF_DIR

    h2_idx = ifindex_of(gw, 'gw-eth1')
    h3_idx = ifindex_of(gw, 'gw-eth2')
    h1_idx = ifindex_of(gw, 'gw-eth0')

    gw.cmdPrint('bpftool map update pinned %s key 0 0 0 0 '
                'value %s 0 0 0 0' % (tx_port, ifindex_bytes(h2_idx)))
    gw.cmdPrint('%s %s 1 %d %s'
                % (SET_DEVMAP_PROG_BIN, tx_port, h3_idx, mirror_prog))
    gw.cmdPrint('bpftool map update pinned %s key 0 0 0 0 '
                'value %s 0 0 0 0' % (pass_tx_port, ifindex_bytes(h1_idx)))
    gw.cmdPrint('bpftool map update pinned %s key %s value 1'
                % (mirror_targets, as_bpftool_bytes(
                    five_tuple_key_bytes(FLOW))))


def attach_programs(gw):
    gw.cmdPrint('ip -force link set dev gw-eth0 xdp pinned '
                '%s/filter_prog' % BPF_DIR)
    gw.cmdPrint('ip -force link set dev gw-eth1 xdp pinned '
                '%s/pass_prog' % BPF_DIR)


def attach_host_passthrough(hosts):
    for host, intf in hosts:
        # Without this, "ip link set xdp obj" still reports success but
        # the attach silently doesn't take effect (redirected frames
        # never arrive) -- confirmed by testing without it.
        host.cmdPrint('mount bpffs /sys/fs/bpf -t bpf')
        host.cmdPrint('ip -force link set dev %s xdp obj '
                      'mininetlab/hostpass.o sec xdp' % intf)


def send_udp(h1, h2_mac, h1_mac, flow):
    h1.cmd('''
        python3 -c "from scapy.all import *; \
            pkt=Ether(dst='%s',src='%s') \
                /IP(src='%s',dst='%s') \
                /UDP(sport=%d,dport=%d)/Raw(load='mirror-test'); \
            sendp(pkt, iface='h1-eth0')"
''' % (h2_mac, h1_mac, flow['saddr'], flow['daddr'], flow['sport'],
       flow['dport']))


def run():
    setLogLevel('info')
    write_sources()

    net = Mininet()
    h1 = net.addHost('h1')
    h2 = net.addHost('h2')
    h3 = net.addHost('h3')
    gw = net.addHost('gw')

    # gw must be the first argument on every addLink() call here: with
    # a host-to-host link (no switch) and the *non-gw* node passed
    # first, that link's carrier can come up permanently one-sided
    # (NO-CARRIER on gw's end, UP on the peer's), independent of any
    # BPF/XDP program -- reproduced with plain net.addLink(h1, gw) as
    # the first link, before any clang/bpftool/attach step runs.
    net.addLink(gw, h1)
    net.addLink(gw, h2)
    net.addLink(gw, h3)

    net.start()

    compile_sources(gw)
    compile_native(gw)
    load_programs(gw)
    configure_maps(gw)
    attach_programs(gw)
    attach_host_passthrough(
        [(h1, 'h1-eth0'), (h2, 'h2-eth0'), (h3, 'h3-eth0')])

    loss = net.ping(hosts=[h1, h2])

    h2_mac = mac_of(h2, 'h2-eth0')
    h1_mac = mac_of(h1, 'h1-eth0')

    h2.cmd('tcpdump -i h2-eth0 -w /tmp/h2.pcap udp &')
    h3.cmd('tcpdump -i h3-eth0 -w /tmp/h3.pcap udp &')
    time.sleep(2)

    send_udp(h1, h2_mac, h1_mac, FLOW)
    send_udp(h1, h2_mac, h1_mac, OTHER_FLOW)
    time.sleep(3)

    h2.cmd('pkill tcpdump')
    h3.cmd('pkill tcpdump')
    time.sleep(2)
    h2.cmd('sync')
    h3.cmd('sync')

    # -T fields -e udp.dstport prints the raw destination port number(s)
    # of every UDP layer in a frame (one per layer, comma-separated when
    # a frame has more than one, e.g. an outer VXLAN UDP header plus the
    # tunnelled inner UDP header), independent of which dissector tshark
    # picks for the payload. Matching against tshark's default summary
    # text instead is not reliable: FLOW/OTHER_FLOW use sport=9999, which
    # collides with the well-known port for the TP-Link Smart Home
    # dissector, so tshark decodes the payload as that protocol instead
    # of showing a plain "srcport -> dstport" summary -- on runners where
    # that dissector happens to be present, dstport then never appears
    # as text at all, even though the packet is exactly as expected.
    h2_out = h2.cmd(
        'tshark -r /tmp/h2.pcap -Y udp -T fields -e udp.dstport')
    h3_out = h3.cmd(
        'tshark -r /tmp/h3.pcap -Y vxlan -T fields '
        '-e udp.dstport')
    h2_flow_count = len(h2.cmd(
        'tshark -r /tmp/h2.pcap -Y "udp.port==%d"'
        % FLOW['dport']).strip().splitlines())
    h3_flow_count = len(h3.cmd(
        'tshark -r /tmp/h3.pcap -Y vxlan').strip().splitlines())

    checks = [
        str(FLOW['dport']) in h2_out,
        str(OTHER_FLOW['dport']) in h2_out,
        str(FLOW['dport']) in h3_out,
        str(OTHER_FLOW['dport']) not in h3_out,
        h2_flow_count == h3_flow_count,
        h2_flow_count > 0,
    ]

    h2.cmd('rm -f /tmp/h2.pcap')
    h3.cmd('rm -f /tmp/h3.pcap')

    net.stop()

    return loss + (0.0 if all(checks) else 100.0)


if __name__ == '__main__':
    run()
