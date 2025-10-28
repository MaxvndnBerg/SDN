from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.util import quietRun


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

        # -------- Hosts (IPv4) --------
        # VLAN10 (employee)
        hA1_emp = self.addHost('h1', ip='10.0.10.1/24')
        hB1_emp = self.addHost('h4', ip='10.0.10.2/24')

        # VLAN20 (guest)
        hA1_gst = self.addHost('h2', ip='10.0.20.1/24')
        hB2_gst = self.addHost('h5', ip='10.0.20.2/24')

        # VLAN30 (management)
        hA2_mng = self.addHost('h3', ip='10.0.30.1/24', mac='b2:be:ec:10:f8:d3')
        hB3_mng = self.addHost('h6', ip='10.0.30.2/24', mac='1e:f0:bf:48:c8:57')

        # (optioneel) management servers
        ctrlA = self.addHost('ctrlA', ip='10.0.100.1/24')
        ctrlB = self.addHost('ctrlB', ip='10.0.100.2/24')

        # -------- Links --------
        # Core <-> Access (A)
        self.addLink(a_core, a1)
        self.addLink(a_core, a2)

        # Core <-> Access (B)
        self.addLink(b_core, b1)
        self.addLink(b_core, b2)
        self.addLink(b_core, b3)

        # Darkfiber A <-> B
        self.addLink(a_core, b_core)

        # Hosts A
        self.addLink(hA1_emp, a1)
        self.addLink(hA1_gst, a1)
        self.addLink(hA2_mng, a2)
        
        # Hosts B
        self.addLink(hB1_emp, b1)
        self.addLink(hB2_gst, b2)
        self.addLink(hB3_mng, b3)

        # Controllers (optioneel)
        self.addLink(ctrlA, a_core)
        self.addLink(ctrlB, b_core)

        # Edge-router en ISP
        edgeA = self.addHost('edgeA', ip='10.0.30.254/24')
        isp0 = self.addHost('isp0', ip='203.0.113.1/28')

        # LAN naar VLAN30
        self.addLink(edgeA, a2)
        # WAN naar ISP
        self.addLink(edgeA, isp0)
        # LAN naar VLANS (trunk)
        self.addLink(edgeA, a_core)


def run():
    topo = SDNTopo()
    net = Mininet(topo=topo, switch=OVSSwitch, build=False, controller=None)

    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    net.build()
    net.start()

    isp0 = net.get('isp0')
    # een korte wacht kan helpen, maar 'replace' is meestal genoeg
    isp0.cmd('ip -6 route replace 2001:db8:10::/64 via 2001:db8:ffff::2')
    isp0.cmd('ip -6 route replace 2001:db8:20::/64 via 2001:db8:ffff::2')
    isp0.cmd('ip -6 route replace 2001:db8:30::/64 via 2001:db8:ffff::2')

    # Forceer OpenFlow13 en één controller
    for s in ['s1','s2','s3','s4','s5','s6','s7']:
        quietRun(f'ovs-vsctl del-controller {s}')
        quietRun(f'ovs-vsctl set-controller {s} tcp:127.0.0.1:6653')
        quietRun(f'ovs-vsctl set-fail-mode {s} secure')
        quietRun(f'ovs-vsctl set bridge {s} protocols=OpenFlow13')

    # -------- NAT + IPv6-routering (edgeA) --------
    edgeA = net.get('edgeA')
    isp0 = net.get('isp0')

    # ISP kant (IPv4 + IPv6)
    isp0.cmd('ip addr flush dev isp0-eth0')
    isp0.cmd('ip addr add 203.0.113.1/28 dev isp0-eth0')
    isp0.cmd('ip -6 addr add 2001:db8:ffff::1/64 dev isp0-eth0')
    isp0.cmd('ip link set isp0-eth0 up')
    isp0.cmd('ip -6 route add 2001:db8:10::/64 via 2001:db8:ffff::2')
    isp0.cmd('ip -6 route add 2001:db8:20::/64 via 2001:db8:ffff::2')
    isp0.cmd('ip -6 route add 2001:db8:30::/64 via 2001:db8:ffff::2')

    edgeA.cmd('ip addr flush dev edgeA-eth1')
    edgeA.cmd('ip addr add 203.0.113.2/28 dev edgeA-eth1')
    edgeA.cmd('ip -6 addr add 2001:db8:ffff::2/64 dev edgeA-eth1')
    edgeA.cmd('ip link set edgeA-eth1 up')
    edgeA.cmd('ip route add default via 203.0.113.1')
    edgeA.cmd('ip -6 route add default via 2001:db8:ffff::1')

    # VLAN-subinterfaces
    edgeA.cmd('ip link add link edgeA-eth2 name edgeA-eth2.10 type vlan id 10')
    edgeA.cmd('ip link add link edgeA-eth2 name edgeA-eth2.20 type vlan id 20')
    edgeA.cmd('ip link add link edgeA-eth2 name edgeA-eth2.30 type vlan id 30')

    edgeA.cmd('ip addr add 10.0.10.254/24 dev edgeA-eth2.10')
    edgeA.cmd('ip addr add 10.0.20.254/24 dev edgeA-eth2.20')
    edgeA.cmd('ip addr add 10.0.30.254/24 dev edgeA-eth2.30')

    edgeA.cmd('ip -6 addr add 2001:db8:10::1/64 dev edgeA-eth2.10')
    edgeA.cmd('ip -6 addr add 2001:db8:20::1/64 dev edgeA-eth2.20')
    edgeA.cmd('ip -6 addr add 2001:db8:30::1/64 dev edgeA-eth2.30')

    edgeA.cmd('ip link set edgeA-eth2 up')
    edgeA.cmd('ip link set edgeA-eth2.10 up')
    edgeA.cmd('ip link set edgeA-eth2.20 up')
    edgeA.cmd('ip link set edgeA-eth2.30 up')

    #Zet IPv6 forwarding HIER aan (nu bestaan de interfaces pas echt)
    edgeA.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')
    edgeA.cmd('sysctl -w net.ipv6.conf.edgeA-eth1.forwarding=1')
    edgeA.cmd('sysctl -w net.ipv6.conf.edgeA-eth2.forwarding=1')
    edgeA.cmd('sysctl -w net.ipv6.conf.edgeA-eth2.10.forwarding=1')
    edgeA.cmd('sysctl -w net.ipv6.conf.edgeA-eth2.20.forwarding=1')
    edgeA.cmd('sysctl -w net.ipv6.conf.edgeA-eth2.30.forwarding=1')

    # IP forwarding
    edgeA.cmd('sysctl -w net.ipv4.ip_forward=1')
    edgeA.cmd('sysctl -w net.ipv6.conf.all.forwarding=1')

    # -------- Stateful firewall --------
    edgeA.cmd('iptables -t nat -F')
    edgeA.cmd('iptables -F')
    edgeA.cmd('iptables -X')
    edgeA.cmd('ip6tables -F')
    edgeA.cmd('ip6tables -X')

    edgeA.cmd('iptables -P INPUT DROP')
    edgeA.cmd('iptables -P FORWARD DROP')
    edgeA.cmd('iptables -P OUTPUT ACCEPT')

    edgeA.cmd('ip6tables -P INPUT DROP')
    edgeA.cmd('ip6tables -P FORWARD DROP')
    edgeA.cmd('ip6tables -P OUTPUT ACCEPT')

    edgeA.cmd('iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    edgeA.cmd('iptables -A INPUT -i lo -j ACCEPT')
    edgeA.cmd('iptables -A INPUT -p icmp -j ACCEPT')

    edgeA.cmd('ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    edgeA.cmd('ip6tables -A INPUT -i lo -j ACCEPT')
    edgeA.cmd('ip6tables -A INPUT -p ipv6-icmp -j ACCEPT')
    edgeA.cmd('ip6tables -A FORWARD -p ipv6-icmp -j ACCEPT')

    # LAN ▒^f^r WAN (v4 + v6)
    for vid in ['10','20','30']:
        edgeA.cmd(f'iptables -A FORWARD -i edgeA-eth2.{vid} -o edgeA-eth1 -j ACCEPT')
        edgeA.cmd(f'ip6tables -A FORWARD -i edgeA-eth2.{vid} -o edgeA-eth1 -j ACCEPT')
    
    edgeA.cmd('ip6tables -A FORWARD -p ipv6-icmp -j ACCEPT')
    for vid in ['10','20','30']:
        edgeA.cmd(f'ip6tables -A FORWARD -i edgeA-eth1 -o edgeA-eth2.{vid} -p ipv6-icmp -j ACCEPT')
        
    # Retourverkeer toestaan
    edgeA.cmd('iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')
    edgeA.cmd('ip6tables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT')

    # Inter-VLAN blokkeren
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth2.10 -o edgeA-eth2.20 -j DROP')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth2.20 -o edgeA-eth2.10 -j DROP')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth2.30 -o edgeA-eth2.10 -j DROP')
    edgeA.cmd('iptables -A FORWARD -i edgeA-eth2.30 -o edgeA-eth2.20 -j DROP')

    edgeA.cmd('ip6tables -A FORWARD -i edgeA-eth2.10 -o edgeA-eth2.20 -j DROP')
    edgeA.cmd('ip6tables -A FORWARD -i edgeA-eth2.20 -o edgeA-eth2.10 -j DROP')
    edgeA.cmd('ip6tables -A FORWARD -i edgeA-eth2.30 -o edgeA-eth2.10 -j DROP')
    edgeA.cmd('ip6tables -A FORWARD -i edgeA-eth2.30 -o edgeA-eth2.20 -j DROP')

    # NAT voor IPv4
    edgeA.cmd('iptables -t nat -A POSTROUTING -o edgeA-eth1 -j MASQUERADE')

    # -------- Default gateways en IPv6 --------
    # VLAN10
    net.get('h1').cmd('ip route add default via 10.0.10.254')
    net.get('h4').cmd('ip route add default via 10.0.10.254')
    net.get('h1').cmd('ip -6 addr add 2001:db8:10::10/64 dev h1-eth0')
    net.get('h4').cmd('ip -6 addr add 2001:db8:10::11/64 dev h4-eth0')
    net.get('h1').cmd('ip -6 route add default via 2001:db8:10::1')
    net.get('h4').cmd('ip -6 route add default via 2001:db8:10::1')

    # VLAN20
    net.get('h2').cmd('ip route add default via 10.0.20.254')
    net.get('h5').cmd('ip route add default via 10.0.20.254')
    net.get('h2').cmd('ip -6 addr add 2001:db8:20::10/64 dev h2-eth0')
    net.get('h5').cmd('ip -6 addr add 2001:db8:20::11/64 dev h5-eth0')
    net.get('h2').cmd('ip -6 route add default via 2001:db8:20::1')
    net.get('h5').cmd('ip -6 route add default via 2001:db8:20::1')

    # VLAN30
    net.get('h3').cmd('ip route add default via 10.0.30.254')
    net.get('h6').cmd('ip route add default via 10.0.30.254')
    net.get('h3').cmd('ip -6 addr add 2001:db8:30::10/64 dev h3-eth0')
    net.get('h6').cmd('ip -6 addr add 2001:db8:30::11/64 dev h6-eth0')
    net.get('h3').cmd('ip -6 route add default via 2001:db8:30::1')
    net.get('h6').cmd('ip -6 route add default via 2001:db8:30::1')

    # Management servers
    net.get('ctrlA').cmd('ip addr add 10.0.100.10/24 dev ctrlA-eth0')
    net.get('ctrlB').cmd('ip addr add 10.0.100.11/24 dev ctrlB-eth0')

    isp0.cmd('ip addr add 8.8.8.8/32 dev isp0-eth0')

    print('*** IPv4/IPv6 routing + stateful firewall actief op edgeA')
    print('*** Test v4: h1 ping 8.8.8.8 | Test v6: h1 ping6 2001:db8:ffff::1')
    print('*** Guestisolatie: h2 ping h5 (zou moeten falen door ACL)')

    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()

