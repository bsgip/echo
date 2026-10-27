Defining Optimisation Constraints
===================================
Optimisation constraints are typically defined on either nodes or ports. There is a range of pre-defined ports and nodes that come with appropriate pre-defined constraints, but sometimes custom constraints are required.

Node constraints
------------------
As discussed in :ref:`*echo* Nodes`, nodes can have pre-built constraints (e.g., a Tellegen constraint), or they can have custom constraints that are defined internally. To allow the user to define generic linear node constraints, echo has a ``Transform`` class that is designed specifically for this purpose. It is a convenient and extendable way of defining arbitrary linear node constraints, where each constraint consists of weighted port variables.

Generic Linear Node Constraints
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Each ``Transform`` object is designed to hold a single linear constraint expression. It has a RHS (right-hand-side) and LHS (left-hand-side) expression, and the user can add as many linearly weighted *terms* to each side of the constraint expression. Each term in a transformation has the following parameters:

* ``variable``: the name of the variable
* ``weight``: a float, or an array of floats that will be used to weight the variable

Once a custom transform has been built, it is simply added to a node. This automatically sets ``NodeRule=NodeRule.Transform`` so that the echo optimiser builds the correct constraint.

To create a custom transform:

.. code-block::

    # Create a node with some ports
    n = Node()
    n.add_port(ElectricalPort(), 'grid')
    n.add_port(CarbonSource(), 'emissions')

    # Initialise a transform object
    lhs_terms = [TransformTerm(var=self.ports['emissions'].port_name, weight=ArrayWrap(1))]
    t = Transform(lhs_terms=lhs_terms)
    n.add_transformation(t)

An arbitrary number of these transformations can be added to a node. Each transform will get 'unpacked' into a single pyomo constraint when the optimiser is initialised. The function that unpacks any transformation is shown below for completeness:

.. code-block::

            def transform(model, p, t):  # Generic transformation node
            def unpack_transform(x):
                expr = 0
                for term in x:
                    var = term['var']
                    expr += getattr(model, var)[p, t] * weight[p, t]
                return expr

            rhs = unpack_transform(current_transform.rhs)
            lhs = unpack_transform(current_transform.lhs)
            return lhs == rhs


.. note::
    Be careful to check the signs when defining a Transform.  The signs used in constructing the transform are consistent with any signs that may be implicit in the creation of the ports themselves. In the above example, the ``CarbonSource`` port is export only, so we know that this port variable ``self.ports['emissions'].port_name`` must be negative. If we had defined the weight on the grid variable as -0.6 instead of 0.6, this would have constrained the carbon port to be positive, (since ``self.ports['grid'].neg`` is negative), and the optimisation would be infeasible.


Advanced use
------------------

Writing custom constraints outside of the optimiser
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
For advanced users, custom constraints can also be written directly using pyomo modules. These constraints can then be added directly to the pyomo model.
An example of how this might be done in code is shown below. First, we define an example network:

.. code-block::

    system = OptimisationGraph()

    grid = FlexNode(node_name='grid', port_name='grid', port_unit=Units.KW)

    battery = Battery(node_name='battery',
                      port_name='battery',
                      max_capacity=10,
                      depth_of_discharge_limit=0,
                      charging_power_limit=2.0,
                      discharging_power_limit=-2.0,
                      charging_efficiency=1,
                      discharging_efficiency=1,
                      initial_state_of_charge=0.0)

    load = Load(node_name='load',
                port_name='load',
                port_unit=Units.KW,
                profile=[2] * time_periods)

    site = TellegenNode()
    site.add_electrical_ports_from_list(['cp', 'load', 'battery'])

    system.add_node_obj([grid, battery, load, site])

    system.connect_ports_and_create_edge(grid.ports['grid'], site.ports['cp'])
    system.connect_ports_and_create_edge(battery.ports['battery'], site.ports['battery'])
    system.connect_ports_and_create_edge(load.ports['load'], site.ports['load'])

    throughput_cost = ThroughputCost(component=battery.ports['battery'], rate=0.0001)
    objective_set = ObjectiveSet(objective_list=[throughput_cost])

    optimiser = EchoOptimiser(
        interval_duration=interval_duration,
        number_of_intervals=time_periods,
        number_of_expansion_intervals=expansion_periods,
        discount_rate=0,
        ES=system,
        objective_set=objective_set
    )


This will build the echo graph, initialise the optimiser, and build the pyomo model. Now that the pyomo model has been built, we can simple add custom constraints to it, as shown below:

.. code-block::

    import pyomo.environ as en
    # Write a constraint rule
    # The rule must take the pyomo model, and the two indices (expansion and time intervals) as arguments.
    def constraint_rule(model, p, t):
        return getattr(model, grid_node.ports['downstream'].port_name)[p, t] <= 10

    constraint_name = 'max_import_constraint_' + grid_node.node_name
    setattr(model, constraint_name, en.Constraint(model.Expansion, model.Time, rule=constraint_rule))

After defining this custom constraint, and adding it to the pyomo model, you can optimise:

.. code-block::

    optimiser.optimise()

.. note::
    Mistakes are easy to make when writing custom rules, so make sure to:

    * use the correct variable names when retrieving a variable using ``getattr(model, variable_name)``.
    * index the variables correctly in the constraint rule. Most variables are indexed by expansion period (p) and time interval (t), but some are only indexed by one, or are not indexed at all.
    * use a unique constraint name. If the name matches an existing constraint, the original constraint will be overwritten.
    * pass ``model.Expansion`` and ``model.Time`` in the same order as the order they are defined and used in the constraint rule.
    * make sure sign conventions are consistent, otherwise the optimisation will be infeasible.

