from typing import Any, Callable
from collections import defaultdict
from itertools import pairwise


class AttributeTracker:
    """Attribute Tracker

    Each checkpoint records *all* the attributes on the object at the checkpoint.

    Therefore to see which attributes were added between two checkpoints, we need
    to calculate the difference, which we can do with the `diff` method.

    Usage:
    >>> class Foo(object):
    ...     pass
    ...
    >>> foo = Foo()
    >>> tracker = AttributeTracker()
    >>> tracker.track(foo, "init")
    >>> foo.a = 1
    >>> tracker.track(foo, "setting-a")
    >>> tracker.diff("setting-a", "init")
    >>> attrs = tracker.filtered_pairwise_attributes(include: lambda prev_k, k: k=="checkpoint-of-interest")
    >>> tracker.to_html_string(foo, "setting-a")
    """

    def __init__(self, object: Any):
        """Store the attributes for a checkpoint. The ordering of the keys (checkpoints) is important"""
        self.attributes: dict[str, list[str]] = {}
        self.object = object

    def mark(self, checkpoint: str):
        """Create a new checkpoint and associate it with the objects attributes."""
        self.attributes[checkpoint] = dir(self.object)

    def diff(self, checkpoint1: str, checkpoint2: str) -> list[str]:
        """Returns the attributes that are present at checkpoint2 but not a checkpoint1."""
        s1 = set(self.attributes[checkpoint1])
        s2 = set(self.attributes[checkpoint2])

        return list(s2 - s1)

    def __str__(self) -> str:
        """Returns string representation of all attributes added between first and last checkpoints."""
        result = ""
        for prev_checkpoint, checkpoint in pairwise(self.attributes.keys()):
            for attr_name in self.diff(prev_checkpoint, checkpoint):
                result += f"- {attr_name} ({type(getattr(self.object,attr_name))})\n"

        return result

    def filtered_pairwise_attributes(self, include: Callable[[str, str], bool]) -> dict[str, list[Any]]:
        """
        Pairwise diff (attributes added to object between consecutive checkpoints).
        Only including pairs where filter function `include(prev_checkpoint, checkpoint)` returns True.
        And groups attributes by type (as class-name string).

        Returns a mapping from attribute class name to a list of attributes (by name) belonging to that class.
        """

        attrs = defaultdict(list)
        for prev_checkpoint, checkpoint in pairwise(self.attributes.keys()):
            if include(prev_checkpoint, checkpoint):
                attr_keys = self.diff(prev_checkpoint, checkpoint)

                for attr_key in attr_keys:
                    attr = getattr(self.object, attr_key)
                    attr_classname = type(attr).__name__

                    # Group attributes by class
                    attrs[attr_classname].append(attr_key)
        return attrs
