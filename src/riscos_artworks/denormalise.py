"""Expands the raw, flat sibling-list structure that :mod:`decoder`
produces into the nested parent/child tree ArtWorks actually renders.

Background
----------
The on-disk format stores a run of sibling records -- e.g. a shape
followed by its own local fill-colour override, or a layer followed by
its own content -- as a flat list, exactly as :mod:`decoder` reads it
(see ``Record.child_lists`` and ``RecordList.records``). That flat
form is *not* what a renderer should walk directly: real ArtWorks (and
the independently-maintained ``riscos-artworks-js`` reference, whose
``Artworks.denormalise()`` this function mirrors byte-for-byte in
behaviour, despite the initially-confusing name) re-nests every such
flat run before rendering, turning ``[A, B, C]`` into ``A`` containing
a single synthetic child list holding just ``B``, which in turn
contains a single synthetic child list holding just ``C``: each
subsequent sibling becomes the *sole child* of the one immediately
before it, all the way down.

This matters because attributes only affect their own parent once
rendered (see ``Record``'s own docstring), and "their own parent"
means the record whose child subtree they were nested inside -- not
whatever their *file-order* sibling happens to be. Confirmed with a
minimal, real-world repro: ``BlueRect,d94`` (a single rectangle with
one local ``FillColourRecord`` after it, both flat siblings as
:mod:`decoder` reads them) renders with the *ambient default* colour
(black) instead of blue unless this transform runs first; the
``riscos-artworks-js`` reference renders it correctly precisely
because its own SVG mapper always calls ``denormalise()`` before
walking the tree.

Call :func:`denormalise` once, on a freshly decoded :class:`~riscos_artworks.model.ArtWorks`,
before doing any rendering/attribute-cascade walk of its own. Decoding
itself is left alone -- the flat form is what's actually on disk, and
is still the right representation for anything that inspects raw file
structure (offsets, spans, audits) rather than rendering it.
"""

from __future__ import annotations

import dataclasses

from . import model as m

__all__ = ["denormalise"]


def denormalise(artwork: m.ArtWorks) -> m.ArtWorks:
    """Return a copy of *artwork* with every flat sibling run re-nested
    into a parent/child chain, ready for rendering. See the module
    docstring for why this is necessary and what it changes."""
    return dataclasses.replace(artwork, record_lists=_denormalise_lists(artwork.record_lists))


def _denormalise_lists(lists: tuple[m.RecordList, ...]) -> tuple[m.RecordList, ...]:
    return tuple(dataclasses.replace(record_list, records=_denormalise_list(record_list.records))
                 for record_list in lists)


def _denormalise_list(records: tuple[m.Record, ...]) -> tuple[m.Record, ...]:
    if not records:
        return records
    return _denormalise_subrecords(_nest_siblings(records))


def _nest_siblings(records: tuple[m.Record, ...]) -> tuple[m.Record, ...]:
    """[A, B, C] -> [A'] where A' nests B as its sole synthetic child,
    and B (unexpanded here -- see _denormalise_subrecords) nests C the
    same way once its own child_lists get walked in turn."""
    result = list(records)
    while len(result) > 1:
        last = result.pop()
        penultimate = result.pop()
        synthetic = m.RecordList(
            pointer=m.RelativePointer(offset=last.span.offset, previous=0, next=0),
            records=(last,),
            span=m.SourceSpan(offset=last.span.offset, length=0),
        )
        result.append(dataclasses.replace(
            penultimate, child_lists=(synthetic, *penultimate.child_lists)))
    return tuple(result)


def _denormalise_subrecords(records: tuple[m.Record, ...]) -> tuple[m.Record, ...]:
    return tuple(dataclasses.replace(record, child_lists=_denormalise_lists(record.child_lists))
                 for record in records)
