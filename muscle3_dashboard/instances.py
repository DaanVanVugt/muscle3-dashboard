"""Helpers for libmuscle instance names.

A multiplicity / vector-port component runs several instances, each named
``component[index]`` (e.g. ``worker[0]``, ``nice_inv[4]``). Several views need
to map an instance back to its base component (the single box ymmsl2svg draws,
the row in the graph, the log grouping), so the parsing lives here once instead
of being re-implemented per view.
"""

import re

# One or more trailing ``[...]`` index groups (``worker[0]`` -> ``worker``,
# ``grid[2][3]`` -> ``grid`` for multi-dimensional multiplicity). Anchored to the
# end so a bracket in the middle of a name is left untouched.
_INSTANCE_SUFFIX = re.compile(r"(?:\[[^\]]*\])+$")


#: First numeric index in an instance name (``nice_inv[2]`` -> ``2``).
_INSTANCE_INDEX = re.compile(r"\[(\d+)\]")
#: The full bracketed label of an instance (``grid[2][3]`` -> ``2][3``).
_INSTANCE_LABEL = re.compile(r"\[(.+)\]$")


def base_name(name: str) -> str:
    """Return the base component name, stripping a trailing instance suffix.

    ``worker[5]`` -> ``worker``; ``macro`` -> ``macro``.
    """
    return _INSTANCE_SUFFIX.sub("", name)


def instance_sort_key(name: str) -> tuple[int]:
    """Sort key ordering instances by numeric index (``[2]`` before ``[10]``)."""
    match = _INSTANCE_INDEX.search(name)
    return (int(match.group(1)),) if match else (-1,)


def instance_label(name: str) -> str:
    """Short label for an instance selector: the text inside the brackets."""
    match = _INSTANCE_LABEL.search(name)
    return match.group(1) if match else name
