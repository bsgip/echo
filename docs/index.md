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

Echo is one component in a collection of powerful multi-commodity energy modelling software called [Eris](https://bsgip.github.io/eris/).

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
