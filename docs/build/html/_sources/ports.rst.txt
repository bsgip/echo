*echo* Port object
=======================
Ports terminate a network edge and represent the connection of an edge to a node.
Ports are associated with an individual commodity and represent the flow of the that commodity into or out of a node.

Port variables
----------------------
All ports have at least one variable, :math:`p_{x, t}` the port flow value. 

If the port needs to be split into a positive and negative component, we introduce the additional variables:

:math:`p_{x, t}^+`,  the positive component of the port flow

:math:`p_{x, t}^-`,  the negative component of the port flow

:math:`p_{x, t}^{*}`, a binary variable for indicating whether :math:`p^+` is non-zero.


The following three constraints are used to split the variable.

:math:`p_{x, t} &= p^+_{x, t} + p^-_{x, t}`
    
:math:`p^+_{x, t} &\leq p^*_{x, t} \cdot M`
    
:math:`p^-_{x, t} &\geq (p^*_{x, t} - 1) \cdot M`


Port validation
----------------------

What is intended to go here?