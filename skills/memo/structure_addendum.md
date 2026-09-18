
## Data honesty (structure v2 — these rules override any instinct to fill gaps)
- Never invent, extrapolate, or "estimate" a number that no source states.
  A missing datum is stated as missing, in place, every time.
- Missing table cell: write exactly "Not disclosed — <implication, 15 words
  max>" (Chinese: "未披露——<含义>"). The implication says what the gap means
  for the analysis, not that data is unavailable.
- Missing datum in prose: one sentence states the gap, the next states what
  follows from it. Never skip a contracted passage because its data is thin.
- Chart slots render as real `chart` blocks (rules below) built ONLY from
  numbers the tables or pins already state. When the series is not
  disclosed, no chart: keep the slot and write: "Chart omitted —
  <series> is not disclosed. <nearest disclosed anchor, or 'No disclosed
  anchor exists.'> <what the gap means for the thesis>."
- A table with most rows undisclosed keeps its full fixed structure; add
  one sentence naming the disclosure gap itself as evidence about the
  company.
- Fund-specific mechanics we cannot know are placeholders, verbatim:
  "Proposed amount: [TO BE DETERMINED BY IC]", "Allocation: [TO BE
  DETERMINED BY IC]", "Strategy: [重仓 / 跟投 / 卡位 — IC to select]".
- Absence of disclosure is itself information about the company; read it.

## Inputs are closed (structure v2)
- Your inputs are this run's folder, its research folder and studio
  packet, and the registry entry above — nothing else on disk.
- Never read this application's source code (server/, frontend/,
  tests/) to infer schemas or field meanings. The JSON schema you were
  given is the complete, authoritative output contract; if a field is
  not in it, do not produce it.
- Never open another company's or another run's folders under
  data/memos/. A prior memo is not evidence, not a template, and not a
  schema example — copying its shape or facts contaminates this memo.

## Section navigation (structure v2)
- Every section is organized under the fixed numbered subsections its
  contract declares, in order. Emit each as a `heading` block, level 2,
  with BOTH languages filled exactly as the contract lists them:
  {"type": "heading", "level": 2, "text": {"en": "1. <en title>",
  "zh": "1. <zh title>"}}. Numbering restarts at 1 in each section and
  is arabic ("1.") in BOTH languages — never roman ("i.") and never
  Chinese numerals ("一、"); those prefixes are dropped by the renderer.
- Every other block belongs under one of the declared subsections; no
  content precedes subsection 1's heading.
- The heading does the orienting: never open a passage by announcing
  what it is about ("This section examines...", "Turning to the
  market..."). Under its heading, the passage starts with the verdict.
- The executive summary contains NO tables. It says the point: what the
  company is, what the deal is, why invest, what could kill it, and the
  recommendation — every number interpreted in its own sentence. The
  snapshot tables live in the overview section the contract routes them
  to.

## Charts (structure v2)
Where a section contract names a chart slot, emit a `chart` block:
{"type": "chart",
 "chart_type": "bar" | "grouped_bar" | "hbar" | "line" | "pie",
 "title": {"en": ..., "zh": ""}, "unit": {"en": "US$B", "zh": ""},
 "reading": {"en": "Higher is better", "zh": ""},
 "caption": {"en": <one interpretation sentence>, "zh": ""},
 "series": [{"label": "<plain EN string>",
             "points": [{"x": "<label>", "y": <plain number>}, ...]}],
 "source_ids": ["S1", ...]}
- The contract's chart type is a SUGGESTION: use whichever supported
  type explains the point best (hbar suits long names; line suits a
  trajectory; pie suits a composition summing to a whole).
- `reading` is REQUIRED: one short phrase telling the reader how to
  read the chart — "Higher is better", "Lower is better", "Bars below
  1.0x lose money", "Shares of total revenue". When the natural
  reading has an exception, say it there ("Higher is better — the
  2027 bar is a company forecast").
- Numbers only from the section's tables or the pinned fact sheet —
  a chart never introduces a number the text does not carry.
- `y` is a PLAIN NUMBER in the stated `unit` ("$1.1T" with unit US$B is
  y: 1100). No strings, no ranges; convert carefully.
- Series labels and x labels are plain English/neutral strings — they
  render inside the image, which is shared by both language documents.
  `title`, `reading`, `caption`, and `unit` are bilingual objects like
  all block text.
- 1-4 series; every series shares the same x categories in the same
  order; `bar`, `hbar`, and `pie` take exactly one series; at least
  two data points — a single number is prose, not a chart.
- The caption interprets, never restates: what the shape or gap means
  for the thesis.
- A chart slot whose series is not disclosed emits NO chart block —
  write the chart-omitted fallback line from the data-honesty rules.
  Never a chart with invented or placeholder numbers.

## Explanatory register (structure v2)
- Headings state the verdict, not the topic: "Revenue forecasting remains
  unreliable", never "Revenue forecast".
- Answer first: every named verdict passage ("The ceiling question",
  "Healthier or hungrier", "Widening or narrowing", ...) OPENS with its
  one-line answer in plain words a reader can quote, then argues it, then
  restates it. A reader who stops after the first sentence must still
  have the verdict.
- Every table is followed by a reading that OPENS with what the numbers
  MEAN — good, bad, or mixed for this investment, and why — before any
  numbers repeat. A passage that walks through the data without saying
  which way it cuts is unfinished, however accurate.
- Bullets open with the claim, not the topic: the words before the first
  period carry the direction ("The price sits below every disclosed
  peer — 13.8x vs a 21x median."), never a naked label ("Price.",
  "市场规模。").
- No orphan numbers: every figure is interpreted in the same or the next
  sentence; a paragraph may not end on an uninterpreted figure.
- After presenting evidence, weigh it explicitly: "The pipeline is valuable
  evidence of demand. It is not revenue."
- Where a number implies a consequence, do the arithmetic in-line:
  "After note conversion, a $10B outcome produces less than a 2x gross
  return before later dilution."
- Short subject-verb-object sentences, one idea per paragraph, verdict
  first. Ban: "positions the company", "underscores", "highlights",
  "robust", "significant traction", "leverage" as a verb.
- Ambiguous evidence is argued both ways in its own passage, then
  weighed: the honest bull reading, the honest bear reading, and which
  one the evidence favors.

Worked examples (match the Prefer register, never the Avoid one):
- Avoid: "Risk 1: Entry price. $1.0B+ on ~$24M ARR is ~42x against a
  ~12x comp median."
  Prefer: "Risk 1: The entry price already assumes success — ordinary
  execution earns nothing. At $1.0B+ on ~$24M ARR the round is priced
  at ~42x, three and a half times the ~12x comp median. ARR must
  roughly double before the price merely matches peers, so flawless
  execution holds value flat, and any multiple compression comes out
  of principal first."
- Avoid: "NRR: 118%. CAC payback: 19 months."
  Prefer: "NRR of 118% means the installed base grows on its own — a
  real asset. The 19-month CAC payback works against it: each new
  customer ties up cash for over a year and a half, so growth is
  rationed by the balance sheet, not by demand."
- Avoid: "The company has a strong pipeline of $40M."
  Prefer: "The company reports a $40M pipeline. The pipeline is
  valuable evidence of demand. It is not revenue, and at the company's
  own 25% historical conversion it supports roughly $10M of bookings."

## Citations (structure v2)
- Every external fact carries the id of the source it rests on, inline,
  as `[S3]` (several: `[S3, S7]`); every derived number carries the id
  of its calculation note as `[C2]`. The renderer turns them into links
  to the Sources table and the Calculation notes appendix, so a reader
  can click to see where a number came from and how it was computed.
- Highlights, key risks, the verdict callout, every table cell that
  holds a number, and every scenario, fair-value and market-size figure
  MUST carry them. Cite only ids that exist in the pin sheet's
  calculation notes or the package sources — an unknown id fails
  validation. Place the token after the number or at the end of the
  sentence, never inside a heading.
- Keep the tokens exactly as written in both languages.

## Teach, don't assert (structure v2)
The reader is a senior investor who has never seen this company and
reads the memo once, fast. Write the way a professor walks a student
through a case: nothing is assumed known, every step is shown.
- Define a term the first time it appears, in five to ten words:
  "run-rate (the latest month's revenue multiplied by twelve)", "NRR
  (how much last year's customers spend this year, as a percentage)",
  "MOIC (money returned divided by money invested)", "IRR (the
  annualized return over the holding period)".
- A number is preceded by what it measures and followed by what it
  means. "Revenue is $65B" is not enough; say what kind of revenue,
  over what period, measured how — then what that size implies.
- Every derived number shows its arithmetic in the sentence or the
  next one: "the base case values the company at 13 times $200B of
  2029 revenue, or $2.6T; against today's $1.75T entry that is 1.5x,
  a 15% annual return over three years". Every comparison names the
  rule it is judged against: "1.44x is below the 1.5x floor we require
  for a late-stage position, which is why the verdict is Watch".
- Every external number names who produced it and what it counts; our
  own estimates say so ("our estimate, built from X and Y") and never
  pass as a market fact. Never write "the memo" or "this memo" in the
  body: the reader is holding it. Say "we" or "our".
- Never jump from a fact to a conclusion with the middle step missing.
  If the reader would have to ask "why does that follow?", the
  sentence that answers it is missing.
- Highlights and risks lead with a plain verdict sentence a reader can
  quote, then the evidence — the judgment first, the support second.

Worked examples (from the founder's review of a live memo):
- Avoid: "Growth is exceptional and the price still decides the
  outcome: run-rate went from roughly $9B in December 2025 to $65B at
  end-July 2026, sevenfold in seven months, yet the base case returns
  only 1.5x gross and a 15% IRR over three years. At $1.5T that return
  exists; above $1.8T no margin of safety remains."
  Prefer: "Growth is exceptional, but the price already pays for most
  of it. Annualized revenue (the latest month multiplied by twelve, as
  the company reports it to investors) rose from about $9B in
  December 2025 to $65B by July 2026 — seven times in seven months.
  The base case assumes $200B of revenue in 2029 valued at 13 times
  revenue, or $2.6T. Against a $1.75T entry price that returns 1.5x,
  a 15% annual return over three years. At an entry of $1.5T the same
  exit returns 1.7x; at $1.8T it returns 1.44x, below the 1.5x floor
  we require for a late-stage position — so the price, not the
  growth, decides whether this works."
- Avoid: "Risk 1: The entry price already assumes the plan is
  delivered. At $1.75T the buyer pays about 9x a 2028 revenue line
  that was revised from $70B to $190-200B in ten months, and the base
  case returns 0.91x. Rated 9/10, likelihood high."
  Prefer: "Risk 1 — Valuation & exit: the price is too high for the exit
  to return enough — it already assumes the 2028 plan comes true.
  Impact: the base case returns 0.91x — a 9% loss even if the company
  executes. Why: the sellers are discussing a price of $1.75T. That is
  about 9 times the revenue the company now plans for 2028
  ($190-200B). Ten months ago the same plan said $70B, so the plan
  nearly tripled before any of it was earned, and a revision that size
  is itself what makes the number hard to hit. The multiple depends on
  the company type too: mature software leaders trade at about 8 times
  revenue, while a foundation-model or platform company can earn more
  in the right market — so a valuation judgment has to establish two
  things, whether the revenue line is achievable AND what multiple
  range genuinely applies to this type. If 2028 revenue comes in at
  the plan and the market pays 8 times revenue, the company is worth
  about $1.6T, less than the $1.75T paid. The risk is rated 9/10
  because it alone can turn a good company into a losing investment,
  and likelihood is high because the price range is already public."

## The six moves (structure v2)
Every judgment that carries weight — a highlight, a risk, a valuation
call, a dimension scan line — is written in the same order. The order is
not a style preference; it is what lets a reader who is new to investing
follow an argument they could not have reconstructed themselves.

1. **Say the point, in plain words, with no numbers in it.** The first
   sentence states what is true and why it matters. A reader who stops
   after it has still learned something.
2. **Show the arithmetic, with the numbers in it.** Not the result alone
   — the inputs, the operation, the result, and the [C#] of the note it
   comes from. "About $190-200B of 2028 revenue against a $1.75T price
   is roughly 9x revenue [C4]."
3. **Say what it costs, or what it earns.** Translate the number into
   consequence for the investment, in a sentence a partner could repeat
   in a meeting.
4. **Calibrate it — say what counts as normal HERE.** This is the move
   most often missing, and the one a new reader most needs: a number
   means nothing until they know the range it sits in. Mature software
   trades near 8x revenue; a frontier lab can hold more in a strong
   market. The company-type lens in your instructions tells you what
   normal looks like for THIS type of company — use it, and name the
   comparison you are making.
5. **Say what to check.** Two or three facts that would settle the
   question, named concretely enough that someone could go and find
   them. Never "monitor execution".
6. **Rate it, and say why the rating is what it is** — in the same
   breath, in parentheses. A rating with no reason is a number the
   reader has to take on trust.

Worked example (the founder's own refinement of a live memo passage —
this is the target register for the whole report):

> The asking price already assumes an optimistic 2028 and an optimistic
> multiple. On the current plan, 2028 revenue is about $190-200B, so the
> $1.75T the seller is discussing works out to roughly 9 times revenue
> [C4] — already at the high end. Ten months ago the company's own
> target for that year was $70B; raising it to about $190B in that time
> demands enormous growth, which makes the target itself part of the
> risk. Worth knowing: what buyers pay per dollar of revenue varies a
> great deal by company type — mature software often trades near 8x,
> while a frontier model or platform company can hold more in a strong
> market. So the valuation judgment here has to test two things at once:
> whether the revenue is achievable, and which comparable multiple
> actually applies.
> What to check: the seller's price range, the evidence that 2028
> revenue is achievable, and comparable transaction multiples for this
> type of company.
> Risk rating: 9/10 — one assumption slipping turns this into a loss;
> likelihood high, because the price range is already public.

Notice what the example does NOT do: it never states a conclusion the
reader cannot retrace, it never uses a number before saying what the
number measures, and it never assumes the reader already knows whether
9x is a lot. Write every weighted judgment this way.
