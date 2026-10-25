"""Orchestrator: file -> Report (HLD 3.2).

``Resources`` holds everything slow to load (classifier, embedder, LLM provider, cache) so the
backend loads it once at startup (HLD 10.2) and the CLI loads it once per run. ``run`` reports
progress through ``progress_cb(stage, pct)`` with the stage names of HLD 10.1.

Failure policy (HLD 16): ingestion errors and a missing classifier stop the run with a readable
error; a missing embedder or a failing LLM only add warnings, and the report is still produced.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from contractguard.classification.classifier import ClauseClassifier, load_classifier
from contractguard.config import Settings, get_settings
from contractguard.embeddings.service import Embedder, try_load_embedder
from contractguard.extraction.document import extract_meta
from contractguard.extraction.facts import extract_facts
from contractguard.ingestion.router import load_document
from contractguard.llm.base import LLMProvider
from contractguard.llm.explainer import Explainer, LLMCache, make_provider
from contractguard.models import PipelineStage, Report
from contractguard.policy.engine import PolicyEngine
from contractguard.policy.schema import load_policy
from contractguard.preprocessing.cleaner import clean_document
from contractguard.report.builder import build_report
from contractguard.segmentation.segmenter import segment

log = logging.getLogger(__name__)

ProgressCallback = Callable[[PipelineStage, int], None]


@dataclass
class Options:
    contract_type: str | None = None  # None or "auto" -> detect
    our_org_name: str | None = None
    policy_id: str | None = None
    use_llm: bool = True


@dataclass
class Resources:
    classifier: ClauseClassifier
    embedder: Embedder | None
    provider: LLMProvider | None
    cache: LLMCache
    settings: Settings
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def load(
        cls,
        settings: Settings | None = None,
        with_embeddings: bool = True,
        with_llm: bool = True,
        cache_path: str | Path | None = None,
    ) -> Resources:
        settings = settings or get_settings()
        warnings = []
        embedder = try_load_embedder(settings) if with_embeddings else None
        if with_embeddings and embedder is None:
            warnings.append(
                "Embedding model unavailable: semantic checks and the embedding fallback were "
                "skipped, so possible MISSING clauses were not cross-checked."
            )
        classifier = load_classifier(settings, embedder)
        provider = make_provider(settings) if with_llm else None
        return cls(classifier, embedder, provider, LLMCache(cache_path), settings, warnings)


def run(
    path: str | Path,
    options: Options | None = None,
    resources: Resources | None = None,
    progress_cb: ProgressCallback | None = None,
    contract_id: str | None = None,
    filename: str | None = None,
) -> Report:
    options = options or Options()
    resources = resources or Resources.load(with_llm=options.use_llm)
    settings = resources.settings
    progress = progress_cb or (lambda stage, pct: None)
    timings: dict[str, float] = {}
    warnings = list(resources.warnings)
    path = Path(path)

    def timed(name: str, t0: float) -> None:
        timings[name] = time.perf_counter() - t0

    t = time.perf_counter()
    progress("EXTRACTING", 5)
    doc = load_document(path, settings)
    cleaned = clean_document(doc)
    timed("extract", t)

    t = time.perf_counter()
    progress("SEGMENTING", 30)
    clauses = segment(cleaned, doc)
    timed("segment", t)

    t = time.perf_counter()
    progress("CLASSIFYING", 45)
    clauses = resources.classifier.classify(clauses)
    timed("classify", t)

    t = time.perf_counter()
    progress("EVALUATING", 65)
    policy = load_policy(options.policy_id or settings.policy.default_policy_id)
    our_org = options.our_org_name or policy.our_org_default or settings.org.default_name
    user_type = options.contract_type if options.contract_type not in (None, "auto") else None
    meta = extract_meta(clauses, our_org, user_type, settings.org.date_order)
    if not any(p.role != "UNKNOWN" for p in meta.parties):
        warnings.append(
            "Party roles could not be resolved; role-dependent rules may need review. "
            "Check the 'our organization' name."
        )
    facts = extract_facts(clauses, meta.parties)
    findings = PolicyEngine(policy, resources.embedder, settings).evaluate(
        meta.contract_type, clauses, facts
    )
    timed("evaluate", t)

    t = time.perf_counter()
    progress("EXPLAINING", 80)
    provider = resources.provider if options.use_llm else None
    explainer = Explainer(provider, resources.cache, settings)
    try:
        findings = explainer.explain_findings(findings, policy.rules, clauses, meta)
        summary = explainer.executive_summary(findings, meta.contract_type)
    except Exception as exc:  # never lose the report over explanations
        log.exception("Explanation stage failed")
        warnings.append(f"AI explanations failed ({type(exc).__name__}); templates were used.")
        explainer = Explainer(None, resources.cache, settings)
        findings = explainer.explain_findings(findings, policy.rules, clauses, meta)
        summary = explainer.template_summary(findings)
    if options.use_llm and provider is None:
        warnings.append("AI explanations are off (no LLM configured); template explanations used.")
    elif provider is not None and explainer.stats["template"] and explainer.stats["llm"] == 0:
        warnings.append("The LLM did not return usable explanations; template explanations used.")
    timed("explain", t)

    report = build_report(
        contract_id=contract_id or uuid.uuid4().hex,
        filename=filename or path.name,
        doc=doc,
        meta=meta,
        clauses=clauses,
        findings=findings,
        policy=policy,
        executive_summary=summary,
        warnings=warnings,
        llm_used=explainer.stats["llm"] > 0,
        timings_s=timings,
        settings=settings,
    )
    progress("DONE", 100)
    return report
