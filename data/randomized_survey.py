"""Strictly alternate participants between the two survey conditions.

Render uses Postgres for a concurrency-safe global sequence. Local runs use a
small SQLite database with the same sticky participant assignment behavior.
"""

from datetime import datetime
from pathlib import Path
import os
import sqlite3
import uuid

import streamlit as st

try:
    import psycopg
except ImportError:
    psycopg = None


ASSIGNMENT_KEY = "_beta_survey_condition"
SURVEY_FILES = {
    "compositional": "compositional_survey.py",
    "annotation": "app_2.py",
}
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
LOCAL_ASSIGNMENT_DB = os.environ.get(
    "SURVEY_ASSIGNMENT_DB",
    "/tmp/geologic_survey_condition_assignments.sqlite3",
)


def safe_participant_id(value):
    safe = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in str(value)
    )
    return safe[:80] or "local_demo"


def get_or_create_participant_id():
    raw_id = (
        st.query_params.get("participant_id")
        or st.query_params.get("pid")
        or st.query_params.get("survey_instance")
    )
    if raw_id:
        return safe_participant_id(raw_id)

    participant_id = safe_participant_id(
        f"participant_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )
    # Make the identity durable before assigning a condition. A hard refresh,
    # reconnect, or a second tab opened from this URL then keeps the same group.
    st.query_params["pid"] = participant_id
    st.rerun()


def start_internal_preview(condition):
    """Launch an explicitly marked, non-study preview run."""
    preview_id = safe_participant_id(
        f"internal_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )
    st.query_params.from_dict({
        "pid": preview_id,
        "survey_instance": preview_id,
        "preview": "1",
        "preview_condition": condition,
    })
    st.rerun()


def condition_for_number(assignment_number):
    return "compositional" if assignment_number % 2 == 1 else "annotation"


def assign_with_postgres(participant_id):
    if psycopg is None:
        raise RuntimeError("psycopg is required when DATABASE_URL is configured")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.survey_condition_counter (
                    counter_id SMALLINT PRIMARY KEY CHECK (counter_id = 1),
                    next_assignment_number BIGINT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.survey_condition_assignments (
                    participant_id TEXT PRIMARY KEY,
                    condition TEXT NOT NULL CHECK (condition IN ('compositional', 'annotation')),
                    assignment_number BIGINT NOT NULL UNIQUE,
                    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                INSERT INTO public.survey_condition_counter (
                    counter_id, next_assignment_number
                ) VALUES (1, 1)
                ON CONFLICT (counter_id) DO NOTHING
                """
            )
            # One global row lock serializes simultaneous first-time visitors.
            cur.execute(
                """
                SELECT next_assignment_number
                FROM public.survey_condition_counter
                WHERE counter_id = 1
                FOR UPDATE
                """
            )
            next_number = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT condition
                FROM public.survey_condition_assignments
                WHERE participant_id = %s
                """,
                (participant_id,),
            )
            existing = cur.fetchone()
            if existing:
                return existing[0]

            condition = condition_for_number(next_number)
            cur.execute(
                """
                INSERT INTO public.survey_condition_assignments (
                    participant_id, condition, assignment_number
                ) VALUES (%s, %s, %s)
                """,
                (participant_id, condition, next_number),
            )
            cur.execute(
                """
                UPDATE public.survey_condition_counter
                SET next_assignment_number = %s
                WHERE counter_id = 1
                """,
                (next_number + 1,),
            )
            return condition


def assign_with_sqlite(participant_id):
    with sqlite3.connect(LOCAL_ASSIGNMENT_DB, timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS survey_condition_counter (
                counter_id INTEGER PRIMARY KEY CHECK (counter_id = 1),
                next_assignment_number INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS survey_condition_assignments (
                participant_id TEXT PRIMARY KEY,
                condition TEXT NOT NULL,
                assignment_number INTEGER NOT NULL UNIQUE,
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO survey_condition_counter (
                counter_id, next_assignment_number
            ) VALUES (1, 1)
            """
        )
        existing = conn.execute(
            """
            SELECT condition FROM survey_condition_assignments
            WHERE participant_id = ?
            """,
            (participant_id,),
        ).fetchone()
        if existing:
            return existing[0]

        next_number = int(
            conn.execute(
                """
                SELECT next_assignment_number FROM survey_condition_counter
                WHERE counter_id = 1
                """
            ).fetchone()[0]
        )
        condition = condition_for_number(next_number)
        conn.execute(
            """
            INSERT INTO survey_condition_assignments (
                participant_id, condition, assignment_number
            ) VALUES (?, ?, ?)
            """,
            (participant_id, condition, next_number),
        )
        conn.execute(
            """
            UPDATE survey_condition_counter
            SET next_assignment_number = ?
            WHERE counter_id = 1
            """,
            (next_number + 1,),
        )
        return condition


# Production participants remain on the annotation-only flow. The internal
# route can preview either interface without using participant identifiers.
query_params = st.query_params
preview_mode = str(query_params.get("preview", "")).lower() in {"1", "true", "yes"}
preview_condition = str(query_params.get("preview_condition", "")).lower()
has_identity = any(query_params.get(key) for key in ("participant_id", "pid", "survey_instance"))

if preview_mode and preview_condition in SURVEY_FILES:
    participant_id = get_or_create_participant_id()
    condition = preview_condition
elif not has_identity:
    st.title("Geometry Reasoning Survey")
    st.caption("Choose the route that matches your purpose.")
    route = st.radio("How are you accessing this survey?", ("I’m a participant", "Internal preview / testing"))
    if route == "I’m a participant":
        st.write("You will enter the current annotation survey and complete its tutorial first.")
        if st.button("Continue as participant", type="primary"):
            get_or_create_participant_id()
    else:
        st.write("Preview runs are labelled as internal and may skip the tutorial.")
        selected_preview_condition = st.radio("Survey to preview", ("annotation", "compositional"), format_func=str.title)
        if st.button("Open internal preview", type="primary"):
            start_internal_preview(selected_preview_condition)
    st.stop()
else:
    participant_id = get_or_create_participant_id()
    condition = "annotation"

st.session_state[ASSIGNMENT_KEY] = condition
survey_path = Path(__file__).resolve().with_name(SURVEY_FILES[condition])

# Execute the selected survey inside this registered Streamlit module so custom
# components can resolve their caller correctly.
__file__ = str(survey_path)
exec(compile(survey_path.read_bytes(), str(survey_path), "exec"), globals())
