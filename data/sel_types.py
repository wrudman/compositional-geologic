# sel_types.py
"""Selection types for the Geo Tools app.
MUST live in its own module: Streamlit re-runs app.py on every interaction,
re-creating any classes defined there, which breaks isinstance() for objects
stored in st.session_state. Module classes are cached and stable."""

class AngleSel:
    def __init__(self, vertex, face):
        self.vertex = vertex
        self.face = face
    def __eq__(self, other):
        return (type(other).__name__ == "AngleSel"
                and other.vertex is self.vertex and other.face is self.face)
    def __hash__(self):
        return hash(("angle", id(self.vertex), id(self.face)))

class EdgeSel:
    def __init__(self, segments, owner, text):
        self.segments = tuple(segments)
        self.owner = owner
        self.text = text
    def __eq__(self, other):
        return (type(other).__name__ == "EdgeSel"
                and other.owner is self.owner
                and self._segment_keys() == other._segment_keys())
    def __hash__(self):
        return hash(("edge", id(self.owner), self._segment_keys()))

    def _segment_keys(self):
        """Identity of the underlying undirected geometric segments.

        A click can reach the same physical edge through either half-edge
        orientation, so each segment is keyed together with its reverse.
        """
        return frozenset(
            frozenset((id(segment), id(segment.reverse)))
            for segment in self.segments
        )
