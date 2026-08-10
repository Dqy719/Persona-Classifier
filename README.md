# Persona-Classifier

A two-stage classifier that assigns a sales persona to every contact in a CRM based on their job title. Stage 1 handles the majority with deterministic rule matching; Stage 2 sends only the residual to a language model. Built during my technical GTM internship.

This is a **sanitized version** of the production script. Credentials, sheet IDs, and real contact data have been replaced with placeholders and representative examples.

For the full write-up on the design, tradeoffs, and lessons learned, see [the project page on my portfolio](https://dqy719.github.io/portfolio/crm-persona-classification/).

---

## What This Does

Reads a CRM contact list from a Google Sheet, and for every contact whose `Persona` field is blank, assigns one of ten sales personas based on the `Job Title` field. The output is a CSV with the persona filled in, plus an audit column recording how each label was produced.

The design premise is a **cascade**: cheap, transparent rules run first and handle the bulk; the expensive LLM is reserved for the residual titles that no rule can confidently place. This keeps the system auditable, cheap to run, and honest about what it can and cannot classify.

## Architecture

| Stage | What It Does | Output |
|-------|--------------|--------|
| **1. Rule-based matching** | Normalizes titles, applies word-boundary keyword matching with context-sensitive disambiguation and proximity-based combo rules, resolves conflicts via a persona precedence order | Assigned persona OR blank + a `Needs_Stage2_LLM` flag |
| **2. LLM classification** | For flagged rows only, filters out blank and garbled titles (mojibake detection that preserves CJK and accented Latin), then sends the remainder to Claude Haiku in batches of 25 with exponential backoff | Persona OR "None" if the model declines to force a fit |

Every row's provenance is recorded in a `Persona_Match_Method` column:

- `strong` — matched by a specific keyword
- `combo` — matched by a proximity rule (e.g., a seniority word within 4 tokens of "sales")
- `junk` — placeholder title like "Wrong email ID"; skipped
- `llm` — classified by the language model
- `llm_none` — model declined to force a fit
- `skipped_blank` / `skipped_garbled` — filtered before the model
- `none` — no rule fired and row was not eligible for Stage 2

This audit column is what makes the whole pipeline reviewable after the fact.

## The Ten Personas

- **PE / Value Creation** — operating partners, portfolio-ops at PE firms
- **Sales Executive / CRO** — sales leadership at director level and above
- **Revenue Operations / Sales Operations** — RevOps, SalesOps, GTM operations
- **Sales Enablement / Learning** — enablement and L&D roles supporting sales
- **CEO / Founder** — CEOs, founders, and company-level presidents
- **People / Talent / HR** — CHROs, People Ops, talent acquisition
- **Product / Technology / Data** — CTOs, CPOs, engineering, data, analytics
- **IT / Security** — CIOs, CISOs, IT infrastructure roles
- **Investor** — venture partners, angel investors
- **Advisor** — external advisors and consultants

## Files

- **`Persona_parse.py`** — Contains stage 1: Rule-based matcher. Normalization, word-boundary matching, contextual disambiguation (e.g., "president" is a CEO signal, but not after "vice"), proximity combo rules, and precedence-based conflict resolution.
 And stage 2: LLM classifier for the residual. Filters blank and garbled titles before spending API calls, batches remaining titles, and uses Claude Haiku with exponential-backoff retry and code-fence-tolerant JSON parsing.

## Setup

Both stages are designed to run in Google Colab, since that was the environment used at PeopleLens for CRM work, but they run anywhere with minor edits.

### Stage 1

1. Install dependencies:
2. Share the target Google Sheet with a Google Service Account.
3. Fill in `SHEET_URL`, `GID`, and `OUTPUT_PATH` at the top of `stage1_regex_match.py`.
4. Run.


---

Built during my GTM engineering internship, April–July 2026.
