"""Shared spacing for the two surveys' right-hand panel headings."""

SIDE_PANEL_CSS = """
<style>
/* Keep the initial workspace compact, while allowing results to grow normally. */
.block-container {
    padding-top: 4rem !important;
    padding-bottom: 1rem !important;
}
div[data-testid="stVerticalBlock"] { gap: 0.5rem; }
/* Style-only elements and invisible script frames must not create blank rows. */
div[data-testid="stElementContainer"]:has(> div[data-testid="stMarkdown"] style):not(:has(p, section)),
div.element-container:has(> div[data-testid="stMarkdown"] style):not(:has(p, section)),
div[data-testid="stElementContainer"]:has(iframe[height="0"]),
div.element-container:has(iframe[height="0"]) {
    display: none;
}
div[data-testid="stForm"]:has(#survey-answer-style-anchor) [data-testid="stWidgetLabel"] p,
div[data-testid="stForm"]:has(#survey-answer-style-anchor) .stTextArea label p,
div[data-testid="stForm"]:has(#survey-answer-style-anchor) .stRadio > label p {
    font-size: 1rem !important;
}
div[data-testid="stAlert"][data-baseweb="notification"]:has(svg[aria-label="info"]),
div[data-testid="stAlert"]:has([data-testid="stNotificationContentInfo"]) {
    background: #eff6ff;
    color: #1e3a5f;
}
.survey-side-heading {
    margin: 0 !important;
    padding: 12px 0 6px;
    line-height: 1.35 !important;
}
.survey-side-heading[data-section="Help"] { padding-top: 0; }
div[data-testid="stElementContainer"]:has(> div[data-testid="stMarkdown"] #survey-answer-style-anchor) {
    display: none;
}
@media (max-width: 700px) {
    .block-container { padding-top: 4rem !important; }
}
</style>
"""


def render_survey_header(caption, text, practice=False):
    """Identical header geometry above both surveys' work/Help row."""
    import html
    import re
    import streamlit as st
    left, _ = st.columns([8, 3], gap="small", vertical_alignment="top")
    with left:
        st.caption(caption)
        paragraphs = [part.replace("\n", " ").strip()
                      for part in re.split(r"\n\s*\n", html.escape(text)) if part.strip()]
        content = "".join(
            f'<div style="margin:{"0" if i == 0 else "0.45rem"} 0 0 0;">{part}</div>'
            for i, part in enumerate(paragraphs)
        )
        if practice:
            st.markdown(
                f'<div style="font-size:18px; font-weight:600; line-height:1.35; '
                f'min-height:2.7em; margin:0.1rem 0 0.9rem 0;">{content}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<section aria-label="Question" style="background:#eff6ff; color:#1e3a5f; '
                'border:1px solid #bfdbfe; border-radius:8px; '
                'padding:0.6rem 0.85rem; margin:0.1rem 0 0.35rem 0;">'
                '<div style="font-size:1.125rem; font-weight:700; margin-bottom:0.25rem;">Question</div>'
                f'<div style="font-size:18px; font-weight:600; line-height:1.35;">{content}</div>'
                '</section>',
                unsafe_allow_html=True,
            )
