"""Quality gate for generated investment memo DOCX files.

The memo skill may keep detailed source provenance in analysis artifacts and
in a dedicated source/fact index. The final memo body and operating tables
should not expose those internal tokens.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from server import memo_structure
from typing import Any, Iterable


@dataclass(frozen=True)
class MemoLintFinding:
    severity: str
    code: str
    location: str
    snippet: str
    suggestion: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MemoLintResult:
    path: str
    findings: list[MemoLintFinding]

    @property
    def p0_findings(self) -> list[MemoLintFinding]:
        return [finding for finding in self.findings if finding.severity == "P0"]

    @property
    def has_blocking_findings(self) -> bool:
        return bool(self.p0_findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": "failed" if self.has_blocking_findings else "passed",
            "finding_count": len(self.findings),
            "p0_count": len(self.p0_findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class _TextBlock:
    kind: str
    text: str
    location: str
    section: str
    allowed_trace_section: bool
    operating_table: bool
    # Full text of the table row this cell belongs to (empty for paragraphs).
    # Lets the disclosure-gap check see implication supplied in a sibling cell —
    # e.g. a "Value: Not disclosed" cell whose "Note" cell carries the risk.
    row_text: str = ""


_BRACKET_RE = re.compile(r"\[[^\[\]\n]{1,100}\]")
_CITATION_TOKEN_RE = re.compile(r"\[(?:[SC]\d+)(?:\s*,\s*[SC]\d+)*\]")
_SOURCE_ID_RE = re.compile(r"s\d+(?:\s*[,;]\s*s\d+)*", re.IGNORECASE)
_SOURCE_BRACKET_KEYWORDS = (
    "wv",
    "spv",
    "memo",
    "companies.yaml",
    "internal",
    "source",
    "trace",
    "yaml",
    "claim",
    "packet",
)
_GAP_PHRASE_RE = re.compile(r"\bnot disclosed\b|\bnot computable\b", re.IGNORECASE)
_GAP_NOISE_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "to",
    "of",
    "or",
    "and",
    "for",
    "any",
    "period",
    "value",
    "metric",
    "n",
    "a",
    "na",
    "none",
    "unknown",
    "tbd",
}
_ALLOWED_SECTION_PATTERNS = (
    re.compile(r"\bsources?\b.*\b(source classes?|fact reference index|references?)\b", re.IGNORECASE),
    re.compile(r"\bfact reference index\b", re.IGNORECASE),
    re.compile(r"\bvalidation\b.*\bassumptions?\b", re.IGNORECASE),
    re.compile(r"\bvalidation appendix\b", re.IGNORECASE),
)
_INTERNAL_ARTIFACT_PATTERNS = (
    re.compile(r"\bcompanies\.ya?ml\b", re.IGNORECASE),
    re.compile(r"\bmemo_packet(?:\.md)?\b", re.IGNORECASE),
    re.compile(r"\bsource_traces?\b", re.IGNORECASE),
    re.compile(r"\bclaim_register(?:\.md)?\b", re.IGNORECASE),
    re.compile(r"\bresearch_tasks?\b", re.IGNORECASE),
    re.compile(r"\breviewer_prompts?\b", re.IGNORECASE),
    re.compile(r"\bchart_specs?\b", re.IGNORECASE),
    re.compile(r"\binfographic_source_brief\b", re.IGNORECASE),
    re.compile(r"\bbenchmark_dashboard\b", re.IGNORECASE),
)
_SCAFFOLD_PATTERNS = (
    re.compile(r"\bCritical Reality Check\b", re.IGNORECASE),
    re.compile(r"\bpresent-state\b", re.IGNORECASE),
    re.compile(r"\bupside-state\b", re.IGNORECASE),
    re.compile(r"\bupside-only\b", re.IGNORECASE),
    re.compile(r"\bStrongest independent support\b", re.IGNORECASE),
    re.compile(r"\bStrongest independent supporting facts\b", re.IGNORECASE),
    re.compile(r"\bStrongest disconfirming facts\b", re.IGNORECASE),
    re.compile(r"\bStill unproven\b", re.IGNORECASE),
    re.compile(r"\bAlready true\b.*\b(upside|today)\b", re.IGNORECASE),
)
_PACKET_PROCESS_LABEL_PATTERNS = (
    re.compile(r"\bPrompt\s*:", re.IGNORECASE),
    re.compile(r"\bDesign prompt\b", re.IGNORECASE),
    re.compile(r"\bReviewer prompts?\b", re.IGNORECASE),
    re.compile(r"\bNarrative reviewer prompts?\b", re.IGNORECASE),
    # A copied packet label is "Confidence: High" — the label plus a
    # rating. Bare "confidence:" fires on ordinary prose punctuation
    # ("...with much confidence: at $2T the...") and survived THREE
    # repair attempts in a live run because no rewording removes a colon
    # the writer cannot see as the trigger.
    re.compile(
        r"\bConfidence\s*:\s*(?:very\s+)?(?:high|medium|moderate|low|\d)",
        re.IGNORECASE,
    ),
    re.compile(r"\bSource traces?\b", re.IGNORECASE),
    re.compile(r"\bsource[-_ ]trace notes?\b", re.IGNORECASE),
    re.compile(r"\bNo-go\b", re.IGNORECASE),
    re.compile(r"\bprohibited visual\b", re.IGNORECASE),
    re.compile(r"\bMust-prove\b", re.IGNORECASE),
    # A copied packet HEADER reads "Benchmark Gaps" on its own line or
    # followed by a colon. Bare "benchmark gap" is the ordinary English
    # for a measured performance difference, and AI-infrastructure memos
    # are required to produce exactly that — the ai_infra type file tells
    # the competitive pass to "Benchmark against NVIDIA's own stack ...
    # and the leading open-source engines". On the 2026-09-17 RadixArk
    # run this rejected "the benchmark gap on unique-prompt traffic is
    # already 1-4%", the correct term for the thing being analysed, and
    # was the memo's only P0. Same failure as the bare "confidence:"
    # above: the writer cannot see what the trigger is.
    re.compile(r"^\s*Benchmark gaps?\s*:?\s*$", re.IGNORECASE),
    re.compile(r"\bBenchmark gaps?\s*:", re.IGNORECASE),
    re.compile(r"\bReadiness Reviews?\b", re.IGNORECASE),
    re.compile(r"\bWaivers?\b", re.IGNORECASE),
    re.compile(r"\bMemo Uses?\b", re.IGNORECASE),
    re.compile(r"\bPre-Mortem\b", re.IGNORECASE),
    re.compile(r"\bReverse IC\b", re.IGNORECASE),
    re.compile(r"\bValidation\s*&\s*Assumptions Log\b", re.IGNORECASE),
    re.compile(r"\bsupport thresholds?\b", re.IGNORECASE),
    re.compile(r"\bconfirmation evidence\b", re.IGNORECASE),
    re.compile(r"\btop\s+gating\s+questions\b", re.IGNORECASE),
)
_FUZZY_PATTERNS = (
    re.compile(r"\bsoft instrument\b", re.IGNORECASE),
    re.compile(r"\bhard IP wall\b", re.IGNORECASE),
    re.compile(r"\bmoat narrows\b", re.IGNORECASE),
    re.compile(r"\bno-rights SAFE\b", re.IGNORECASE),
    re.compile(r"\bwhere nothing else works\b", re.IGNORECASE),
    re.compile(r"\bleast-proven part of the story\b", re.IGNORECASE),
)
# The memo's conclusion is a recommendation — no decision exists when it is
# written. Decided-action constructions are banned, EXCEPT inside a sentence
# recording an actual past decision (the pinned decision-history sentence
# "BSH made the decision to ... on ... because ...", whose user-entered
# reason may itself contain decided phrasing). The exemption is
# sentence-scoped and keyed on the history markers, which the pin template
# guarantees are present in the one legitimate sentence.
_DECIDED_LANGUAGE_PATTERNS = (
    re.compile(
        r"\bBSH is (?:committing|investing|participating)\b", re.IGNORECASE
    ),
    re.compile(
        r"\bBSH is not (?:committing|investing|participating)\b",
        re.IGNORECASE,
    ),
)
_DECISION_HISTORY_SENTENCE_PATTERN = re.compile(
    r"[^.!?]*(?:\bmade the decision\b|\bdecided (?:on|to)\b)[^.!?]*[.!?]?",
    re.IGNORECASE,
)

_SELL_SIDE_BANNED_PATTERNS = (
    re.compile(
        r"\bthe recommendation (?:is|should|would|must|remain|remains)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bthe current recommendation posture\b", re.IGNORECASE),
    re.compile(r"\bthe right posture is\b", re.IGNORECASE),
    re.compile(r"\bthe opportunity offered to investors is\b", re.IGNORECASE),
    re.compile(r"\bthe base case credits\b", re.IGNORECASE),
    re.compile(r"\bthe investment view is\b", re.IGNORECASE),
    re.compile(r"\bwe invest behind\b", re.IGNORECASE),
    re.compile(r"\bwe back\b(?!-)", re.IGNORECASE),
    re.compile(r"\bwe want exposure\b", re.IGNORECASE),
    re.compile(r"\bwhy we want exposure\b", re.IGNORECASE),
    re.compile(r"\bwe are being offered\b", re.IGNORECASE),
    re.compile(r"\bwe are participating through\b", re.IGNORECASE),
    re.compile(r"\bwe recommend participating\b", re.IGNORECASE),
    # The same slogans negated read as the same generated copy; the
    # positive patterns above let "We do not recommend participating"
    # through (R19). memo_analysis's voice rewrite should mirror these.
    re.compile(
        r"\bwe (?:do not|don't|would not|wouldn't) recommend participating\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bwe are not being offered\b", re.IGNORECASE),
    re.compile(r"\bwe are not participating (?:through|via)\b", re.IGNORECASE),
    re.compile(r"\bwe give credit to\b", re.IGNORECASE),
    re.compile(r"\bour base case credits\b", re.IGNORECASE),
    re.compile(r"\bour base case gives credit\b", re.IGNORECASE),
    re.compile(r"\bthe investment case rests on\b", re.IGNORECASE),
    re.compile(r"\bthe investment case uses\b", re.IGNORECASE),
    re.compile(r"\bthe investment case treats\b", re.IGNORECASE),
    re.compile(r"\bthe investment case assumes\b", re.IGNORECASE),
    re.compile(r"\bthe investment case identifies\b", re.IGNORECASE),
    re.compile(r"\bthe investment case gives credit\b", re.IGNORECASE),
    re.compile(r"\bvaluation-support factor\b", re.IGNORECASE),
    re.compile(r"\bvaluation support is strongest\b", re.IGNORECASE),
    re.compile(r"\brather than treating\b", re.IGNORECASE),
    re.compile(r"\bkey risk centers on\b", re.IGNORECASE),
    re.compile(r"\bis compelling because\b", re.IGNORECASE),
    re.compile(r"\bavailable evidence does not document\b", re.IGNORECASE),
    re.compile(r"\bcontrol layer underneath\b", re.IGNORECASE),
    re.compile(r"\bonly scaled platform\b", re.IGNORECASE),
    re.compile(r"\bas framed\b", re.IGNORECASE),
    re.compile(r"\bframed (?:A2|terms|economics|round)\b", re.IGNORECASE),
    re.compile(r"\bon the framed\b", re.IGNORECASE),
    re.compile(r"\bdecision posture\b", re.IGNORECASE),
    re.compile(r"\brecommendation posture\b", re.IGNORECASE),
    re.compile(r"\bopen questions\b", re.IGNORECASE),
    re.compile(r"\btop\s+3\s+(?:decision|gating)\s+questions\b", re.IGNORECASE),
    re.compile(r"\(for BSH\)", re.IGNORECASE),
    # Deal-context underwriting only: "we underwrite", "the underwriting
    # case/posture". The bare profession noun ("insurance underwriters
    # use the product") is legitimate domain content — the blanket ban
    # locked a live Anthropic run in an unfixable repair loop
    # (2026-09-11: customer-evidence prose about underwriters).
    re.compile(
        r"\b(?:we|bsh)\s+underwrit(?:e|es|ing|ten)\b"
        r"|\bunderwriting\s+(?:case|view|posture|assumption|basis|lens)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\btickets?\b", re.IGNORECASE),
    re.compile(r"\bBSH target allocation\b", re.IGNORECASE),
    re.compile(r"\btarget allocation\b", re.IGNORECASE),
    re.compile(r"\bposition size\b", re.IGNORECASE),
    re.compile(r"\bBSH should\b", re.IGNORECASE),
    re.compile(r"\bwhat BSH should do\b", re.IGNORECASE),
    re.compile(r"\bkill criteria\b", re.IGNORECASE),
    re.compile(r"\bNeed More Information\b", re.IGNORECASE),
    re.compile(r"\bConditional Yes\b", re.IGNORECASE),
    re.compile(r"\bProceed if confirmed\b", re.IGNORECASE),
    re.compile(r"\bHold pending confirmation\b", re.IGNORECASE),
    re.compile(r"\bwe proceed once\b", re.IGNORECASE),
    re.compile(r"\bwe would proceed if\b", re.IGNORECASE),
    re.compile(r"\bwe would revisit if\b", re.IGNORECASE),
    re.compile(r"\bwe recommend proceeding if\b", re.IGNORECASE),
    re.compile(r"\bwe recommend proceeding once\b", re.IGNORECASE),
    re.compile(r"\bproceed only after\b", re.IGNORECASE),
    re.compile(r"\b(?:proceed|participate|recommend)[^.]{0,80}\bsubject to\b", re.IGNORECASE),
    re.compile(r"\bClosing Confirmations?\b", re.IGNORECASE),
    re.compile(r"\bClosing Confirmation Bars?\b", re.IGNORECASE),
    re.compile(r"\bWhat Must Be Confirmed\b", re.IGNORECASE),
    re.compile(r"\bConfirmation Items?\b", re.IGNORECASE),
    re.compile(r"\bExpected Bars?\b", re.IGNORECASE),
    re.compile(r"\bValuation Sensitivity Bars?\b", re.IGNORECASE),
    re.compile(r"\bInvestment Conditions?\b", re.IGNORECASE),
    re.compile(r"\bStop or Revisit Conditions?\b", re.IGNORECASE),
    re.compile(r"\bStop\s*/\s*Revisit Triggers?\b", re.IGNORECASE),
    re.compile(r"\bWhat Would Make Us Revisit\b", re.IGNORECASE),
    re.compile(r"\bImmediate Confirmation Work\b", re.IGNORECASE),
    re.compile(r"\bClosing bar\b", re.IGNORECASE),
    re.compile(r"^\s*Cross-check\b", re.IGNORECASE),
    re.compile(r"^\s*Source two\b", re.IGNORECASE),
    re.compile(r"^\s*Request\b", re.IGNORECASE),
    re.compile(r"^\s*Commission\b", re.IGNORECASE),
    re.compile(r"^\s*Patent counsel\b", re.IGNORECASE),
    re.compile(r"\binvestment conditions?\b", re.IGNORECASE),
    re.compile(r"\bconfirm before funding\b", re.IGNORECASE),
    re.compile(r"^\s*Confirm\b", re.IGNORECASE),
    re.compile(r"\bbefore signing subscription documents\b", re.IGNORECASE),
    re.compile(r"\bwe still need\b", re.IGNORECASE),
    re.compile(r"\bneed to confirm\b", re.IGNORECASE),
    re.compile(r"\brequire (?:the )?(?:split|signed-vs-MOU split)\b", re.IGNORECASE),
    re.compile(r"\bdiligence actions?\b", re.IGNORECASE),
    re.compile(r"\bDiligence Thresholds\b", re.IGNORECASE),
    re.compile(r"\bdiligence thresholds?\b", re.IGNORECASE),
    re.compile(r"\bNext Diligence Actions\b", re.IGNORECASE),
    re.compile(r"\bsupport thresholds?\b", re.IGNORECASE),
    # A named lead is a checklist item when the memo DEMANDS one, and
    # evidence when it names what would change the call — which is what
    # a pass or watch verdict is required to state, and what a risk
    # card's "What we watch" row is FOR. Live on 2026-09-20 the Surge AI
    # memo lost two P0s to "a closed priced round with a named
    # institutional lead", the plainest available wording for the signal
    # it was asked to name. Fires as a demand or as a line-initial
    # label, not inside prose.
    re.compile(
        r"(?:^\s*"
        r"|\b(?:conditions?|requirements?|gates?|thresholds?)\s*:\s*"
        r"(?:\w+\s+){0,3}"
        r"|\b(?:requires?|required|requiring|needs?|needed|confirm|"
        r"conditional(?:\s+on)?|contingent\s+on|subject\s+to|pending|"
        r"before)\s+(?:\w+\s+){0,3})"
        r"named\s+(?:institutional\s+)?lead\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bdown-?round protection\b", re.IGNORECASE),
    re.compile(r"\bMFN\b"),
    re.compile(r"\brequire data room\b", re.IGNORECASE),
    re.compile(r"\b(?:should|would|could|ought to) be able to\b", re.IGNORECASE),
    re.compile(r"\bshould be closeable\b", re.IGNORECASE),
    re.compile(r"\brealistically obtainable\b", re.IGNORECASE),
    re.compile(r"\bbefore BSH funds\b", re.IGNORECASE),
    re.compile(r"\bkeep (?:the )?(?:position|allocation|check|ticket) small\b", re.IGNORECASE),
    re.compile(r"\blate-stage financial-return exception\b", re.IGNORECASE),
    re.compile(r"\bfinancial-return exception\b", re.IGNORECASE),
    re.compile(r"\bthesis-fit exception", re.IGNORECASE),
    re.compile(r"\bBSH preference\b", re.IGNORECASE),
    re.compile(r"\bAsian-immigrant\b", re.IGNORECASE),
    re.compile(r"\bAsian ethnicity preferred\b", re.IGNORECASE),
    re.compile(r"\bimmigrant background founders\b", re.IGNORECASE),
    re.compile(r"\bpaper-mark outcome\b", re.IGNORECASE),
    re.compile(r"\bflat-to-modest carry\b", re.IGNORECASE),
)
# Nouns that turn "document" into a modifier rather than a name for this
# memo — a document store is a product, not a self-reference.
_DOCUMENT_COMPOUND_NOUNS = (
    r"(?:stores?|repositor(?:y|ies)|corpus|corpora|indexe?s?|librar(?:y|ies)|"
    r"set|sets|collections?|databases?|intelligence|management|search|"
    r"retrieval|understanding|processing|extraction|ingestion|classification|"
    r"pipelines?|workflows?|types?|formats?|sources?|volume|volumes|count|"
    r"counts|AI|Q&A)\b"
)


_META_LANGUAGE_PATTERNS = (
    re.compile(r"\b(?:the|this|our) memo\b", re.IGNORECASE),
    re.compile(r"\b(?:the|this|our) analysis\b", re.IGNORECASE),
    re.compile(r"\b(?:the|this|our) framework\b", re.IGNORECASE),
    # Scaffold references only ("This section examines...", "in this
    # section, we..."): the answer-first register legitimately writes
    # "the strongest number in the section" and "every other risk in
    # this section works through that channel" — both burned repair
    # cycles in a live full run.
    re.compile(
        r"\b(?:the|this) section,?\s+(?:we|will|discusses|examines|covers|"
        r"outlines|reviews|summari[sz]es|analy[sz]es|addresses|turns|"
        r"presents|explores)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bour section\b", re.IGNORECASE),
    # "document" naming the memo itself, never "document" modifying the
    # noun after it. Glean sells enterprise document search, so "the
    # document stores", "the document index", "this document corpus" are
    # its product — and the gate read them as the memo talking about
    # itself. Live on 2026-09-20 that failed a whole package attempt no
    # repair agent could have cleared, because the prose was right.
    re.compile(
        r"\b(?:the|this|our) document\b(?!\s+" + _DOCUMENT_COMPOUND_NOUNS + r")",
        re.IGNORECASE,
    ),
    re.compile(r"\bmemo language was\b", re.IGNORECASE),
    re.compile(r"\bthe sponsor (?:itself )?(?:implies|frames|flags)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:the )?sponsor (?:itself |explicitly )?(?:acknowledges|discloses)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\binside the memo\b", re.IGNORECASE),
    re.compile(r"\bsource material\b", re.IGNORECASE),
    re.compile(r"\bembedded in the registry\b", re.IGNORECASE),
    re.compile(r"\bthe registry\b", re.IGNORECASE),
    re.compile(
        r"\bwe (?:will )?(?:outline|discuss|summari[sz]e|cover|frame|review|walk through)\b",
        re.IGNORECASE,
    ),
)
_RISK_GENERIC_WATCH_RE = re.compile(
    r"^\s*(?:monitor|track|watch|confirm|request|obtain|"
    r"cross[- ]check|verify|require|ensure|validate|ask for)\b",
    re.IGNORECASE,
)
_RISK_GENERIC_HEADINGS = {
    "commercial risk",
    "competition risk",
    "execution risk",
    "financing risk",
    "liquidity risk",
    "market risk",
    "regulatory risk",
    "technology risk",
    "valuation risk",
}
_RISK_GENERIC_FILLER_PATTERNS = (
    re.compile(r"\bcompetition is a risk\b", re.IGNORECASE),
    re.compile(r"\bexecution could be difficult\b", re.IGNORECASE),
    re.compile(r"\bmarket conditions may change\b", re.IGNORECASE),
    re.compile(r"\bthere are risks?\b", re.IGNORECASE),
    re.compile(r"\bthe company faces risks?\b", re.IGNORECASE),
)
# Contractual service levels a company either offers or does not: "guaranteed
# SLAs", "guaranteed uptime". The word names a product term there, not a
# promise the memo is making, and the rule below must not read it as one —
# live on 2026-09-20 a RadixArk risk card said the company shows no evidence
# of "guaranteed production SLAs", which is the rule's own suggestion already
# followed, and the finding survived three attempts and two surgical repairs
# because there was nothing to repair.
_SERVICE_LEVEL_NOUNS = (
    r"SLAs?|uptime|availability|capacity|throughput|latency|"
    r"service[- ]levels?|response times?|delivery"
)
_RISK_UNSUPPORTED_CLAIM_RE = re.compile(
    r"\b(?:guaranteed(?!\s+(?:\w+\s+)?(?:" + _SERVICE_LEVEL_NOUNS + r")\b)"
    r"|certain to|will definitely|cannot fail|"
    r"no competitor can)\b",
    re.IGNORECASE,
)
_BODY_TREATMENT_SPEAK_PATTERNS = (
    re.compile(r"\bsource class\b", re.IGNORECASE),
    re.compile(r"\bmodel treatment\b", re.IGNORECASE),
)

# The mandatory legal-disclosure sentence necessarily says "this document"
# — the renderer's `disclosures` component REQUIRES this language, so the
# meta-language gate must not fight it (it forced a surgical-repair round
# on both 2026-08-28 benchmark runs). Markers mirror the renderer's
# disclosures-component coverage patterns in memo_docx_renderer.
_DISCLOSURE_LANGUAGE_PATTERNS = (
    re.compile(r"\bnot an offer to (?:sell|purchase)\b", re.IGNORECASE),
    # The commonest legal phrasing of the same sentence — "does not
    # constitute an offer to buy or sell, nor a solicitation of an offer
    # to purchase" — was the one finding left on a live Gemini run.
    re.compile(
        r"\b(?:does not|do not|shall not|not) constitute an offer\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bsolicitation of an offer\b", re.IGNORECASE),
    re.compile(r"\boffer to sell securities\b", re.IGNORECASE),
    re.compile(r"\bdefinitive subscription documents\b", re.IGNORECASE),
    re.compile(r"\baccredited investors\b", re.IGNORECASE),
    re.compile(r"\bpartial or total loss\b", re.IGNORECASE),
)


# Internal plumbing the memo may READ but must never cite. A reader has
# no idea what "the registry" is, and naming it presents an internal
# lookup as though it were a public source. 2026-09-17, RadixArk run 3:
# the writer found a good formulation for "we looked everywhere and
# found nothing" — "no figure exists in the launch release, the company
# blog, the registry or any press coverage we reviewed" — and reused it
# across four sections, five findings in one memo. The surgical repair
# saw the generic self-reference advice, which offered rewrites for "this
# memo" and "the analysis" and said nothing about the registry, and left
# every one of them in place.
_INTERNAL_SOURCE_RE = re.compile(
    r"\b(?:the registry|embedded in the registry|source material)\b",
    re.IGNORECASE,
)

_META_SUGGESTION_SELF = (
    "Delete the self-reference and keep the judgment: "
    '"every multiple in this memo" -> "every multiple we use"; '
    '"the margin risk that carries this memo" -> "the margin risk that '
    'carries the investment case"; "What the gap costs the analysis" -> '
    '"What the gap costs us". Never name the memo, the analysis, the '
    "document, the framework or the section — name the investment "
    "instead. Table headers and table cells count."
)

_META_SUGGESTION_INTERNAL = (
    "Never cite our own plumbing as a source. The registry and the "
    "source packet are internal inputs the reader cannot see, so naming "
    'them presents a lookup as evidence: "no figure exists in the launch '
    'release, the company blog, the registry or any press coverage we '
    'reviewed" -> "no figure exists in the launch release, the company '
    'blog or any press coverage we reviewed". Name public sources only, '
    "and drop the internal one from the list."
)


def _meta_language_suggestion(match_text: str) -> str:
    """Advice that fits the phrase actually matched."""
    if _INTERNAL_SOURCE_RE.search(match_text):
        return _META_SUGGESTION_INTERNAL
    return _META_SUGGESTION_SELF


def lint_memo_docx(
    path: str | Path,
    structure: memo_structure.MemoStructure | None = None,
    *,
    sizing_supplied: bool | None = None,
    deal_terms_on_file: bool | None = None,
    hurdle_moic: float | None = None,
    pinned_values: Iterable[str] | None = None,
) -> MemoLintResult:
    """Lint one generated memo DOCX and return structured findings.

    ``structure`` names the report structure the memo was rendered
    against (heading recognizers, the risk section key); default late v1.

    The keyword-only run facts feed NON-BLOCKING findings (P1/P2 — never
    a P0, so they never trigger a repair or fail a gate):

    - ``sizing_supplied``: whether an input gave BSH's check size. Anything
      but True flags a dollar amount after "BSH commits" (invented sizing).
    - ``deal_terms_on_file``: False flags SPV / SAFE / vehicle assertions
      (None — unknown — skips the check).
    - ``hurdle_moic``: the firm's target MOIC for the run's stage, when a
      policy is saved; flags a commit recommendation whose base-case MOIC
      (the scenario table's MOIC column) starts below it.
    - ``pinned_values``: pinned figures ("$1.2B", "1.5x") the pin-echo gate
      requires in several places; exempt from the repetition count.
    """
    structure = structure or memo_structure.LATE
    docx_path = Path(path)
    try:
        blocks = _extract_docx_blocks(docx_path, structure)
    except Exception as exc:  # noqa: BLE001
        return MemoLintResult(
            path=str(docx_path),
            findings=[
                MemoLintFinding(
                    severity="P0",
                    code="docx_extract_error",
                    location="document",
                    snippet=f"{type(exc).__name__}: {exc}",
                    suggestion=(
                        "Generate a valid DOCX before marking the memo ready."
                    ),
                )
            ],
        )
    findings = _lint_blocks(blocks, structure)
    findings.extend(
        _advisory_findings(
            blocks,
            sizing_supplied=sizing_supplied,
            deal_terms_on_file=deal_terms_on_file,
            hurdle_moic=hurdle_moic,
            pinned_values=pinned_values,
            v2=bool(structure.scorecard_weights()),
        )
    )
    return MemoLintResult(path=str(docx_path), findings=_dedupe_findings(findings))


def render_markdown_report(result: MemoLintResult) -> str:
    """Render a compact human-readable lint artifact."""
    payload = result.to_dict()
    lines = [
        "# Memo Quality Lint",
        "",
        f"- source: `{payload['path']}`",
        f"- status: {payload['status']}",
        f"- p0_count: {payload['p0_count']}",
        f"- finding_count: {payload['finding_count']}",
        "",
    ]
    if not result.findings:
        lines.append("No findings.")
        return "\n".join(lines).strip() + "\n"

    lines += [
        "| Severity | Code | Location | Snippet | Suggestion |",
        "|---|---|---|---|---|",
    ]
    for finding in result.findings:
        lines.append(
            "| "
            f"{_md_cell(finding.severity)} | "
            f"{_md_cell(finding.code)} | "
            f"{_md_cell(finding.location)} | "
            f"{_md_cell(finding.snippet)} | "
            f"{_md_cell(finding.suggestion)} |"
        )
    return "\n".join(lines).strip() + "\n"


def banned_body_voice_phrase(text: str) -> str | None:
    """The first body-voice phrase this gate will reject, or None.

    The same patterns `_lint_blocks` applies to body prose, exposed so a
    gate that runs EARLIER can ask the same question. A pin that fails
    here cannot be repaired later: the echo gate requires the pinned
    sentence verbatim in every place it appears, so a banned phrase
    inside one is a P0 the sections are forbidden to fix. Live on
    2026-09-20 the Glean spine pinned "...and BSH should move when..."
    and the memo shipped with three copies of it, after three package
    attempts and three surgical repairs that never had a legal move.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    for pattern in _SELL_SIDE_BANNED_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    if not any(
        pattern.search(text) for pattern in _DISCLOSURE_LANGUAGE_PATTERNS
    ):
        for pattern in _META_LANGUAGE_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(0)
    return None


def _extract_docx_blocks(
    path: Path,
    structure: memo_structure.MemoStructure | None = None,
) -> list[_TextBlock]:
    structure = structure or memo_structure.LATE
    from docx import Document  # type: ignore
    from docx.oxml.table import CT_Tbl  # type: ignore
    from docx.oxml.text.paragraph import CT_P  # type: ignore
    from docx.table import Table  # type: ignore
    from docx.text.paragraph import Paragraph  # type: ignore

    document = Document(path)
    blocks: list[_TextBlock] = []
    section = "front matter"
    paragraph_index = 0
    table_index = 0

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            # Renderer-derived restatements (the page-one decision summary,
            # the contents list, table footnotes) are linted where their
            # text first appears, never twice.
            if memo_structure.is_derived_docx_element(child):
                continue
            paragraph = Paragraph(child, document)
            text = _clean_text(memo_structure.docx_paragraph_text(paragraph))
            if not text:
                continue
            paragraph_index += 1
            section = _section_after_heading(text, section, structure)
            allowed = _allowed_trace_section(section)
            blocks.append(
                _TextBlock(
                    kind="paragraph",
                    text=text,
                    location=f"paragraph {paragraph_index}",
                    section=section,
                    allowed_trace_section=allowed,
                    operating_table=False,
                )
            )
        elif isinstance(child, CT_Tbl):
            table_index += 1
            if memo_structure.is_derived_docx_element(child):
                continue
            table = Table(child, document)
            allowed = _allowed_trace_section(section)
            for row_index, row in enumerate(table.rows, start=1):
                row_text = _clean_text(
                    " ".join(memo_structure.docx_cell_text(cell) for cell in row.cells)
                )
                for col_index, cell in enumerate(row.cells, start=1):
                    text = _clean_text(memo_structure.docx_cell_text(cell))
                    if not text:
                        continue
                    blocks.append(
                        _TextBlock(
                            kind="table_cell",
                            text=text,
                            location=(
                                f"table {table_index} row {row_index} "
                                f"cell {col_index}"
                            ),
                            section=section,
                            allowed_trace_section=allowed,
                            operating_table=not allowed,
                            row_text=row_text,
                        )
                    )
    return blocks


def _lint_blocks(
    blocks: list[_TextBlock],
    structure: memo_structure.MemoStructure | None = None,
) -> list[MemoLintFinding]:
    structure = structure or memo_structure.LATE
    risk_section_key = structure.numbered_lint_key("risk")
    findings: list[MemoLintFinding] = []
    # Structure-v2 memos cite sources and calculation notes inline as
    # [S3] / [C2] (rendered as links); v1 memos keep ids in the index.
    citations_allowed = bool(structure.scorecard_weights())
    for block in blocks:
        if not block.allowed_trace_section:
            for match in _BRACKET_RE.finditer(block.text):
                if citations_allowed and _CITATION_TOKEN_RE.fullmatch(
                    match.group(0)
                ):
                    continue
                if _source_like_bracket(match.group(0)):
                    findings.append(
                        _finding(
                            block,
                            "P0",
                            (
                                "operating_table_source_token"
                                if block.operating_table
                                else "source_token_leak"
                            ),
                            match.group(0),
                            (
                                "Move detailed source IDs to the fact reference "
                                "index and name the person, contract, or "
                                "publication in the body."
                            ),
                        )
                    )

            for pattern in _INTERNAL_ARTIFACT_PATTERNS:
                match = pattern.search(block.text)
                if match:
                    findings.append(
                        _finding(
                            block,
                            "P0",
                            "internal_artifact_leak",
                            match.group(0),
                            (
                                "Remove internal file or artifact names from the "
                                "body and operating tables."
                            ),
                        )
                    )

            for pattern in _PACKET_PROCESS_LABEL_PATTERNS:
                match = pattern.search(block.text)
                if match:
                    findings.append(
                        _finding(
                            block,
                            "P0",
                            "packet_process_label",
                            match.group(0),
                            (
                                "Convert copied packet or review labels into "
                                "investor-facing evidence, source-treatment, "
                                "risk, or valuation language."
                            ),
                        )
                    )

        for pattern in _SCAFFOLD_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "scaffold_label",
                        match.group(0),
                        "Rewrite prompt taxonomy as investor-facing prose.",
                    )
                )

        for pattern in _FUZZY_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "banned_fuzzy_phrase",
                        match.group(0),
                        "Replace clever shorthand with concrete deal mechanics.",
                    )
                )

        # The Sources index describes how each source shaped the memo —
        # "which is why the recommendation is capped at..." is treatment
        # language there, not body voice (two live source cells burned a
        # repair cycle on exactly that).
        for pattern in (
            () if block.allowed_trace_section else _SELL_SIDE_BANNED_PATTERNS
        ):
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "sell_side_voice_violation",
                        match.group(0),
                        (
                            "Rewrite buyer-side, detached, treatment-speak, or "
                            "stock participation slogans as LP co-invest "
                            "English: firm as subject, named terms, plain risks."
                        ),
                    )
                )
                break

        decided_scope = _DECISION_HISTORY_SENTENCE_PATTERN.sub(" ", block.text)
        for pattern in _DECIDED_LANGUAGE_PATTERNS:
            match = pattern.search(decided_scope)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "decided_voice_violation",
                        match.group(0),
                        (
                            "The memo's conclusion is a recommendation, not a "
                            "decision: write 'Recommendation: BSH commits ...' "
                            "or 'Recommendation: pass on ...'. Decided "
                            "language is allowed only in the pinned "
                            "decision-history sentence."
                        ),
                    )
                )
                break

        block_is_disclosure_language = any(
            pattern.search(block.text)
            for pattern in _DISCLOSURE_LANGUAGE_PATTERNS
        )
        if not block_is_disclosure_language:
            for pattern in _META_LANGUAGE_PATTERNS:
                match = pattern.search(block.text)
                if not match:
                    continue
                # The Sources / Fact Reference Index and validation
                # appendix describe the memo's own sourcing by definition —
                # article and demonstrative references ("the memo
                # carries…", "figures in this memo", "the registry fields
                # are not used") are treatment language there, not process
                # leakage; the sources contract itself asks how "the memo
                # weighs and uses this source". Possessive/process forms
                # ("our analysis", "we will outline") stay banned
                # everywhere — a live compact run lost a full regeneration
                # cycle to "in this memo" flagged inside the sources table.
                if block.allowed_trace_section and match.group(0).lower().startswith(
                    ("the ", "this ")
                ):
                    continue
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "meta_process_language",
                        match.group(0),
                        _meta_language_suggestion(match.group(0)),
                    )
                )
                break

        if not block.allowed_trace_section:
            for pattern in _BODY_TREATMENT_SPEAK_PATTERNS:
                match = pattern.search(block.text)
                if match:
                    findings.append(
                        _finding(
                            block,
                            "P0",
                            "sell_side_voice_violation",
                            match.group(0),
                            (
                                "Name the person, contract, or publication. "
                                "Put source class in the fact index."
                            ),
                        )
                    )
                    break

        if (
            not block.allowed_trace_section
            and _unresolved_disclosure_gap(block.text, block.row_text)
        ):
            findings.append(
                _finding(
                    block,
                    "P0",
                    "disclosure_gap_without_treatment",
                    "not disclosed",
                    (
                        "A bare 'Not disclosed' cell is unfinished. Add the "
                        "implication in the same cell or the note cell: "
                        "'Revenue is not disclosed. $3.0B is high relative "
                        "to disclosed commercial proof.'"
                    ),
                )
            )

    risk_headings: dict[str, _TextBlock] = {}
    for index, block in enumerate(blocks):
        if block.section != risk_section_key:
            continue
        for pattern in _RISK_GENERIC_FILLER_PATTERNS:
            match = pattern.search(block.text)
            if match:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "generic_risk_filler",
                        match.group(0),
                        "Replace generic risk language with a named fact, failure mode, and consequence.",
                    )
                )
        match = _RISK_UNSUPPORTED_CLAIM_RE.search(block.text)
        if match:
            findings.append(
                _finding(
                    block,
                    "P0",
                    "unsupported_risk_claim",
                    match.group(0),
                    "State the evidence behind the risk or qualify it as an inference.",
                )
            )
        if block.kind == "paragraph" and re.match(
            r"^\s*risk\s+\d+\s*[:：]\s*\S", block.text, re.IGNORECASE
        ):
            summary = block.text.split(":", 1)[-1].strip()
            normalized = re.sub(r"[^a-z0-9]+", " ", summary.lower()).strip()
            if summary.lower().strip(" .") in _RISK_GENERIC_HEADINGS:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "generic_risk_heading",
                        summary,
                        "Name the concrete failure mode, not only the risk category.",
                    )
                )
            if normalized in risk_headings:
                findings.append(
                    _finding(
                        block,
                        "P0",
                        "duplicate_risk_card",
                        summary,
                        "Combine duplicate risks or distinguish their failure modes.",
                    )
                )
            else:
                risk_headings[normalized] = block
        if (
            block.kind == "table_cell"
            and block.text.lower().strip() == "what we watch"
            and index + 1 < len(blocks)
        ):
            watch = blocks[index + 1]
            if watch.section == block.section and _RISK_GENERIC_WATCH_RE.match(
                watch.text
            ):
                findings.append(
                    _finding(
                        watch,
                        "P0",
                        "risk_watch_checklist",
                        watch.text,
                        "Name an observable operating or transaction signal, not a confirmation command.",
                    )
                )

    return _dedupe_findings(findings)


# ---- advisory findings (P1 / P2 — never blocking) ---------------------------
#
# Things a reader should hear about but no repair loop may chase: every
# finding below is P1 or P2, so the gate status stays "passed", nothing is
# retried on them, and old memos re-linted only gain notes. Each code is
# capped so one noisy memo cannot bury the report.

_ADVISORY_CAP = 8

# A dollar amount right after "BSH commits": BSH's check size, which only an
# input may supply (the 2026-09-18 ZaiNar memo committed an invented $15M).
_SIZING_AMOUNT_RE = re.compile(
    r"\bBSH\s+commits\s+(?:up\s+to\s+|about\s+|approximately\s+|roughly\s+"
    r"|~\s*)?(?:US)?[$€£¥]\s?\d",
    re.IGNORECASE,
)
# BSH's own vehicle, instrument or allocation, asserted while the run has
# no deal terms on file. SPV / SAFE are matched in capitals only.
_DEAL_VEHICLE_RE = re.compile(r"\b(?:SPV|SAFEs?)\b")
_DEAL_VEHICLE_PHRASE_RE = re.compile(
    r"\b(?:the|this|our|BSH's|BSH)\s+(?:co-invest(?:ment)?\s+)?vehicle\b"
    r"|\b(?:BSH's|our)\s+allocation\b",
    re.IGNORECASE,
)
_NO_TERMS_MARKERS = ("no vehicle or terms on file", "to be determined by ic")
_COMMIT_RECOMMENDATION_RE = re.compile(
    r"\bRecommendation:\s*BSH\s+commits\b", re.IGNORECASE
)
_MOIC_VALUE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*x\b", re.IGNORECASE)
_CELL_LOCATION_RE = re.compile(r"^table (\d+) row (\d+) cell (\d+)$")
# A figure that carries a unit: money, a percentage or a multiple. Bare
# integers (years, scores, counts) are not figures for these checks.
_NUMBER_TOKEN_RE = re.compile(
    r"(?:US)?[$€£¥]\s?\d[\d,]*(?:\.\d+)?"
    r"(?:\s?(?:[KMBT]|bn|mn|million|billion|trillion)\b)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:%|x\b)",
    re.IGNORECASE,
)
_NUMBER_UNIT_WORDS = (
    ("trillion", "t"),
    ("billion", "b"),
    ("million", "m"),
    ("bn", "b"),
    ("mn", "m"),
)
# More than this many uses of one figure inside one body section is
# restatement, not argument (pinned figures are exempt).
_REPEAT_LIMIT = 2
# "rather than" and ", not X": the English habit the Chinese memo mirrors
# as 而非 (54 and 56 of them in one live pair). Idioms such as ", not yet"
# or ", not only" are not contrasts.
_CONTRAST_RE = re.compile(
    r"\brather than\b"
    r"|,\s+not\s+(?!yet\b|only\b|least\b|just\b|all\b|necessarily\b"
    r"|disclosed\b|including\b|to\b)\w",
    re.IGNORECASE,
)
_CONTRAST_PER_THOUSAND = 2.0
_CONTRAST_MIN_COUNT = 3
# Risk-card row labels repeat across cards by design.
_RISK_CARD_ROW_LABELS = frozenset(
    {
        "risk type",
        "verdict",
        "impact",
        "why it matters",
        "what we watch",
        "mitigation",
        "likelihood",
        "risk rating",
    }
)


def _normalize_number_token(token: str) -> str:
    value = re.sub(r"[\s,]", "", token.lower())
    for word, short in _NUMBER_UNIT_WORDS:
        if value.endswith(word):
            return value[: -len(word)] + short
    return value


def _number_tokens(text: str) -> list[str]:
    return [
        _normalize_number_token(match.group(0))
        for match in _NUMBER_TOKEN_RE.finditer(text or "")
    ]


def _is_body_block(block: _TextBlock) -> bool:
    return not block.allowed_trace_section and block.section != "front matter"


def _is_disclosure_block(block: _TextBlock) -> bool:
    return any(pattern.search(block.text) for pattern in _DISCLOSURE_LANGUAGE_PATTERNS)


def _table_cells(
    blocks: list[_TextBlock],
) -> dict[int, dict[int, dict[int, _TextBlock]]]:
    """table index -> row index -> column index -> cell block."""
    tables: dict[int, dict[int, dict[int, _TextBlock]]] = {}
    for block in blocks:
        if block.kind != "table_cell":
            continue
        match = _CELL_LOCATION_RE.match(block.location)
        if not match:
            continue
        table, row, col = (int(part) for part in match.groups())
        tables.setdefault(table, {}).setdefault(row, {})[col] = block
    return tables


def _advisory_finding(
    code: str,
    severity: str,
    location: str,
    snippet: str,
    suggestion: str,
) -> MemoLintFinding:
    return MemoLintFinding(
        severity=severity,
        code=code,
        location=location,
        snippet=_clean_text(snippet)[:240],
        suggestion=suggestion,
    )


def _sizing_findings(blocks: list[_TextBlock]) -> list[MemoLintFinding]:
    findings: list[MemoLintFinding] = []
    for block in blocks:
        if block.allowed_trace_section:
            continue
        match = _SIZING_AMOUNT_RE.search(block.text)
        if match:
            findings.append(
                _finding(
                    block,
                    "P1",
                    "sizing_without_input",
                    match.group(0),
                    (
                        "No BSH check size was supplied for this run, so the "
                        "recommendation names no amount: 'Recommendation: BSH "
                        "commits to <target> at <terms>.' A dollar figure "
                        "after 'BSH commits' is invented sizing."
                    ),
                )
            )
    return findings[:_ADVISORY_CAP]


def _deal_vehicle_findings(blocks: list[_TextBlock]) -> list[MemoLintFinding]:
    findings: list[MemoLintFinding] = []
    for block in blocks:
        if not _is_body_block(block) or _is_disclosure_block(block):
            continue
        lowered = block.text.lower()
        if any(marker in lowered for marker in _NO_TERMS_MARKERS):
            continue
        match = _DEAL_VEHICLE_RE.search(block.text) or _DEAL_VEHICLE_PHRASE_RE.search(
            block.text
        )
        if match:
            findings.append(
                _finding(
                    block,
                    "P1",
                    "deal_vehicle_without_terms",
                    match.group(0),
                    (
                        "No deal terms are on file for this run, so the memo "
                        "cannot assert a BSH vehicle, instrument or "
                        "allocation. Describe the round as the sources report "
                        "it; the deal-terms table says 'No vehicle or terms on "
                        "file'."
                    ),
                )
            )
    return findings[:_ADVISORY_CAP]


def _base_case_moic(blocks: list[_TextBlock]) -> float | None:
    """The lower bound of the base scenario's MOIC, read from a table with a
    MOIC column and a row labelled Base; None when no such table exists."""
    for rows in _table_cells(blocks).values():
        header = rows.get(min(rows)) if rows else None
        if not header:
            continue
        moic_cols = [
            col
            for col, cell in header.items()
            if re.search(r"\bmoic\b", cell.text, re.IGNORECASE)
        ]
        if not moic_cols:
            continue
        for row_index in sorted(rows):
            row = rows[row_index]
            first = row.get(min(row)) if row else None
            if first is None or not re.match(r"\s*base\b", first.text, re.IGNORECASE):
                continue
            cell = row.get(moic_cols[0])
            match = _MOIC_VALUE_RE.search(cell.text) if cell else None
            if match:
                return float(match.group(1))
    return None


def _hurdle_findings(
    blocks: list[_TextBlock], hurdle_moic: float
) -> list[MemoLintFinding]:
    base = _base_case_moic(blocks)
    if base is None or base >= hurdle_moic:
        return []
    for block in blocks:
        if block.allowed_trace_section:
            continue
        match = _COMMIT_RECOMMENDATION_RE.search(block.text)
        if match:
            return [
                _finding(
                    block,
                    "P1",
                    "recommendation_below_hurdle",
                    match.group(0),
                    (
                        f"The base case returns {base:g}x, below the firm's "
                        f"{hurdle_moic:g}x hurdle for this stage, yet the "
                        "recommendation commits. State the comparison and the "
                        "price at which the base case clears the hurdle, or "
                        "change the call."
                    ),
                )
            ]
    return []


def _duplicate_row_findings(blocks: list[_TextBlock]) -> list[MemoLintFinding]:
    findings: list[MemoLintFinding] = []
    seen: dict[tuple[str, frozenset[str]], int] = {}
    for table_index, rows in sorted(_table_cells(blocks).items()):
        for row_index in sorted(rows):
            row = rows[row_index]
            first = row.get(min(row)) if row else None
            if first is None or not _is_body_block(first):
                continue
            label = re.sub(r"[^a-z0-9]+", " ", first.text.lower()).strip()
            if not label or label in _RISK_CARD_ROW_LABELS:
                continue
            numbers = frozenset(
                token
                for col, cell in row.items()
                if col != min(row)
                for token in _number_tokens(cell.text)
            )
            if not numbers:
                continue
            key = (label, numbers)
            earlier = seen.setdefault(key, table_index)
            if earlier != table_index:
                findings.append(
                    _finding(
                        first,
                        "P1",
                        "duplicate_table_row",
                        first.text,
                        (
                            "This row repeats a row of an earlier table with "
                            "the same figures. Keep each headline number in "
                            "one table (the Key Metrics Snapshot) and point to "
                            "it from the others."
                        ),
                    )
                )
    return findings[:_ADVISORY_CAP]


def _repetition_findings(
    blocks: list[_TextBlock], pinned: set[str]
) -> list[MemoLintFinding]:
    counts: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for block in blocks:
        if not _is_body_block(block) or _is_disclosure_block(block):
            continue
        # Prose only. A table repeats a figure per row by design (the
        # scenario table's per-case dilution, a column of "Not disclosed"
        # dates), and that is layout, not restatement; duplicate rows across
        # tables have their own check above.
        if block.kind == "table_cell":
            continue
        for token in _number_tokens(block.text):
            if token in pinned:
                continue
            key = (block.section, token)
            if key not in counts:
                order.append(key)
            counts[key] = counts.get(key, 0) + 1
    findings = [
        _advisory_finding(
            "number_repeated_in_section",
            "P1",
            section,
            f"{token} appears {counts[(section, token)]} times in {section}",
            (
                "State each figure once, in the passage that argues it, and "
                "refer back to it elsewhere in the section instead of "
                "restating it. Pinned figures the pin sheet requires are "
                "exempt."
            ),
        )
        for section, token in order
        if counts[(section, token)] > _REPEAT_LIMIT
    ]
    return findings[:_ADVISORY_CAP]


def _contrast_density_findings(blocks: list[_TextBlock]) -> list[MemoLintFinding]:
    words = 0
    contrasts = 0
    for block in blocks:
        if not _is_body_block(block):
            continue
        words += len(block.text.split())
        contrasts += len(_CONTRAST_RE.findall(block.text))
    if not words or contrasts < _CONTRAST_MIN_COUNT:
        return []
    density = contrasts * 1000 / words
    if density <= _CONTRAST_PER_THOUSAND:
        return []
    return [
        _advisory_finding(
            "rather_than_density",
            "P2",
            "document",
            (
                f"{contrasts} 'rather than' / ', not X' contrasts in {words} "
                f"words ({density:.1f} per 1,000)"
            ),
            (
                "Say what a thing is before what it is not, and keep "
                "contrasts for where the contrast is the point — about two "
                "per thousand words. The Chinese memo mirrors each one as 而非."
            ),
        )
    ]


def _advisory_findings(
    blocks: list[_TextBlock],
    *,
    sizing_supplied: bool | None = None,
    deal_terms_on_file: bool | None = None,
    hurdle_moic: float | None = None,
    pinned_values: Iterable[str] | None = None,
    v2: bool = False,
) -> list[MemoLintFinding]:
    """The non-blocking P1/P2 findings (see lint_memo_docx). ``v2`` marks
    a memo whose structure cites inline ([S#] / [C#]); the estimate-
    discipline check runs only there."""
    findings: list[MemoLintFinding] = []
    if sizing_supplied is not True:
        findings.extend(_sizing_findings(blocks))
    if deal_terms_on_file is False:
        findings.extend(_deal_vehicle_findings(blocks))
    if hurdle_moic is not None and hurdle_moic > 0:
        findings.extend(_hurdle_findings(blocks, float(hurdle_moic)))
    findings.extend(_duplicate_row_findings(blocks))
    pinned = {
        token for value in (pinned_values or ()) for token in _number_tokens(str(value))
    }
    findings.extend(_repetition_findings(blocks, pinned))
    findings.extend(_contrast_density_findings(blocks))
    findings.extend(_restatement_findings(blocks, pinned))
    if v2:
        findings.extend(_figure_anchor_findings(blocks))
    return findings


# ---- estimate discipline and cross-section restatement (2026-09-23) ----------
#
# Report-only. A v2 memo carries [S#] / [C#] on every figure it asserts;
# a sentence with a figure and neither is an estimate the reader cannot
# trace (the Gemini v1 memo's "8 to 10 months of runway" came from no
# source). And a sentence — or a figure with its metric — that the memo
# says again in section after section is restatement, not argument (the
# 2026-09-23 v2 draft restated "2.2x", "1.73x" and "no named customer"
# across most of its sections).

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[$])")
_ANCHOR_MIN_WORDS = 6
_RESTATED_MIN_WORDS = 8
_CLAIM_SECTIONS = 3
_FIGURE_SECTIONS = 4
_METRIC_WORD_RE = re.compile(
    r"\b(arr|mrr|revenue|sales|bookings|billings|growth|margin|customers?|"
    r"clients?|users?|employees?|headcount|valuation|tam|sam|som|cagr|ebitda|"
    r"profit|income|loss|cash|burn|runway|funding|raised|round|contracts?|"
    r"backlog|churn|retention|patents?|multiple|moic|irr|price|exit|ev|"
    r"dilution|ownership|stake|discount|hurdle|return|entry|mark|proceeds)\b",
    re.IGNORECASE,
)
# A sentence that says the figure is NOT on file is the anchor the
# prompts prescribe for an unanchorable figure ("Not disclosed — no
# document on file"); glossary definitions render as a table (cells are
# never checked).
_NOT_DISCLOSED_RE = re.compile(
    r"\bnot (?:disclosed|computable|available|on file|verified)\b|\bno document on file\b",
    re.IGNORECASE,
)
# The renderer prints a citation as a superscript link carrying the bare
# id ("2.2x C3", "revenue S5,S6"); the docx text has no brackets.
_ANCHOR_RE = re.compile(r"(?:\[[SC]\d+(?:\s*,\s*[SC]\d+)*\]|(?<![A-Za-z0-9-])[SC]\d+(?![A-Za-z0-9-]))")


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END_RE.split(text or "") if part.strip()]


def _specific_figure(token: str) -> bool:
    """A figure that identifies itself: a multiple ("2.2x", "1.73x") or a
    number with three or more significant digits ("$579.37m", "$118.4m").
    Round figures ("$1b", "20%") need the metric word beside them."""
    if token.endswith("x"):
        return True
    digits = re.sub(r"[^0-9]", "", token).lstrip("0").rstrip("0")
    return len(digits) >= 3


def _sentence_key(sentence: str) -> str:
    clean = _CITATION_TOKEN_RE.sub(" ", sentence.lower())
    clean = re.sub(r"[^a-z0-9$%. ]+", " ", clean)
    return re.sub(r"\s+", " ", clean).strip()


def _figure_anchor_findings(blocks: list[_TextBlock]) -> list[MemoLintFinding]:
    """P1 ``figure_without_anchor``: a body-prose sentence in a v2 memo
    that states a figure ($, %, x) and cites neither a source nor a
    calculation note. Table cells and the sources / calculation sections
    are not prose; "not disclosed" is not a figure."""
    findings: list[MemoLintFinding] = []
    total = 0
    for block in blocks:
        if not _is_body_block(block) or block.kind == "table_cell":
            continue
        for sentence in _sentences(block.text):
            if len(sentence.split()) < _ANCHOR_MIN_WORDS:
                continue
            if _ANCHOR_RE.search(sentence):
                continue
            tokens = _number_tokens(sentence)
            if not tokens or _NOT_DISCLOSED_RE.search(sentence):
                continue
            total += 1
            if len(findings) < _ADVISORY_CAP:
                findings.append(
                    _finding(
                        block,
                        "P1",
                        "figure_without_anchor",
                        tokens[0] if tokens[0] in sentence else sentence[:40],
                        (
                            "Every figure carries a [S#] source or a [C#] "
                            "calculation note in the same sentence; a figure "
                            "with neither is written as 'not disclosed'."
                        ),
                    )
                )
    if total > len(findings) and findings:
        first = findings[0]
        findings[0] = MemoLintFinding(
            severity=first.severity,
            code=first.code,
            location=first.location,
            snippet=first.snippet,
            suggestion=first.suggestion + f" ({total} such sentences in all)",
        )
    return findings


def _restatement_findings(
    blocks: list[_TextBlock], pinned: set[str]
) -> list[MemoLintFinding]:
    """P1 ``claim_restated``: one sentence (8+ words, normalised) in three
    or more sections. P2 ``figure_restated_across_sections``: one figure
    with the same metric word beside it in four or more sections. Pinned
    figures the pin sheet requires everywhere are exempt from the figure
    check, not from the sentence check (a pin is echoed once per section
    by design; three sections is the owner's limit for anything else)."""
    sentence_sections: dict[str, dict[str, str]] = {}
    figure_sections: dict[tuple[str, str], dict[str, str]] = {}
    for block in blocks:
        if not _is_body_block(block) or _is_disclosure_block(block):
            continue
        section = block.section
        for sentence in _sentences(block.text):
            key = _sentence_key(sentence)
            if len(key.split()) >= _RESTATED_MIN_WORDS:
                sentence_sections.setdefault(key, {}).setdefault(section, block.location)
            if block.kind == "table_cell":
                continue
            metric_spans = [
                (m.start(), m.end(), m.group(1).lower())
                for m in _METRIC_WORD_RE.finditer(sentence)
            ]
            for match in _NUMBER_TOKEN_RE.finditer(sentence):
                token = _normalize_number_token(match.group(0))
                if token in pinned:
                    continue
                if _specific_figure(token):
                    metric = ""
                elif metric_spans:
                    # The metric word nearest the figure names it.
                    metric = min(
                        metric_spans,
                        key=lambda span: min(
                            abs(span[0] - match.end()), abs(match.start() - span[1])
                        ),
                    )[2]
                else:
                    continue
                figure_sections.setdefault((token, metric), {}).setdefault(
                    section, block.location
                )
    findings: list[MemoLintFinding] = []
    by_spread = sorted(
        sentence_sections.items(), key=lambda item: -len(item[1])
    )
    for key, sections in by_spread:
        if len(sections) < _CLAIM_SECTIONS:
            continue
        findings.append(
            _advisory_finding(
                "claim_restated",
                "P1",
                next(iter(sections.values())),
                f"\"{key[:120]}\" appears in {len(sections)} sections: "
                + ", ".join(list(sections)[:5]),
                (
                    "Say it once, in the section that argues it, and refer "
                    "back to it elsewhere. A pinned sentence is echoed at most "
                    "once per section."
                ),
            )
        )
        if len(findings) >= _ADVISORY_CAP:
            break
    figure_findings: list[MemoLintFinding] = []
    figures_by_spread = sorted(
        figure_sections.items(), key=lambda item: -len(item[1])
    )
    for (token, metric), sections in figures_by_spread:
        if len(sections) < _FIGURE_SECTIONS:
            continue
        figure_findings.append(
            _advisory_finding(
                "figure_restated_across_sections",
                "P2",
                next(iter(sections.values())),
                f"{token}{f' ({metric})' if metric else ''} is stated in {len(sections)} sections: "
                + ", ".join(list(sections)[:6]),
                (
                    "State the figure where it is argued and refer to it "
                    "elsewhere; the executive summary and the decision may "
                    "each carry it once."
                ),
            )
        )
        if len(figure_findings) >= _ADVISORY_CAP:
            break
    return findings + figure_findings


def _section_after_heading(
    text: str,
    current: str,
    structure: memo_structure.MemoStructure | None = None,
) -> str:
    structure = structure or memo_structure.LATE
    lowered = text.strip().lower()
    if _allowed_trace_section(lowered):
        return lowered
    if len(text) <= 140 and (
        structure.numbered_prefix_pattern().match(lowered)
        or lowered in structure.lint_section_titles()
    ):
        return lowered
    return current


def _allowed_trace_section(section: str) -> bool:
    return any(pattern.search(section or "") for pattern in _ALLOWED_SECTION_PATTERNS)


def _source_like_bracket(value: str) -> bool:
    inner = value.strip()[1:-1].strip()
    lowered = inner.lower()
    if _SOURCE_ID_RE.fullmatch(inner):
        return True
    return any(keyword in lowered for keyword in _SOURCE_BRACKET_KEYWORDS)


def _substance_remainder(text: str) -> str:
    remainder = _GAP_PHRASE_RE.sub(" ", text.lower())
    remainder = re.sub(r"[^a-z0-9$]+", " ", remainder)
    words = [word for word in remainder.split() if word not in _GAP_NOISE_WORDS]
    return " ".join(words)


def _unresolved_disclosure_gap(text: str, row_text: str = "") -> bool:
    cell = text.lower().strip()
    if not _GAP_PHRASE_RE.search(cell):
        return False
    if _substance_remainder(cell):
        return False
    if not row_text:
        return True
    row_without_cell = row_text.lower().replace(cell, " ", 1)
    return len(_substance_remainder(row_without_cell)) < 20


def _finding(
    block: _TextBlock,
    severity: str,
    code: str,
    match_text: str,
    suggestion: str,
) -> MemoLintFinding:
    return MemoLintFinding(
        severity=severity,
        code=code,
        location=f"{block.location} ({block.section})",
        snippet=_snippet(block.text, match_text),
        suggestion=suggestion,
    )


def _snippet(text: str, match_text: str, *, radius: int = 100) -> str:
    clean = _clean_text(text)
    index = clean.lower().find(match_text.lower())
    if index < 0:
        return clean[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(clean), index + len(match_text) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}".strip()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe_findings(findings: list[MemoLintFinding]) -> list[MemoLintFinding]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[MemoLintFinding] = []
    for finding in findings:
        key = (finding.code, finding.location, finding.snippet)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Lint generated memo DOCX output.")
    parser.add_argument("docx_path", type=Path)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    lint_result = lint_memo_docx(args.docx_path)
    if args.markdown:
        print(render_markdown_report(lint_result))
    else:
        print(json.dumps(lint_result.to_dict(), indent=2, ensure_ascii=False))
    raise SystemExit(1 if lint_result.has_blocking_findings else 0)
