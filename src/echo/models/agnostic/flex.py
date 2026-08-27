from echo.configuration import FlowConstraint, Flows, OptimisationType
from echo.models.base import Port


class FlexPort(Port):
    """Flexible variable port, which can import and export without constraints."""

    flows = Flows.Both
    import_constraint = FlowConstraint.NoConstraint
    export_constraint = FlowConstraint.NoConstraint
    flow_type = OptimisationType.Variable


class FlexSink(FlexPort):
    """Flexible port, imports only"""

    flows = Flows.Import


class FlexSource(FlexPort):
    """Flexible ports, exports only"""

    flows = Flows.Export
