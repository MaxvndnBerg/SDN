from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.util import quietRun  # voor OVS-commando's


class SDNTopo(Topo):
    def build(self):
        # -------- Switches met vaste DPIDs (matchen met faucet.yaml) --------
        a_core = self.addSwitch('s1', dpid='0000000000000001')  # Core A
        b_core = self.addSwitch('s2', dpid='0000000000000002')  # Core B

        a1 = self.addSwitch('s3', dpid='0000000000000003')      # Access A1
        a2 = self.addSwitch('s4', dpid='0000000000000004')      # Access A2 (mgmt)
        b1 = self.addSwitch('s5', dpid='0000000000000005')      # Access B1
        b2 = self.addSwitch('s6', dpid='0000000000000006')      # Access B2 (guest)
        b3 = self.addSwitch('s7', dpid='0000000000000007')      # Access B3 (mgmt)

        # -------- Hosts (IPs) --------
        # VLAN10 (employee)
        hA1_emp = self.addHost('h1', ip='10.0.10.1/24')
        hB1_emp = self.addHost('h4', ip='10.0.10.2/24')

        # VLAN20 (guest)
        hA1_gst = self.addHost('h2', ip='10.0.20.1/24')
        hB2_gst = self.addHost('h5', ip='10.0.20.2/24')

        # VLAN30 (management) -- MET VASTE MACS (belangrijk voor ACL)
        hA2_mng = self.addHost('h3', ip='10.0.30.1/24', mac='b2:be:ec:10:f8:d3')
        hB3_mng = self.addHost('h6', ip='10.0.30.2/24', mac='1e:f0:bf:48:c8:57')

        # (optioneel) management servers
        ctrlA = self.addHost('ctrlA', ip='10.0.100.1/24')
        ctrlB = self.addHost('ctrlB', ip='10.0.100.2/24')

        # -------- Links (volgorde bepaalt poortnummers) --------
        # Core <-> Access (A)
        self.addLink(a_core, a1)   # s1-eth1 <-> s3-eth1 (trunk)
        self.addLink(a_core, a2)   # s1-eth2 <-> s4-eth1 (trunk)

        # Core <-> Access (B)
        self.addLink(b_core, b1)   # s2-eth1 <-> s5-eth1 (trunk)
        self.addLink(b_core, b2)   # s2-eth2 <-> s6-eth1 (trunk)
        self.addLink(b_core, b3)   # s2-eth3 <-> s7-eth1 (trunk)

        # Darkfiber A <-> B (trunk)
        self.addLink(a_core, b_core)  # s1-eth3 <-> s2-eth4

        # Hosts A
        self.addLink(hA1_emp, a1)  # h1-eth0 <-> s3-eth2 (employee)
        self.addLink(hA1_gst, a1)  # h2-eth0 <-> s3-eth3 (guest)
        self.addLink(hA2_mng, a2)  # h3-eth0 <-> s4-eth2 (management)

        # Hosts B
        self.addLink(hB1_emp, b1)  # h4-eth0 <-> s5-eth2 (employee)
        self.addLink(hB2_gst, b2)  # h5-eth0 <-> s6-eth2 (guest)
        self.addLink(hB3_mng, b3)  # h6-eth0 <-> s7-eth2 (management)

        # Controllers (als hosts in mgmt VLAN, optioneel)
        self.addLink(ctrlA, a_core)  # ctrlA-eth0 <-> s1-eth4
        self.addLink(ctrlB, b_core)  # ctrlB-eth0 <-> s2-eth5


def run():
    topo = SDNTopo()
    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        build=False,
        controller=None
    )

    # -- EÃ©n remote controller (Faucet) --
    c0 = net.addController('c0',
                           controller=RemoteController,
                           ip='127.0.0.1', port=6653)

    net.build()
    net.start()

    # -- Controllers & OpenFlow13 hard fixen na start (op alle bridges) --
    bridges = ['s1', 's2', 's3', 's4', 's5', 's6', 's7']
    for b in bridges:
        quietRun(f'ovs-vsctl del-controller {b}')
        quietRun(f'ovs-vsctl set-controller {b} tcp:127.0.0.1:6653')
        quietRun(f'ovs-vsctl set-fail-mode {b} secure')
        quietRun(f'ovs-vsctl set bridge {b} protocols=OpenFlow13')
    print('*** Controllers gefixeerd: alleen 127.0.0.1:6653 en OpenFlow13 op alle bridges.')

    # -- Info: bevestig vaste MACs voor ACL (h3 & h6) --
    mac_h3 = quietRun('cat /sys/class/net/h3-eth0/address').strip()
    mac_h6 = quietRun('cat /sys/class/net/h6-eth0/address').strip()
    print(f'*** MAC h3 = {mac_h3}  (verwacht: b2:be:ec:10:f8:d3)')
    print(f'*** MAC h6 = {mac_h6}  (verwacht: 1e:f0:bf:48:c8:57)')

    # -- Optioneel: oud port-policing voor guests (UITGESCHAKELD) --
    enable_port_policing = False  # laat False; je gebruikt nu ACL+meter in YAML
    if enable_port_policing:
        guest_ports = ['s3-eth3', 's6-eth2']  # h2 en h5
        rate_kbps = 10000
        burst_kb = 1000
        for intf in guest_ports:
            quietRun(f'ovs-vsctl set interface {intf} '
                     f'ingress_policing_rate={rate_kbps} '
                     f'ingress_policing_burst={burst_kb}')
            applied = quietRun(f'ovs-vsctl get interface {intf} ingress_policing_rate').strip()
            print(f'*** Guest rate limit (policing) op {intf}: {applied} kbps')

    print('*** Netwerk is gestart ***')
    print('*** Tip: test VLAN pings (h1<->h4, h2<->h5, h3<->h6). Voor guest throughput: iperf3 h5<-h2 ***')
    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()
