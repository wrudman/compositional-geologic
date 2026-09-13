"""Shared tutorial wording and progress display for both conditions."""
TUTORIAL_SELECTION_TITLE = 'Select one Region, one Angle, one Vertex, and one Edge.'
TUTORIAL_FRAME_TEXT = "The **frame** is the diagram's outer boundary.  \nThe **outside of the frame** is the area beyond that boundary."
TUTORIAL_DIRECTION_TEXT = "**Clockwise** follows the direction of a clock's hands: top → right → bottom → left.  \n**Counterclockwise** goes in the opposite direction: top → left → bottom → right."
TUTORIAL_DIRECTION_QUESTION = '**Which direction do the numbered vertices and arrows show?**'


def render_tutorial_progress(stage, tool_fraction=0.0, *, tool_count=4, answer_complete=False):
    """Each common lesson, tool exercise, and answer exercise has equal weight."""
    import streamlit as st
    labels = ["Selection", "Frame", "Directions", "Tools", "Answer practice"]
    total = 3 + tool_count + 1
    if stage < 3:
        completed = stage
    elif stage == 3:
        completed = 3 + round(tool_fraction * tool_count)
    else:
        completed = 3 + tool_count + int(answer_complete)
    st.progress(min(completed / total, 1.0), text=labels[stage])

TUTORIAL_BLUE_BOX_GUIDE = "The blue box below explains what you can do with each tool and how to use it."
