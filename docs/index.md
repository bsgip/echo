---
title: echo - energy and commodity holistic optimiser
---
#

<figure markdown="span">
  ![echo logo](assets/images/echo.png){ width="400" }
  
<figcaption>The Energy and Commodity Holistic Optimiser</figcaption>
</figure>

---

**Documentation**: [https://bsgip.github.io/echo](https://bsgip.github.io/echo)

**Source Code**: [https://github.com/bsgip/echo](https://github.com/bsgip/echo)

---


Echo is a multi-commodity energy flow solver/optimiser. Echo combines detailed energy network modelling with interfaces to industrial-strength [solvers](solvers.md).

Echo is one component in a powerful collection of multi-commodity energy modelling software called [Eris](#eris).

!!! tip

    Although it is possible to model complex energy systems directly with Echo, it was designed to be a relatively low-level toolbox. `eris-scenario` builds on top of [echo](index.md) in order to greatly expand the possibilities whilst making it as simple as possible to model complex energy system problems.

    We recommend starting out with `eris-scenario` first and only "dropping-down" to the level of Echo when necessary.

## Installation

=== "pip"

    ``` sh
    pip install eris-echo
    ```

=== "uv"

    ``` sh
    uv add --dev eris-echo
    ```

## Eris

Eris is a collection of multi-commodity energy modelling tools,

- [echo](https://github.com/bsgip/echo) — a multi-commodity energy flow solver/optimiser.
- `eris-scenario` — a sophisticated tool for generating energy modelling scenarios.
- `MES` — a package for the stateless representations of energy networks. 
- `e-json` — a data format for representing electrical networks and associated data based on [JSON](https://www.json.org/json-en.html).
- [Smart Grid Toolbox (SGT)](https://gitlab.com/SmartGridToolbox/SmartGridToolbox) — a comprehensive toolbox for solving electical power flow problems.

!!! note "Open-sourcing efforts"

    Currently only [echo](https://github.com/bsgip/echo) and [SGT](https://gitlab.com/SmartGridToolbox/SmartGridToolbox) are open-source. However we are committed to open-sourcing the whole Eris suite in the spirit of collaboration and sharing.

    As each package is open-sourced, the above list will be updated to link through to the available package.





