"""FinAI on Render Workflows: Claude's analysis as distributed tasks.

The web app (app.py) asks Render to run `analyze_finances` and waits for its answer. That task
splits the work like a small team:

    analyze_finances                 (coordinates the steps)
     ├─ classify_group  x N          (one Claude call per group of 20 new transactions,
     │                                 all at the same time, each on its own instance)
     └─ write_insights               (one Claude call: headline, comparison, tips)

Every step is a plain function from ai_analysis.py, so the server can run the very same steps
itself when Render Workflows isn't configured (for example, on your own computer).

Start command on Render:  python workflows.py
"""
import asyncio

from render import Retry, TaskContext, Workflows

import ai_analysis

# One retry if a Claude call fails (for example, a brief network error), and 5 minutes per attempt.
workflow = Workflows(default_retry=Retry(max_retries=1, wait_duration_ms=2000), default_timeout=300)


@workflow.task
def classify_group(ctx: TaskContext, chunk: list, transactions: list, profile: dict, language: str) -> dict:
    """Claude sorts one group of transactions into need / want / luxury (and translates them)."""
    return ai_analysis.classify_chunk(chunk, transactions, profile, language)


@workflow.task
def write_insights(ctx: TaskContext, transactions: list, months: list, profile: dict, goals: list,
                   classifications: list, language: str) -> dict:
    """Claude writes the headline, month comparison, tips and recommendation."""
    return ai_analysis.write_insights(transactions, months, profile, goals, classifications, language)


@workflow.task(timeout_seconds=600)
async def analyze_finances(ctx: TaskContext, transactions: list, months: list, profile: dict, goals: list,
                           language: str, known: dict) -> dict:
    """The whole analysis. `known` holds the answers the web app already remembers, so only new
    transactions are sent to Claude. Returns the same shape as ai_analysis.run_steps_here."""
    keys = ai_analysis.class_keys(transactions, profile, language)
    chunks = ai_analysis.chunks_to_classify(transactions, keys, known)
    answers = await asyncio.gather(*[ctx.run(classify_group, chunk, transactions, profile, language)
                                     for chunk in chunks])
    new = ai_analysis.answers_to_memory(chunks, list(answers), keys)
    classifications, translations = ai_analysis.merge_classes(transactions, keys, {**known, **new}, profile, language)
    insights = await ctx.run(write_insights, transactions, months, profile, goals, classifications, language)
    return {"new_classes": new, "classifications": classifications, "translations": translations,
            "insights": insights, "classify_runs": len(chunks)}


if __name__ == "__main__":
    workflow.start()
