#!/usr/bin/env python

from mininet.net import Mininet
from mininet.log import setLogLevel

xdp_code = """
#include <linux/bpf.h>

#ifndef __section
# define __section(NAME) \
   __attribute__((section(NAME), used))
#endif

__section("prog")
int xdp_drop(struct xdp_md *ctx)
{
    return XDP_DROP;
}
"""


def run():
    setLogLevel('info')
    with open("mininetlab/xdp_code.c", mode="w") as f:
        f.write(xdp_code)

    net = Mininet()
    h1 = net.addHost('h1')
    h2 = net.addHost('h2')
    net.addLink(h1, h2)
    net.start()

    h1.cmdPrint('clang -O2 -Wall -target bpf -c mininetlab/xdp_code.c ' +
                '-o mininetlab/xdp_code.o')
    h1.cmdPrint('file mininetlab/xdp_code.o')
    h1.cmd('mount bpffs /sys/fs/bpf -t bpf')
    h1.cmd('ip link set dev h1-eth0 xdp obj mininetlab/xdp_code.o sec prog')

    # It is assumed to be positive that all packets are dropped
    loss_rate = 0 if net.ping(hosts=[h1, h2]) == 100 else 100

    h1.cmd('ip link set dev h1-eth0 xdp off')
    loss_rate += net.ping(hosts=[h1, h2])
    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
