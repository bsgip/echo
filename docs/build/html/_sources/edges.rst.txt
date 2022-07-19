.. _Edges_ref:
*echo* Edges
======================
Edges represent a physical, lossless flow of a single commodity.
An edge is terminated on each end by connection to a port. Edges must begin and end on ports that have the same commodity type.

Edge constraint
---------------
Edges are used to apply a flow constraint. They do not have an optimisation variable associated with them.
If an edge connects ports :math:`x` and :math:`y`, which have variables :math:`p^x` and :math:`p^y`, then we can write the following edge constraint:

:math:`p^x + p^y = 0`.

This constraint enforces that any flow imported by :math:`x` must be exported by :math:`y`, and vice versa.