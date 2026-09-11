User Guide
==============

Design Philosophy
---------------------
Echo models multi-commodity energy systems as networks comprised of **edges**, **ports**,
and **nodes**.
Nodes represent physical assets of the energy network (at different levels of aggregation) and logical interconnection points. Each Node has at least one Port.
Port represents the flow of a single commodity into or out of a Node. Nodes that have multiple Ports also define a Transformation of the commodity between their Ports.
Edges represents physical flows of a single commodity between two network Nodes (assets). Ports also represent the connection of an Edge to a Node.

.. image::
   images/echo_graph.jpeg


Creating a model
---------------------------

Creating a model using echo_builder (recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Creating a model from scratch
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Saving and loading models
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Echo graphs can be saved and loaded using either the `json <https://docs.python.org/3/library/json.html#module-json>`_ module or the `pickle <https://docs.python.org/3/library/pickle.html>`_ module (python-specific).

**Pickle**

Pickling converts the network object to a byte stream, which can be saved and re-loaded at a later time.

An example of pickling an echo graph is shown below:

.. code-block::

    system = OptGraph()
    # Assume we add some things to the graph here....
    file = open('my_network', 'wb')  # create a file in write mode
    pickle.dump(system, file)  # pickle to that file
    file.close()


An example of unpickling an echo graph is shown below:

.. code-block::

    # load the graph from the file in read mode
    file = open('my_network', 'rb')
    loaded_system = pickle.load(file)
    file.close()


.. note::
    The optimiser itself cannot be pickled (yet) - it requires all class functions to be defined at the top level, and most constraint functions are not.


**JSON**

TBC - can't convert graph to json yet because of issue with serializing tuples as dict keys, and we use tuples as dict keys when defining edges as well as initial values
