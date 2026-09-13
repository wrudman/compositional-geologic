"""A shared, unscored practice of the actual answer-entry workflow."""
import re
import streamlit as st


def classify_answer(value):
    answer = value.strip()
    if not re.fullmatch(r'[A-Z]', answer):
        return 'format'
    return 'correct' if answer == 'B' else 'incorrect'


def render_answer_practice(state, save, free_practice_text):
    """Render only the answer controls inside the existing tutorial workspace."""
    if state.get('free_practice'):
        st.markdown(free_practice_text)
        return st.button('Start Survey', type='primary', key='answer_practice_start_survey')
    if not state.get('passed'):
        st.info('Type your answer in **Insert answer here**. The gray **Answer format** box below the input tells you how to format your response. Follow the instructions, then click **Confirm Answer**. This practice is not scored.')
    with st.form('answer_format_practice_form', enter_to_submit=False):
        st.markdown('<span id="survey-answer-style-anchor"></span>', unsafe_allow_html=True)
        input_col, _ = st.columns([3, 2], gap='small', vertical_alignment='bottom')
        with input_col:
            value = st.text_area('Insert answer here', height=68, key='answer_format_practice_input',
                                 disabled=state.get('passed', False))
            submitted = st.form_submit_button('Confirm Answer', type='primary', disabled=state.get('passed', False))
        if not state.get('passed'):
            st.markdown(
                '<div style="font-size:1rem; line-height:1.5; color:#374151; background:#f3f4f6; '
                'border-left:3px solid #9ca3af; padding:0.65rem 0.75rem; margin-top:0.25rem; '
                'margin-bottom:0.5rem; border-radius:0 0.3rem 0.3rem 0;">'
                '<strong style="font-size:1rem; font-weight:700; white-space:nowrap;">Answer format:</strong> '
                'Enter one capital letter, e.g. A.</div>', unsafe_allow_html=True)
    if submitted:
        result = classify_answer(value)
        state['feedback'] = result
        state['passed'] = result == 'correct'
        save()
        if state['passed']:
            st.rerun()
    result = state.get('feedback')
    if result == 'format':
        st.error('Please enter one capital letter, such as A.')
    elif result == 'incorrect':
        st.error('Not quite. Look at the blue region near the top and try again.')
    elif result in ('correct', 'example'):
        if result == 'example':
            st.success('Completed example: the blue region is B. Enter B as one capital letter, as required by Answer format, then click Confirm Answer when answering survey questions.')
        else:
            st.success('Correct. In the survey, check the Answer format instructions for each question before clicking Confirm Answer.')
        if st.button('Continue', type='primary', key='answer_practice_continue'):
            state['free_practice'] = True
            save()
            st.rerun()
    return False


def render_answer_practice_help(state, save):
    if state.get('passed') or state.get('free_practice'):
        return
    def show_example():
        st.session_state['answer_format_practice_input'] = 'B'
        state['used_completed_example'] = True
        state['passed'] = True
        state['feedback'] = 'example'
        save()
    with st.expander('Having trouble with this step?'):
        st.caption('Click below to see this step completed for you. Then click Continue.')
        st.button('Show Completed Example', key='answer_practice_show_example',
                  use_container_width=True, on_click=show_example)
