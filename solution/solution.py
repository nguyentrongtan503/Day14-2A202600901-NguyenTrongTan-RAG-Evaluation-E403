"""
Day 14 — AI Evaluation & Benchmarking Pipeline
AICB-P1: AI Practical Competency Program, Phase 1

Completed solution implementing all tasks:
    Task 1  — Data Models (QAPair, EvalResult)
    Task 2  — RAGASEvaluator answer-side metrics
    Task 2b — RAGASEvaluator retrieval-side metrics + reranker
    Task 3  — LLMJudge (rubric scoring + bias detection)
    Task 4  — BenchmarkRunner (run, report, regression, identify failures)
    Task 5  — FailureAnalyzer (categorize, root cause, suggestions, log)

Run: pytest tests/ -v
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Task 1 — Data Models (Golden Dataset + Evaluation Results)
# ---------------------------------------------------------------------------

@dataclass
class QAPair:
    """A question-answer pair for evaluation (part of the Golden Dataset)."""
    question: str
    expected_answer: str
    context: str = ""
    metadata: dict = field(default_factory=dict)
    retrieved_contexts: list = field(default_factory=list)


@dataclass
class EvalResult:
    """Evaluation result for a single Q&A pair."""
    qa_pair: QAPair
    actual_answer: str
    faithfulness: float
    relevance: float
    completeness: float
    passed: bool
    failure_type: str | None = None
    context_precision: float | None = None
    context_recall: float | None = None

    def overall_score(self) -> float:
        """Compute the average of faithfulness, relevance, and completeness."""
        return (self.faithfulness + self.relevance + self.completeness) / 3.0


# ---------------------------------------------------------------------------
# Task 2 — RAGAS Evaluator (Simplified word-overlap heuristic)
# ---------------------------------------------------------------------------

STOPWORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "to", "for", "with", "as", "by", "and", "or",
    "it", "its", "this", "that", "these", "those", "from", "into", "than",
}


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokenization, ignoring punctuation and stopwords."""
    if not text:
        return set()
    tokens = re.findall(r"\b\w+\b", text.lower())
    return {t for t in tokens if t not in STOPWORDS}


def _clamp(value: float) -> float:
    """Clamp a value into the [0.0, 1.0] range."""
    return max(0.0, min(1.0, value))


class RAGASEvaluator:
    """Evaluates RAG pipeline outputs using RAGAS-inspired heuristics."""

    def evaluate_faithfulness(self, answer: str, context: str) -> float:
        """Measure how grounded the answer is in the context."""
        answer_tokens = _tokenize(answer)
        if not answer_tokens:
            return 1.0
        context_tokens = _tokenize(context)
        overlap = answer_tokens & context_tokens
        return _clamp(len(overlap) / len(answer_tokens))

    def evaluate_relevance(self, answer: str, question: str) -> float:
        """Measure how relevant the answer is to the question."""
        question_tokens = _tokenize(question)
        if not question_tokens:
            return 1.0
        answer_tokens = _tokenize(answer)
        overlap = answer_tokens & question_tokens
        return _clamp(len(overlap) / len(question_tokens))

    def evaluate_completeness(self, answer: str, expected: str) -> float:
        """Measure how well the answer covers the expected answer."""
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        answer_tokens = _tokenize(answer)
        overlap = answer_tokens & expected_tokens
        return _clamp(len(overlap) / len(expected_tokens))

    # -----------------------------------------------------------------------
    # Task 2b — Retrieval-side metrics (evaluate the GET-CONTEXT step)
    # -----------------------------------------------------------------------

    def evaluate_context_recall(self, contexts: list[str], expected: str) -> float:
        """Context Recall — coverage of expected by the UNION of chunks."""
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        union_tokens: set[str] = set()
        for chunk in contexts:
            union_tokens |= _tokenize(chunk)
        overlap = expected_tokens & union_tokens
        return _clamp(len(overlap) / len(expected_tokens))

    def evaluate_context_precision(
        self,
        contexts: list[str],
        expected: str,
        relevance_threshold: float = 0.1,
    ) -> float:
        """Context Precision — RANK-AWARE Average Precision (AP@K), like RAGAS."""
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        if not contexts:
            return 0.0

        # Mark each chunk as relevant or not, in retriever order.
        relevant_flags: list[bool] = []
        for chunk in contexts:
            chunk_tokens = _tokenize(chunk)
            coverage = len(chunk_tokens & expected_tokens) / len(expected_tokens)
            relevant_flags.append(coverage >= relevance_threshold)

        num_relevant = sum(relevant_flags)
        if num_relevant == 0:
            return 0.0

        running_relevant = 0
        ap_sum = 0.0
        for k, is_relevant in enumerate(relevant_flags, start=1):
            if is_relevant:
                running_relevant += 1
                precision_at_k = running_relevant / k
                ap_sum += precision_at_k  # relevant_k == 1 here

        return _clamp(ap_sum / num_relevant)

    def run_full_eval(
        self,
        answer: str,
        question: str,
        context: str,
        expected: str,
        contexts: list[str] | None = None,
    ) -> EvalResult:
        """Run all evaluations and combine into an EvalResult."""
        faithfulness = self.evaluate_faithfulness(answer, context)
        relevance = self.evaluate_relevance(answer, question)
        completeness = self.evaluate_completeness(answer, expected)

        passed = faithfulness >= 0.5 and relevance >= 0.5 and completeness >= 0.5

        failure_type: str | None = None
        if not passed:
            if faithfulness < 0.3:
                failure_type = "hallucination"
            elif relevance < 0.3:
                failure_type = "irrelevant"
            elif completeness < 0.3:
                failure_type = "incomplete"
            else:
                failure_type = "off_topic"

        context_recall: float | None = None
        context_precision: float | None = None
        if contexts:
            context_recall = self.evaluate_context_recall(contexts, expected)
            context_precision = self.evaluate_context_precision(contexts, expected)

        qa_pair = QAPair(
            question=question,
            expected_answer=expected,
            context=context,
            retrieved_contexts=contexts or [],
        )

        return EvalResult(
            qa_pair=qa_pair,
            actual_answer=answer,
            faithfulness=faithfulness,
            relevance=relevance,
            completeness=completeness,
            passed=passed,
            failure_type=failure_type,
            context_precision=context_precision,
            context_recall=context_recall,
        )


# ---------------------------------------------------------------------------
# Reranking helper (used by Exercise 3.5 — boosting Context Precision)
# ---------------------------------------------------------------------------

def rerank_by_overlap(contexts: list[str], query: str) -> list[str]:
    """A minimal lexical reranker: sort chunks by word overlap with the query."""
    query_tokens = _tokenize(query)
    return sorted(
        contexts,
        key=lambda c: len(_tokenize(c) & query_tokens),
        reverse=True,
    )


# ---------------------------------------------------------------------------
# Task 3 — LLM Judge
# ---------------------------------------------------------------------------

class LLMJudge:
    """Uses an LLM to score AI responses according to a rubric."""

    def __init__(self, judge_llm_fn: Callable[[str], str]) -> None:
        self.judge_llm_fn = judge_llm_fn

    def score_response(
        self,
        question: str,
        answer: str,
        rubric: dict[str, Any],
    ) -> dict[str, Any]:
        """Score an AI response using the judge LLM."""
        rubric_text = "\n".join(
            f"- {criterion}: {description}"
            for criterion, description in rubric.items()
        )
        prompt = (
            "You are an impartial judge. Score the following answer for each "
            "criterion on a scale from 0.0 to 1.0.\n\n"
            f"Question:\n{question}\n\n"
            f"Answer:\n{answer}\n\n"
            f"Rubric:\n{rubric_text}\n\n"
            'Respond ONLY with a JSON object mapping each criterion to a score, '
            'e.g. {"accuracy": 0.8}.'
        )

        raw = self.judge_llm_fn(prompt)

        scores: dict[str, float] = {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for criterion in rubric:
                    if criterion in parsed:
                        scores[criterion] = float(parsed[criterion])
                    else:
                        scores[criterion] = 0.5
            else:
                scores = {criterion: 0.5 for criterion in rubric}
        except (json.JSONDecodeError, TypeError, ValueError):
            scores = {criterion: 0.5 for criterion in rubric}

        return {"scores": scores, "reasoning": raw}

    def detect_bias(self, scores_batch: list[dict[str, Any]]) -> dict[str, Any]:
        """Detect potential bias patterns in a batch of judge scores."""
        positional_bias = False
        leniency_bias = False
        severity_bias = False

        # Collect all numeric scores across the batch.
        all_scores: list[float] = []
        for entry in scores_batch:
            for value in entry.get("scores", {}).values():
                all_scores.append(float(value))

        if all_scores:
            avg = sum(all_scores) / len(all_scores)
            leniency_bias = avg > 0.8
            severity_bias = avg < 0.3

        # Positional bias: first response consistently scores higher than the rest.
        if len(scores_batch) >= 2:
            def mean_score(entry: dict[str, Any]) -> float:
                vals = list(entry.get("scores", {}).values())
                return sum(float(v) for v in vals) / len(vals) if vals else 0.0

            first = mean_score(scores_batch[0])
            rest = [mean_score(e) for e in scores_batch[1:]]
            if rest:
                positional_bias = first > (sum(rest) / len(rest))

        return {
            "positional_bias": positional_bias,
            "leniency_bias": leniency_bias,
            "severity_bias": severity_bias,
        }


# ---------------------------------------------------------------------------
# Task 4 — Benchmark Runner
# ---------------------------------------------------------------------------

class BenchmarkRunner:
    """Runs a full evaluation benchmark."""

    def run(
        self,
        qa_pairs: list[QAPair],
        agent_fn: Callable[[str], str],
        evaluator: RAGASEvaluator,
    ) -> list[EvalResult]:
        """Run all QA pairs through the agent and evaluate each result."""
        results: list[EvalResult] = []
        for pair in qa_pairs:
            answer = agent_fn(pair.question)
            result = evaluator.run_full_eval(
                answer=answer,
                question=pair.question,
                context=pair.context,
                expected=pair.expected_answer,
                contexts=pair.retrieved_contexts or None,
            )
            # Preserve the original QAPair (with its metadata).
            result.qa_pair = pair
            results.append(result)
        return results

    def generate_report(self, results: list[EvalResult]) -> dict[str, Any]:
        """Generate an aggregate report from evaluation results."""
        total = len(results)
        if total == 0:
            return {
                "total": 0,
                "passed": 0,
                "pass_rate": 0.0,
                "avg_faithfulness": 0.0,
                "avg_relevance": 0.0,
                "avg_completeness": 0.0,
                "failure_types": {},
            }

        passed = sum(1 for r in results if r.passed)
        avg_faithfulness = sum(r.faithfulness for r in results) / total
        avg_relevance = sum(r.relevance for r in results) / total
        avg_completeness = sum(r.completeness for r in results) / total

        failure_types: dict[str, int] = {}
        for r in results:
            if r.failure_type:
                failure_types[r.failure_type] = failure_types.get(r.failure_type, 0) + 1

        return {
            "total": total,
            "passed": passed,
            "pass_rate": passed / total,
            "avg_faithfulness": avg_faithfulness,
            "avg_relevance": avg_relevance,
            "avg_completeness": avg_completeness,
            "failure_types": failure_types,
        }

    def run_regression(self, new_results: list, baseline_results: list) -> dict:
        """Compare new evaluation results against a baseline."""
        def avg(results: list, attr: str) -> float:
            if not results:
                return 0.0
            return sum(getattr(r, attr) for r in results) / len(results)

        new_avg_faithfulness = avg(new_results, "faithfulness")
        new_avg_relevance = avg(new_results, "relevance")
        new_avg_completeness = avg(new_results, "completeness")
        baseline_avg_faithfulness = avg(baseline_results, "faithfulness")
        baseline_avg_relevance = avg(baseline_results, "relevance")
        baseline_avg_completeness = avg(baseline_results, "completeness")

        regressions: list[str] = []
        threshold = 0.05
        if baseline_avg_faithfulness - new_avg_faithfulness > threshold:
            regressions.append("faithfulness")
        if baseline_avg_relevance - new_avg_relevance > threshold:
            regressions.append("relevance")
        if baseline_avg_completeness - new_avg_completeness > threshold:
            regressions.append("completeness")

        return {
            "new_avg_faithfulness": new_avg_faithfulness,
            "new_avg_relevance": new_avg_relevance,
            "new_avg_completeness": new_avg_completeness,
            "baseline_avg_faithfulness": baseline_avg_faithfulness,
            "baseline_avg_relevance": baseline_avg_relevance,
            "baseline_avg_completeness": baseline_avg_completeness,
            "regressions": regressions,
            "passed": len(regressions) == 0,
        }

    def identify_failures(
        self,
        results: list[EvalResult],
        threshold: float = 0.5,
    ) -> list[EvalResult]:
        """Return EvalResults where any score is below threshold."""
        return [
            r for r in results
            if r.faithfulness < threshold
            or r.relevance < threshold
            or r.completeness < threshold
        ]


# ---------------------------------------------------------------------------
# Task 5 — Failure Analyzer
# ---------------------------------------------------------------------------

class FailureAnalyzer:
    """Analyzes failed evaluation results to identify patterns and suggest fixes."""

    def categorize_failures(self, failures: list[EvalResult]) -> dict[str, int]:
        """Count failures by failure_type."""
        categories: dict[str, int] = {}
        for f in failures:
            key = f.failure_type or "unknown"
            categories[key] = categories.get(key, 0) + 1
        return categories

    def find_root_cause(self, failure: EvalResult) -> str:
        """Suggest a root cause for a single failure based on its scores."""
        scores = {
            "faithfulness": failure.faithfulness,
            "relevance": failure.relevance,
            "completeness": failure.completeness,
        }
        lowest = min(scores, key=scores.get)
        lowest_value = scores[lowest]

        # If multiple metrics are similarly low, treat as systemic.
        low_count = sum(1 for v in scores.values() if v < 0.3)
        if low_count >= 2:
            return "Multiple issues detected — review full pipeline"

        if lowest == "faithfulness":
            return "Context is missing or irrelevant — improve retrieval"
        if lowest == "relevance":
            return "Answer does not address the question — improve prompt clarity"
        if lowest == "completeness":
            return "Answer is missing key information — increase context window or improve generation"
        return "Multiple issues detected — review full pipeline"

    def generate_improvement_log(self, failures: list, suggestions: list[str]) -> str:
        """Generate a Markdown table logging failures and improvement actions."""
        header = (
            "| Failure ID | Type | Root Cause | Suggested Fix | Status |\n"
            "|------------|------|------------|---------------|--------|"
        )
        rows = [header]
        for i, failure in enumerate(failures):
            failure_id = f"F{i + 1:03d}"
            ftype = failure.failure_type or "unknown"
            root_cause = self.find_root_cause(failure)
            fix = suggestions[i] if i < len(suggestions) else "Review and address manually"
            rows.append(
                f"| {failure_id} | {ftype} | {root_cause} | {fix} | Open |"
            )
        return "\n".join(rows)

    def generate_improvement_suggestions(
        self, failures: list[EvalResult]
    ) -> list[str]:
        """Generate a prioritized list of improvement suggestions."""
        if not failures:
            return []

        categories = self.categorize_failures(failures)
        suggestions: list[str] = []

        if categories.get("hallucination"):
            suggestions.append(
                "Implement a hallucination checker / faithfulness guardrail to "
                "filter unsupported claims before returning the answer."
            )
        if categories.get("irrelevant"):
            suggestions.append(
                "Improve prompt clarity and intent routing so answers directly "
                "address the question."
            )
        if categories.get("incomplete"):
            suggestions.append(
                "Increase chunk size / context window and add few-shot examples "
                "showing complete answers to improve completeness."
            )
        if categories.get("off_topic"):
            suggestions.append(
                "Strengthen intent detection and add topic guardrails to keep "
                "answers on-subject."
            )

        # Ensure at least 3 actionable suggestions.
        fallback = [
            "Expand the golden dataset with more edge cases to catch failures earlier.",
            "Add an automated re-ranking step to improve retrieval precision.",
            "Tune retrieval top-k and use hybrid search to improve context recall.",
            "Introduce regression tests in CI/CD to block deploys on score drops.",
        ]
        for s in fallback:
            if len(suggestions) >= 3:
                break
            if s not in suggestions:
                suggestions.append(s)

        return suggestions


# ---------------------------------------------------------------------------
# Entry point for manual testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    qa_pairs = [
        QAPair(
            question="What is RAG?",
            expected_answer="RAG stands for Retrieval-Augmented Generation, which combines retrieval with text generation.",
            context="RAG is a technique that retrieves relevant documents and uses them to ground LLM generation.",
            metadata={"difficulty": "easy", "category": "definition"},
        ),
        QAPair(
            question="What is the capital of France?",
            expected_answer="Paris is the capital of France.",
            context="France is a country in Western Europe. Its capital city is Paris.",
            metadata={"difficulty": "easy", "category": "factual"},
        ),
    ]

    evaluator = RAGASEvaluator()
    runner = BenchmarkRunner()

    def mock_agent(question: str) -> str:
        return f"Based on my knowledge: {question[:30]}... The answer involves key concepts."

    results = runner.run(qa_pairs, mock_agent, evaluator)
    report = runner.generate_report(results)
    print("=== Benchmark Report ===")
    for k, v in report.items():
        print(f"  {k}: {v}")

    failures = runner.identify_failures(results, threshold=0.5)
    print(f"\n=== Failures ({len(failures)}) ===")
    analyzer = FailureAnalyzer()
    categories = analyzer.categorize_failures(failures)
    print("Failure Categories:", categories)

    for f in failures:
        print(f"  Root cause: {analyzer.find_root_cause(f)}")

    suggestions = analyzer.generate_improvement_suggestions(failures)
    print("\nImprovement Suggestions:")
    for s in suggestions:
        print(f"  - {s}")

    log = analyzer.generate_improvement_log(failures, suggestions)
    print("\n=== Improvement Log ===")
    print(log)
