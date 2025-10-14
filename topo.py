from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel


class SDNTopo(Topo):
    def build(self):
        # Core switches (centrale patchkasten)
        a_core = self.addSwitch('s1')  # Gebouw A core
        b_core = self.addSwitch('s2')  # Gebouw B core


        # Verdieping switches Gebouw A
        a1 = self.addSwitch('s3')  # A1 switch (VLAN 10/20/30)
        a2 = self.addSwitch('s4')  # A2 switch (VLAN 10/20/30)


        # Verdieping switches Gebouw B
        b1 = self.addSwitch('s5')
        b2 = self.addSwitch('s6')
        b3 = self.addSwitch('s7')


        # Hosts Gebouw A (voorbeeld: 1 host per VLAN per verdieping)
        hA1_emp = self.addHost('h1', ip='10.0.10.1/24')  # VLAN10
        hA1_gst = self.addHost('h2', ip='10.0.20.1/24')  # VLAN20
        hA2_mng = self.addHost('h3', ip='10.0.30.1/24')  # VLAN30


        # Hosts Gebouw B
        hB1_emp = self.addHost('h4', ip='10.0.10.2/24')
        hB2_gst = self.addHost('h5', ip='10.0.20.2/24')
        hB3_mng = self.addHost('h6', ip='10.0.30.2/24')


        # Servers voor controllers
        ctrlA = self.addHost('ctrlA', ip='10.0.100.1/24')  # Faucet in Gebouw A
        ctrlB = self.addHost('ctrlB', ip='10.0.100.2/24')  # Backup in Gebouw B


        # Links tussen core en verdieping switches (Gebouw A)
        self.addLink(a_core, a1)
        self.addLink(a_core, a2)


        # Links tussen core en verdieping switches (Gebouw B)
        self.addLink(b_core, b1)
        self.addLink(b_core, b2)
        self.addLink(b_core, b3)


        # Darkfiber link (core naar core)
        self.addLink(a_core, b_core)


        # Host connecties Gebouw A
        self.addLink(hA1_emp, a1)
        self.addLink(hA1_gst, a1)
        self.addLink(hA2_mng, a2)


        # Host connecties Gebouw B
        self.addLink(hB1_emp, b1)
        self.addLink(hB2_gst, b2)
        self.addLink(hB3_mng, b3)


        # Controllers (via core)
        self.addLink(ctrlA, a_core)
        self.addLink(ctrlB, b_core)




def run():
    topo = SDNTopo()
    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        build=False,
        controller=None
    )


    # Voeg RemoteControllers toe (Faucet draait los in Gebouw A/B)
    c0 = net.addController('c0',
                           controller=RemoteController,
                           ip='127.0.0.1', port=6653)  # faucet.yaml Gebouw A
    c1 = net.addController('c1',
                           controller=RemoteController,
                           ip='127.0.0.1', port=6654)  # backup in B (optioneel)


    net.build()
    net.start()


    print("*** Netwerk is gestart ***")
    CLI(net)
    net.stop()




if __name__ == '__main__':
    setLogLevel('info')
    run()
