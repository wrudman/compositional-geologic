"""Randomly assign each Streamlit session to one of the two survey conditions.

Use this file as the Streamlit entry point on Render.  The assignment is made
once per browser session and retained across Streamlit reruns, so a participant
cannot switch conditions in the middle of the survey.
"""

from pathlib import Path
import random

import streamlit as st


ASSIGNMENT_KEY = "_beta_survey_condition"
SURVEY_FILES = {
    "compositional": "compositional_survey.py",
    "annotation": "app_2.py",
}


if ASSIGNMENT_KEY not in st.session_state:
    st.session_state[ASSIGNMENT_KEY] = random.SystemRandom().choice(
        tuple(SURVEY_FILES)
    )

condition = st.session_state[ASSIGNMENT_KEY]
survey_path = Path(__file__).resolve().with_name(SURVEY_FILES[condition])

# Execute the chosen survey inside this real Streamlit module.  This matters for
# custom components, which inspect their caller's registered Python module.
# Giving the module the survey's __file__ also preserves relative file paths.
__file__ = str(survey_path)
exec(compile(survey_path.read_bytes(), str(survey_path), "exec"), globals())
