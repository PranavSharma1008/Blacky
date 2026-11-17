"""
Screen-analysis tools for BlackyAgent.

Lets the agent look at the live display with the local vision model and work
through an MCQ paper on screen (answer the current question, click Next).
"""

from blacky.tools.base import registry
from blacky.core.screen_mode import (
    ScreenSession,
    format_solved_summary,
)


@registry.register
def analyze_screen(question: str = "") -> str:
    """
    Look at the current macOS screen and answer a question about what is visible.
    Use this whenever the user says 'analyze my screen', 'what is on my screen',
    'read this page/paper for me' or asks anything that needs the visible UI text.
    Args:
        question: What to find out or do based on the screen (empty = describe the screen).
    """
    session = ScreenSession()
    result = session.analyze(question)
    registry.log_call("analyze_screen", {"question": question}, result, success=True)
    return result


@registry.register
def solve_mcqs_on_screen(count: int = 10, auto_advance: bool = True) -> str:
    """
    Solve the multiple-choice questions visible on the macOS screen one by one.
    Reads the current MCQ with the local vision model, clicks the correct option,
    then clicks Next/Save & Next and repeats, like a human solving a sample paper.
    Args:
        count: How many questions to solve in this run (default 10, maximum 50).
        auto_advance: Click the Next button after answering each question.
    """
    session = ScreenSession()
    result = session.solve_mcqs(count=count, auto_advance=auto_advance)
    text = format_solved_summary(result)
    registry.log_call(
        "solve_mcqs_on_screen",
        {"count": count, "auto_advance": auto_advance},
        text,
        success=bool(result.get("solved")),
    )
    return text
