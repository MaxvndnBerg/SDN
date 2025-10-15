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

 # -------- Edge-router en ISP-simulatie --------
        edgeA = self.addHost('edgeA', ip='10.0.30.254/24')  # LAN-zijde (in VLAN30)
        isp0 = self.addHost('isp0', ip='203.0.113.1/28')    # WAN-simulatie

        # LAN naar VLAN30 (via A2-switch)
        self.addLink(edgeA, a2)      # edgeA-eth0 <-> s4-eth3 (faucet: native_vlan vlan30)
        # WAN naar ISP (buiten Faucet)
        self.addLink(edgeA, isp0)    # edgeA-eth1 <-> isp0-eth0 (rechtstreeks)
        # LAN naar VLANS
        self.addLink(edgeA, a_core) # edgeA-eth2 <-> s1-eth5 (trunk voor VLAN10/20/30)


def run():
    topo = SDNTopo()
    net = Mininet(topo=topo, switch=OVSSwitch, build=False, controller=None)

    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    net.build()
    net.start()

    # Forceer OpenFlow13 en één controller
    for s in ['s1','s2','s3','s4','s5','s6','s7']:
        quietRun(f'ovs-vsctl del-controller {s}')
        quietRun(f'ovs-vsctl set-controller {s} tcp:127.0.0.1:6653')
        quietRun(f'ovs-vsctl set-fail-mode {s} secure')
        quietRun(f'ovs-vsctl set bridge {s} protocols=OpenFlow13')

    # -------- NAT configureren (edgeA als router) --------
    edgeA = net.get('edgeA')
    isp0 = net.get('isp0')

    # Publieke kant (ISP simulatie)
    isp0.cmd('ip addr flush dev isp0-eth0')
    isp0.cmd('ip addr add 203.0.113.1/28 dev isp0-eth0')
    isp0.cmd('ip link set isp0-eth0 up')

    edgeA.cmd('ip addr flush dev edgeA-eth1')
    edgeA.cmd('ip addr add 203.0.113.2/28 dev edgeA-eth1')
    edgeA.cmd('ip link set edgeA-eth1 up')
    edgeA.cmd('ip route add default via 203.0.113.1')

    # Interne kant (VLAN’s 10/20/30)
    edgeA.cmd('ip link add link edgeA-eth2 name edgeA-eth2.10 type vlan id 10')
    edgeA.cmd('ip link add link edgeA-eth2 name edgeA-eth2.20 type vlan id 20')
    edgeA.cmd('ip link add link edgeA-eth2 name edgeA-eth2.30 type vlan id 30')
    edgeA.cmd('ip addr add 10.0.10.254/24 dev edgeA-eth2.10')
    edgeA.cmd('ip addr add 10.0.20.254/24 dev edgeA-eth2.20')
    edgeA.cmd('ip addr add 10.0.30.254/24 dev edgeA-eth2.30')
    edgeA.cmd('ip link set edgeA-eth2 up')
    edgeA.cmd('ip link set edgeA-eth2.10 up')
    edgeA.cmd('ip link set edgeA-eth2.20 up')
    edgeA.cmd('ip link set edgeA-eth2.30 up')

    # IP forwarding + iptables NAT
    edgeA.cmd('sysctl -w net.ipv4.ip_forward=1')
    edgeA.cmd('iptables -t nat -F')
    edgeA.cmd('iptables -F')
    edgeA.cmd('iptables -P FORWARD DROP')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth1 -o edgeA-eth2.10 -m state --state RELATED,ESTABLISHED -j ACCEPT')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth1 -o edgeA-eth2.20 -m state --state RELATED,ESTABLISHED -j ACCEPT')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth1 -o edgeA-eth2.30 -m state --state RELATED,ESTABLISHED -j ACCEPT')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth2.10 -o edgeA-eth1 -j ACCEPT')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth2.20 -o edgeA-eth1 -j ACCEPT')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth2.30 -o edgeA-eth1 -j ACCEPT')
    edgeA.cmd('iptables -t nat -A POSTROUTING -o edgeA-eth1 -j MASQUERADE')

    # Default gateways per VLAN
    net.get('h1').cmd('ip route add default via 10.0.10.254')
    net.get('h4').cmd('ip route add default via 10.0.10.254')
    net.get('h2').cmd('ip route add default via 10.0.20.254')
    net.get('h5').cmd('ip route add default via 10.0.20.254')
    net.get('h3').cmd('ip route add default via 10.0.30.254')
    net.get('h6').cmd('ip route add default via 10.0.30.254')

    # “Internet”-adres (8.8.8.8) simuleren op ISP
    isp0.cmd('ip addr add 8.8.8.8/32 dev isp0-eth0')

    print('*** NAT actief: edgeA gateways 10.0.x.254 en WAN 203.0.113.2/28 via 203.0.113.1')
    print('*** Test: h1 ping 203.0.113.1  |  h1 ping 8.8.8.8  |  edgeA iptables -t nat -L -v')

    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()
