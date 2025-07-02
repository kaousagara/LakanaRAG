from __future__ import annotations

import json
import os
import re
import time
import textwrap
from typing import List, Tuple

import pipmaster as pm  # type: ignore

if not pm.is_installed("fpdf2"):
    pm.install("fpdf2")

from fpdf import FPDF

from .base import QueryParam


async def _parse_json(text: str) -> list[str]:
    match = re.search(r"```(?:json)?(.*?)```", text.strip(), re.DOTALL)
    json_text = match.group(1).strip() if match else text.strip()
    try:
        data = json.loads(json_text)
        if isinstance(data, list):
            return [str(q) for q in data]
    except Exception:
        pass
    return []


async def _generate_subqueries(query: str, rag) -> list[str]:
    """Generate initial sub-questions for the tree search."""
    plan_prompt = (
        "Décompose la requête suivante en 3 sous-questions précises "
        "au format JSON (liste de chaînes). Réponse uniquement en JSON."
    )
    plan_text = await rag.aquery(
        query,
        QueryParam(mode="naive", response_type="Bullet Points", stream=False),
        system_prompt=plan_prompt,
    )
    subs = await _parse_json(plan_text)
    return subs or [query]


async def _generate_followups(question: str, answer: str, rag) -> list[str]:
    """Propose follow-up questions to deepen the analysis."""
    prompt = (
        "En te basant sur la question et la réponse ci-dessous, "
        "génère deux questions de suivi au format JSON (liste de chaînes)."
    )
    text = f"Question:\n{question}\n\nRéponse:\n{answer}"
    follow = await rag.aquery(
        text,
        QueryParam(mode="naive", response_type="Bullet Points", stream=False),
        system_prompt=prompt,
    )
    return await _parse_json(follow)


async def _answer_question(question: str, rag, param: QueryParam) -> str:
    sub_param = QueryParam(**param.__dict__)
    sub_param.mode = "hybrid"
    sub_param.stream = False
    ans = await rag.aquery(question, sub_param)
    return ans if isinstance(ans, str) else str(ans)


def _create_pdf(content: str, working_dir: str) -> str:
    """Generate a PDF file from the given text content."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)

    # Very long words without spaces can cause FPDF to raise
    # `Not enough horizontal space to render a single character`.
    # We pre-wrap lines to avoid this situation.
    for line in content.split("\n"):
        wrapped = textwrap.wrap(
            line, width=100, break_long_words=True, break_on_hyphens=False
        )
        for chunk in wrapped or [""]:
            pdf.multi_cell(0, 10, chunk)

    report_dir = os.path.join(working_dir, "reports")
    os.makedirs(report_dir, exist_ok=True)
    file_path = os.path.join(report_dir, f"deepsearch_{int(time.time())}.pdf")
    pdf.output(file_path)
    return file_path


def _format_report(query: str, qa_pairs: List[Tuple[str, str]]) -> str:
    text_lines = [f"Rapport d'analyse pour : {query}", ""]
    for idx, (q, a) in enumerate(qa_pairs, 1):
        text_lines.append(f"### Question {idx}: {q}")
        text_lines.append("")
        text_lines.append(a)
        text_lines.append("")
    return "\n".join(text_lines)


async def deepsearch_query(query: str, rag, param: QueryParam) -> str:
    """Run a Tree-of-Thought deep search and return a PDF report path."""
    subqueries = await _generate_subqueries(query, rag)

    queue: List[Tuple[str, int]] = [(q, 1) for q in subqueries]
    qa_pairs: List[Tuple[str, str]] = []
    max_depth = 2

    while queue:
        current_q, depth = queue.pop(0)
        answer = await _answer_question(current_q, rag, param)
        qa_pairs.append((current_q, answer))
        if depth < max_depth:
            follow = await _generate_followups(current_q, answer, rag)
            for f in follow:
                queue.append((f, depth + 1))

    report_text = _format_report(query, qa_pairs)
    pdf_path = _create_pdf(report_text, rag.working_dir)
    return pdf_path
