#!/usr/bin/env python

from mininet.net import Mininet


def run():
    net = Mininet()

    h1 = net.addHost('h1', ip='192.168.0.1/24')
    h2 = net.addHost('h2', ip='192.168.0.2/24')

    net.addLink(h1, h2)

    net.start()
    loss_rate = net.pingAll()
    net.stop()
    return loss_rate


if __name__ == '__main__':
    run()
