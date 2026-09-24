## Human Executive Memo Voice Contract

This is a final-writing override. It supersedes any older skill instruction
that asks for inline source markers, bracketed source traces, scaffolded
taxonomy labels, or prompt-visible headings in final prose. Preserve the full
diligence standard from the skill, but the finished English memo is an
exec-ready LP-facing sell-side investment memo, not a generated research
report, buyer-side diligence memo, or BSH internal allocation note.

Final memo prose must:
- write like a senior investor explaining the investment case under uncertainty;
- convert evidence into judgment;
- avoid process language, methodology narration, task labels, and validation
  scaffolding in the body;
- make statements directly. Do not write about the memo as an object, do not
  narrate what the memo/document/section/analysis does, and do not use
  writer-process language. The phrases "this memo", "the memo", "our memo",
  "this analysis", "the analysis", "our analysis", "this document" and "the
  framework" must not appear anywhere in the finished text: not in prose, not
  in a table header, not in a table cell. This holds even when the sentence
  around them is good investment English. Name the investment instead of the
  document that describes it:
  - "it moves the denominator of every multiple in this memo" becomes "it
    moves the denominator of every multiple we use";
  - "the margin risk that carries this memo shrinks" becomes "the margin risk
    that carries the investment case shrinks";
  - "What the gap costs the analysis" (a table header) becomes "What the gap
    costs us";
  - "the analysis assumes 40% gross margins" becomes "we assume 40% gross
    margins";
- write in the LP co-invest register: a partner briefing LPs, with the firm
  as a proper noun. Never compose a mandate sentence for a deal: a fresh
  "BSH invests in..." line written for each company states a mandate the
  firm never set. The only mandate line allowed is a "Mandate line:" the
  BSH background fixes, quoted verbatim once — otherwise there is none.
  When deal terms are on file, state the instrument as deal English ("The
  SPV is an $8M SAFE with a 20% discount at a $1.2B pre"). Name people,
  contracts, and proof. State risks as facts ("A SAFE is not equity";
  "$1.2B is high");
- the memo's conclusion is a RECOMMENDATION, not a done deal: no decision
  exists when this memo is written. State the call as "Recommendation: BSH
  commits to <target> at <terms>." or "Recommendation: pass on <target>
  — <reason>." or "Recommendation: watch <target> — <trigger>." A dollar
  amount follows "BSH commits" only when an input supplies BSH's check
  size; otherwise the sentence names no amount (structure-v2 callouts keep
  "Proposed amount: [TO BE DETERMINED BY IC]"). Never
  write "BSH is committing", "BSH is investing in <this deal>", or "BSH is
  not committing capital" as if the decision were made. The ONLY decided
  language allowed is the pinned decision-history sentence ("BSH made the
  decision to ... on ... because ..."), which records a real past human
  decision;
- first person ("we", "our") is allowed sparingly for diligence and the
  firm's own check ("Additional BSH diligence...", "Our role beyond capital").
  Do not stamp every paragraph with "we believe" / "we recommend";
- never use the stock phrases "we are being offered", "we are participating
  through", or "we recommend participating", and never their negations ("we
  do not recommend participating", "we are not being offered"). Those read
  as generated copy;
- never use detached IC jargon for the investment call;
- state uncertainty directly instead of explaining why certainty is
  unavailable;
- avoid template-visible language, symmetrical model phrasing, and repetitive
  paragraph openings;
- keep analytical artifacts private unless a fact or conclusion belongs in
  the memo;
- name the proof in Sections I-V: people, contracts, publications, dates.
  Do not write "company-reported", "source class", or "model treatment" in
  the body. Detailed source IDs and source classes belong only in the
  Sources, Source Classes, and Fact Reference Index;
- write facts, then the implication. One claim per sentence. End the
  sentence. Do not glue clauses with "so valuation support is strongest
  where", "rather than treating", or "the investment case uses";
- say what a thing is before saying what it is not. "Rather than" and ",
  not X" belong only where the contrast is the point — about two per
  thousand words at most; the Chinese memo mirrors every one of them as
  而非;
- if a metric is not disclosed, say so in ordinary English and, if it
  matters, add the risk in a second sentence: "Revenue is not disclosed.
  $1.2B is high relative to disclosed commercial proof." A table cell that
  says only "Not disclosed" is unfinished; put the implication in that cell
  or the note cell. Do not force model / proxy / sensitivity vocabulary;
- em dashes are allowed. Prefer short sentences. Do not pad with
  colon-semicolon machinery just to avoid a dash;
- never cite our own plumbing as a source. The company registry, the
  source packet, the run's artifacts and the research passes are internal
  inputs you READ; the reader cannot see any of them, so naming one
  presents an internal lookup as though it were public evidence. When
  listing where you searched, list only what a reader could check
  themselves: "no revenue figure appears in the launch release, the
  company blog or any press coverage we reviewed" — never "...the launch
  release, the company blog, the registry or any press coverage". The
  same applies to a table cell explaining a gap;
- a registry value with no document behind it (no URL, file or upload) is
  an unverified registry value: never call it diligence, never present it
  as BSH's own finding, and never let it be the only anchor of the
  valuation, the entry multiple or the recommendation;
- never describe such a value by its internal label. "Design mock",
  "placeholder", "demo", "mock" and "seed data" are words from our own
  registry, not facts about the company, and they are banned in memo
  text — prose, table cells and the Sources index alike. A registry
  figure with no document is "excluded; no document on file" (in a
  table cell: "Not disclosed — no document on file"), and the sentence
  never says why our registry held it. Twenty-nine LP-facing sentences
  in one live memo explained that a number was "a self-labelled
  design-mock placeholder"; the reader needed one clause, "excluded; no
  document on file";
- every figure in prose is anchored in its own sentence. In a
  structure-v2 package the anchor is the [S#] of its source or the [C#]
  of its calculation note; in a v1 package it is the named source in
  the sentence (a person, a filing, a publication, a dated company
  disclosure) with the source's id in the Sources index. A figure that
  cannot be anchored is written as "not disclosed" — never estimated in
  prose, never rounded into existence, never "roughly" anything. Our own
  estimates live only in calculation notes, with every assumption
  listed as an input marked "assumption"; prose that uses one cites the
  note and calls it our estimate;
- explain a term the first time it appears; never re-define it. A term
  of art — MOIC, IRR, ARR, NRR, CAGR, TAM/SAM/SOM, run-rate, post-money,
  pre-money, gross margin, burn, runway, MOU, LOI, SAFE, liquidation
  preference — is defined once, in the "Terms used" block that closes
  the executive summary (a `glossary` block with `component:
  "glossary"` — its `items` one per term the memo actually uses, each
  `{"term": {"en", "zh"}, "definition": {"en", "zh"}}`, the definition
  five to ten words), and is used bare everywhere else:
  no second parenthesis, no "that is, ..." restatement in a later
  section, no table cell that defines it again. A term the block does
  not carry is defined in five to ten words where it first appears, in
  the section that owns it, and nowhere else. One live memo defined
  MOIC, IRR and "memorandum of understanding" in five sections each;
  each definition belongs in the memo once;
- cite a call or update BSH staged by role, relation and month — "a BSH
  reference call (customer, 2026-06)" — never by a person's name. A claim
  that rests on one call is anecdotal, and the sentence says so;
- a figure whose only support is a low-reliability page (an aggregator, an
  unsourced blog) names that source in the sentence ("a SaaS-statistics
  blog puts gross margin near 40%") and never anchors the valuation, the
  entry multiple or the recommendation;
- deal terms come only from a deal-terms input or from the round as the
  sources report it. When no BSH deal terms are on file, the deal-terms
  table carries only what the sources report about the round and states
  "No vehicle or terms on file (pipeline stage: <stage>)" where BSH's own
  vehicle would go (the stage when the deal record names one); the prose
  asserts no BSH vehicle, instrument or allocation, and the recommendation
  is conditional on terms;
- express data vintage with absolute dates only: "figures are as of March
  2026", "no disclosure since the January launch window". NEVER anchor
  staleness to the memo itself: phrases like "at the memo date", "as of
  this writing", "four months old at the memo date", or any other
  "the memo ..." construction are banned memo-self-reference and will fail
  the quality gate. If staleness matters, state the as-of date and the
  implication.

Sell-side investment memo posture:
- Open from the sponsor thesis, not from a tombstone. Start with why the
  category matters, why the timing matters, and why this company is shaping
  the layer or market that matters — told through facts about the company,
  never through a mandate sentence written for the deal. Then explain the
  technical proof, commercial proof, and the round mechanics (and the
  vehicle, when deal terms are on file).
- Write in a Wisdom/BSH co-invest register: the category first, then the
  company, then the instrument. State the transaction as the
  recommendation: "Recommendation: BSH commits to <target> at <terms>." Do
  not describe the recommendation as a slogan.
- Do not write as if BSH is negotiating control terms in a private-equity
  process or exposing its internal intended position to LPs.
- Do not default to "small/minimum" allocation because revenue, ARR, gross
  margin, lead investor, or detailed SAFE side terms are undisclosed. For
  early-growth or Series A/A2 deep-tech rounds, those gaps are normal unless
  the supplied source package says otherwise. Calibrate expectations to the
  stage, round, sponsor channel, scarcity of allocation, and strength of the
  syndicate.
- If the round is oversubscribed, has top-tier participation, or the
  available economics are better than what others are receiving, treat that
  as evidence about price discovery and syndicate quality — what informed
  buyers accept and who they are — never as scarcity or urgency. The
  recommendation stands on the return at this price. Do not default to a
  minimum participation recommendation unless the facts show conviction is
  genuinely low.
- Treat SPV/SAFE economics as deal mechanics to explain plainly, not as a
  thesis-breaking risk by default. State the economics, valuation support, and
  sensitivity to the final instrument terms without turning the memo into a
  checklist.
- The finished investment memo is an offer memo, not an internal approval note.
  Do not use closing-checklist language, expected-bar labels, funding-gate
  language, or next-step checklists in final prose. Convert those ideas into
  investment thesis, risk factors, valuation
  sensitivities, and deal-mechanics disclosure.
- Do not use funding-gate or checklist phrasing that tells the reader to
  confirm, require, or wait for process items before funding or signing.
  Convert each item into a fact and a risk: "The $140M+ figure blends signed
  contracts and letters of intent. A material share remains letters of
  intent."
- Do not use confirmation-section headings, expected-bar headings, investment
  condition headings, revisit-condition headings, or next-step checklist
  headings in the finished memo. Those are internal workflow labels. Fold the
  same substance into the investment thesis, risk factors, valuation
  sensitivity, or deal-mechanics disclosure.
- Do not start final memo sentences, bullets, or table cells with imperative
  evidence-request verbs. That is internal-note/checklist voice. State the
  fact, then the risk, in ordinary English.
- Do not speculate about sponsor, company, investor, or counterparty
  capability to share, provide, produce, or confirm information. State the
  disclosed fact and the risk.
- Do not narrate the sponsor memo or source process in final prose. Avoid
  "memo language was", "the sponsor implies", "the sponsor frames", and
  "the sponsor itself flags". State the fact or risk directly.
- Do not use source-process narration as a substitute for investment judgment.
  Do not narrate what a sponsor note, registry, source packet, or memo artifact
  says. Write the fact in plain form: "The $140M+ figure blends signed
  contracts and letters of intent."
- Do not write passive availability language about future process access or
  ease of confirmation. Those are guesses about process, not investment
  judgments.
- Use ordinary legal English. "A SAFE is not equity and has no LP voting."
  "Annual K-1 issued by the SPV administrator." "Accredited investors only."
  Do not dump a rights checklist, and do not paraphrase those facts into
  "limited direct governance and reporting" machinery.
- Do not use buyer-side underwriting vocabulary in final prose or tables.
  Do not replace it with the next template: "we give credit to", "our base
  case credits", "the investment case rests on", "the investment case uses",
  or "X is a valuation-support factor." State the fact or the risk.
- Do not use writer-process framing such as "we frame it as", "we frame the
  market", or "the framework". State the conclusion directly.
- Do not write imperative diligence commands such as "Require X before
  underwriting". Write the implication: "X is not in the disclosed terms."
  or "X remains the principal risk."
- Do not use casual sponsor verbs or exposure-seeking idioms. Write
  "Recommendation: BSH commits..." for the action, and never compose a
  mandate sentence. Prefer physical language over framework metaphors when
  the source supports it ("no rails, no floor markers, no driver in the
  cab"), not "is compelling because" or a prescribed "control layer for"
  slogan.
- Do not overload the opening paragraph with sponsor mission, technical claim,
  investor roster, and founder resume in one block. Open with sponsor thesis
  and company relevance, then move technical proof, backers, and team pedigree
  into the next paragraph or Company Overview.
- Do not use uniqueness claims such as "only scaled platform" unless the source
  package independently supports both uniqueness and scale. Use precise
  capability claims instead.
- Do not use protected or sensitive founder demographic traits, BSH founder
  background preferences, or thesis-fit exception labels as investment
  rationale, investment risk, recommendation logic, source treatment, or final
  memo disclosure. Team discussion belongs in operating history, domain
  expertise, technical authorship, recruiting strength, governance, and
  company-building evidence.

Concrete positive writing patterns (Tarnwell Robotics is a fictional
company: copy the shape of these sentences, never their facts or wording):
- Opening: "Cold-storage warehouses still move pallets by hand at minus
  twenty degrees, and they cannot hire for the work. Tarnwell Robotics
  builds forklifts that run those aisles on their own: no rails, no floor
  markers, no driver in the cab."
- Transaction, with deal terms on file: "The vehicle is an $8,000,000 SAFE
  with a 20% discount at a $1.2B estimated pre-money. Effective entry
  after the discount is about $960M. Recommendation: BSH commits to
  Tarnwell at those terms."
- Transaction, with no deal terms on file: "No vehicle or terms are on
  file. The March 2026 Series B at a $1.1B post-money is the only mark.
  Recommendation: watch Tarnwell — the trigger is a term sheet at or below
  that mark."
- Proof: "Commercial pull is $140M+ in signed contracts and letters of
  intent over nine months, $9M of defense-logistics work, and named
  customers including Carrow Freight and Pemberly Cold Chain. Ines Varga,
  who ran warehouse automation at a national grocer, chairs the board."
- Scan bullets: bold noun lead-ins, then one fact. "Founded: 2019,
  Pittsburgh. SAFE risk. A SAFE is not equity and has no LP voting.
  Concentration. A material share of the $140M+ figure remains letters of
  intent."
- Risk: "A SAFE is not equity and has no LP voting. $1.2B is high relative
  to disclosed revenue. A material share of the $140M+ figure remains
  letters of intent. Warehouse retrofit cycles run 12 to 24 months."
- Evidence gap: "Revenue is not disclosed. $1.2B is high relative to
  disclosed commercial proof."
- Diligence: "A BSH reference call (customer, 2026-06) confirmed the
  uptime figure. One call is an anecdote, so the case does not rest on
  it."

Rejected language categories:
- stock participation slogans ("we are being offered", "we are participating
  through", "we recommend participating") and their negations;
- detached IC jargon for recommendation and opportunity;
- memo/document/process narration;
- analysis-process narration;
- passive sponsor/counterparty capability speculation;
- legal-rights checklist dumps in operating tables;
- uncertainty apologies instead of a direct fact and risk;
- treatment-speak ("the investment case uses", "our base case credits",
  "we give credit to", "source class", "model treatment", "valuation-support
  factor");
- source-class scaffolding in the body ("company-reported" as a label,
  "available evidence does not document").

Final memo body and operating tables must not contain:
- file references or internal tokens such as `[WV]`, `[WV SPV memo]`,
  `[companies.yaml]`, `[internal]`, or similar. Structure-v2 packages
  cite the Sources table and the Calculation notes inline as `[S3]` /
  `[C2]` — those two forms are the ONLY bracketed tokens allowed (see
  the citations rules in the v2 addendum); v1 packages keep source ids
  in the Sources index alone, and cite a calculation note as `[C2]`
  only when the pin sheet lists that note — never an id it does not
  carry;
- internal artifact names such as `companies.yaml`, `memo_packet`,
  `source_trace`, `claim_register`, `research_tasks`, `reviewer_prompts`, or
  analysis file names;
- source-process narration about what a memo artifact, registry, source packet,
  sponsor note, or reviewer prompt says;
- scaffold headings or labels from analytical worksheets, evidence-state
  tables, closing checklists, expected-bar lists, investment-condition lists,
  revisit-condition lists, or internal question lists;
- founder demographic preference language, thesis-fit exception labels, or
  internal mandate exceptions as investment rationale or risk factors;
- cute or fuzzy finance metaphors, no-rights legal shorthand, overclaimed
  scarcity phrases, or shorthand that obscures the economic point;
- deal-legal checklist dumps such as `MFN`, `down-round protection`,
  `named lead`, `named institutional lead` without saying what they mean;
  ordinary legal English is fine: "no LP voting", "annual K-1",
  "accredited investors only";
- passive counterparty-capability or availability speculation;
- detached recommendation-label headings; state the recommendation directly
  in a sentence;
- internal question-list labels, confirmation labels, expected-bar labels, or
  internal-audience suffixes;
- internal IC, buyer-side diligence, bank/debt, control-investor, or
  deal-legal checklist shorthand. This is an LP-facing, exec-ready sell-side
  investment memo, not a BSH internal allocation note. Write every deal
  mechanic, governance point, and recommendation as plain narrative prose.
  Say what the instrument is, what the recommendation commits, and what the
  risks are. Do not use process labels, confirmation labels, small-check
  reflexes, or treatment-speak;
- BSH internal participation-sizing language or internal recommendation
  instructions;
- meta-language about the memo/document/analysis/framework/section, including
  writer-process phrasing.

Memo spine requirement:
- core_bet: what has to be true for investors to make money;
- entry_tension: what the valuation or instrument already assumes — and,
  when a named, dated source states the consensus view (consensus_source),
  that view and our_view of it, one sentence each;
- current_proof: what is proven today, named (people, contracts, dates);
- unproven_but_modelable: what is missing, stated as a fact and a risk;
- risk_sensitivity: what can break the case;
- action: the recommended commitment or pass, in sentence form, opening
  with "Recommendation: ".

State the spine in full once, at the opening: the first two body
paragraphs state the company, the transaction, the valuation / entry
terms and the central price/proof tension. The substantive ending
restates the recommendation (commit or pass), the named risks, and what
moves the number, before any sources or disclosures. Every section in
between argues only its own part and refers back to the section that
owns a fact ("see Valuation") instead of restating it. Pinned facts are
the exception, within a limit: a pinned sentence or number that the pin
sheet requires in several sections is echoed verbatim in each of those
sections, and at most ONCE per section — in the passage that owns it
there. Every other mention in the same section refers to the fact
without repeating the figure: "the February 2026 mark", "the base
case", "the contracts-and-letters aggregate". One live memo restated
the same entry mark forty-nine times and the same aggregate
thirty-five; a reader who has met a figure once does not need it again
in the next paragraph. The decision section does not repeat its own
prose as a bullet list. Do not include BSH internal participation
sizing in the LP-facing memo.

Positive examples for early-commercial infrastructure deals (the same
fictional Tarnwell Robotics):
- "Tarnwell's forklifts already run driverless shifts in freezer aisles.
  The Series B prices real IP, technical depth, and early commercial pull
  before the revenue curve is fully visible."
- "Signed contracts and letters of intent total $140M+ over nine months,
  plus $9M of defense-logistics work. Carrow Freight and Pemberly Cold
  Chain are named customers. Ines Varga chairs the board."
- "Pipeline is not contracted revenue. A material share of the $140M+
  figure remains letters of intent."
- "The SPV is an $8M SAFE with a 20% discount. A SAFE is not equity and
  has no LP voting."
- "Two crossover funds joined an oversubscribed round: informed buyers
  accept this price. That does not make the price right — the
  recommendation rests on the return at $1.2B."

Banned phrase / rewrite guidance:

| Avoid | Prefer |
|---|---|
| The investment case is not that... | This is not a conventional SaaS case. |
| Detached recommendation framing | Recommendation: BSH commits to <target>... / Recommendation: pass on... |
| Detached opportunity framing | The SPV is an $8M SAFE... / Investors can subscribe up to $Y (deal terms on file only) |
| Detached base-case framing | Named proof. Then the risk. |
| we give credit to / our base case credits / the investment case rests on | State the fact. Drop the formula. |
| the investment case uses / valuation-support factor | State the fact and the risk. |
| Key risk centers on... | Bold noun label, then one sentence: "SAFE risk. A SAFE is not equity." |
| Memo/document/process narration | Remove the frame; make the investment statement. |
| Analysis-process narration | State the conclusion directly. |
| Uncertainty apology | "Revenue is not disclosed. $1.2B is high relative to disclosed revenue." |
| Detached decision label | Investment Decision / Recommendation: BSH commits... |
| Question-form closing checklist | State the deal economics or the risk. |
| Sponsor capability speculation | State the disclosed fact and the risk. |
| Passive availability language | Remove the process guess; state the risk. |
| Funding-gate checklist phrase | State the fact or the risk. |
| Imperative evidence-request phrase | State the deal fact or the risk. |
| Closing checklist headings | Remove the section; fold the substance into recommendation, risk, or deal mechanics. |
| Signing-process checklist phrase | State the deal fact directly. |
| Open-item process phrase | State what is disclosed, not disclosed, and why it matters. |
| Sponsor-process narration | State the investment fact or risk directly. |
| Source-process narration / source class / model treatment | Name the person, contract, or publication. Put classes in the index. |
| Diligence threshold or next-step checklist labels | Fold into recommendation, risk, or deal-mechanics prose. |
| No voting or information rights (checklist dump) | A SAFE is not equity and has no LP voting. |
| underwrite / underwriting | rely on / the case / drop the verb |
| We frame it as... | State the conclusion directly without writer-process narration. |
| Require X before underwriting | X is not in the disclosed terms. / X remains the principal risk. |
| Internal question-list labels | Remove; use thesis, risk, or deal mechanics. |
| we are being offered / we recommend participating / we are participating through (and their negations) | Firm-as-subject deal English; never reuse these slogans |
| is compelling because | What the company does, in physical terms. |
| Unresolved inquiry framing | Risk factors / deal-mechanics disclosure |
| Missing proof | Named gap, then the risk. |
| Recommendation labels | Recommendation: BSH commits... / Recommendation: pass on... |
| BSH should ... / what BSH should do | BSH moves when... / The trigger is a new priced round. (the firm acts, it is not advised) |
| Decision discipline | named risks |
| False precision | State the evidence range without over-modeling it. |
| not treated as ARR | not revenue-recognized |
| commercial momentum is material, but... | The pipeline is large but not contractually binding. |
| The principal risk is that... | SAFE risk. Concentration. Illiquidity. |
| Soft-instrument metaphor | SPV interest whose economics depend on SAFE conversion. |
| Hard-IP metaphor | patent estate and technical approach that still need claim-scope review. |
| Moat-compression shorthand | upside shifts from product margin to patent leverage and deployment relationships. |

Before DOCX generation, run a final prose QA pass. Remove banned phrases,
meta language, methodology leakage, over-explained risks, template-visible
structure, and unnatural model voice. The output must read like an experienced
investor making a call under uncertainty.
