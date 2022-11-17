from echo import objectives
import echo.echo_models as models
import echo.echo_thermal_models as thermal_models
import echo.echo_builder as builder
import echo.configuration as config
import echo.echo_optimiser as optimiser
import echo.utils as utils
import pyomo.environ as en



class MultiCommodityTellegenNode(models.Node):
    """
    A node with ports that have multiple commodities.
    A tellegen constraint is applied per commodity.
    """
    node_rule = models.NodeRule.Custom
    def apply_node_constraints(self, model):
        # todo avoid repeating the below
        def reliability(model, p, t):  # Tellegen node rule
            a = 0
            for port in commodity_ports:
                b = getattr(model, port.port_name)
                a += b[p, t]
            return a == 0
        commodities = dict()
        for p in self.ports.values():
            if commodities.get(p.units) is None:
                commodities[p.units] = []
                commodities[p.units].append(p)
            else:
                commodities[p.units].append(p)
        for ctype, commodity_ports in commodities.items():
            setattr(model, 'node_con_' + str(ctype) + self.node_name, en.Constraint(model.Expansion, model.Time, rule=reliability))


class MultiCommodityTellegenNodeManual(MultiCommodityTellegenNode):
    """ Specify subgroups of Ports to which Tellegen constraint appies"""
    tellegen_ports_dict: dict = None
    if tellegen_ports_dict:
        def apply_node_constraints(self, model):
            def reliability(model, p, t):
                a = 0
                for port in tellegen_ports:
                    b = getattr(model, port.port_name)
                    a += b[p, t]
                    return a == 0
            for k, v in self.tellegen_ports_dict.items():
                tellegen_ports = [self.ports.get(i) for i in v]
                setattr(model, 'node_con_' + str(k) + self.node_name, en.Constraint(model.Expansion, model.Time, rule=reliability))
