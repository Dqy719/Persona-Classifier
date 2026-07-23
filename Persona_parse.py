

"""
Stage 1: Rule-based persona matching 
"""

from google.colab import auth, drive
auth.authenticate_user()
drive.mount('/content/drive')

import gspread
from google.auth import default
import pandas as pd
import re

creds, _ = default()
gc = gspread.authorize(creds)

SHEET_URL = "132123132123132"
GID = 1212123132
OUTPUT_PATH = "/content/contacts_with_persona.csv"  

sh = gc.open_by_url(SHEET_URL)
worksheet = next((ws for ws in sh.worksheets() if ws.id == GID), sh.sheet1)
df = pd.DataFrame(worksheet.get_all_records())


# Persona precedence: PE and RevOps/Enablement checked before the generic
# CRO combo match.

PERSONA_PRECEDENCE = [
    "PE / Value Creation",
    "Revenue Operations / Sales Operations",
    "Sales Enablement / Learning",
    "Sales Executive / CRO",
    "CEO / Founder",
    "People / Talent / HR",
    "Product / Technology / Data",
    "IT / Security",
    "Investor",
    "Advisor",
]

PERSONA_KEYWORDS = {
    "PE / Value Creation": ["operating partner","value creation","portfolio operations","portfolio ops","pe operating","private equity","pe advisor"],
    "Sales Executive / CRO": ["chief revenue officer","cro","chief sales officer","evp sales","svp sales","vp sales","rvp","head of sales","sales director"],
    "Revenue Operations / Sales Operations": ["revenue operations","revops","sales operations","sales ops","gtm operations","commercial operations","revenue ops","rev ops","marketing operations","marketing ops"],
    "Sales Enablement / Learning": ["sales enablement","revenue enablement","field enablement","gtm enablement","learning and development","l&d","enablement"],
    "CEO / Founder": ["ceo","chief executive officer","founder","co-founder","cofounder","president"],
    "People / Talent / HR": ["chro","chief people officer","people operations","people ops","talent","hr","human resources"],
    "Product / Technology / Data": ["cto","chief technology officer","chief product officer","engineering","data","analytics","ai"],
    "IT / Security": ["cio","ciso","security","chief information officer","it","evp it","svp it","vp it","director it","manager it","vp technology","infrastructure","enterprise applications"],
    "Investor": ["venture partner","investor","angel investor","vc"],
    "Advisor": ["advisor","gtm advisor"],
}

GENERIC_KEYWORDS_NEED_QUALIFIER = {"it", "security", "ai", "data", "analytics", "engineering", "hr", "talent"}
SENIORITY_QUALIFIERS = ["chief", "vp", "vice president", "svp", "evp", "avp", "director", "head", "manager", "lead", "officer"]

OVERRIDE_RULES = [
    (["marketing operations", "marketing ops"], "Revenue Operations / Sales Operations"),
]

EXCLUSION_PHRASES = ["assistant to"]

# Combo rules: (seniority_terms, role_terms, persona, max_word_gap)
CRO_COMBO_SENIORITY = ["chief", "vp", "vice president", "svp", "evp", "avp", "director", "head", "rvp", "regional vice president"]
COMBO_RULES = [
    (CRO_COMBO_SENIORITY, ["sales"], "Sales Executive / CRO", 4),
]

# Placeholder / junk
JUNK_TITLES = {"intern reference", "wrong email id", "vendor"}


def normalize_title(title):
    if pd.isna(title) or str(title).strip() == "":
        return ""
    t = str(title).strip().lower()
    t = t.replace("&", " and ")
    t = re.sub(r"[/,;|]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def keyword_in_title(keyword, normalized_title):
    kw = keyword.lower().replace("&", " and ")
    kw = re.sub(r"\s+", " ", kw).strip()
    pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
    for m in re.finditer(pattern, normalized_title):
        if kw == "president":
            preceding_words = normalized_title[:m.start()].strip().split(" ")
            if preceding_words and preceding_words[-1] == "vice":
                continue  # "Vice President" is not a CEO/Founder signal
        return True
    return False


def has_seniority_qualifier(normalized_title):
    return any(keyword_in_title(q, normalized_title) for q in SENIORITY_QUALIFIERS)


def find_term_positions(term, tokens):
    term_tokens = term.split()
    n = len(term_tokens)
    return [i for i in range(len(tokens) - n + 1) if tokens[i:i + n] == term_tokens]


def combo_hit(normalized_title, seniority_terms, role_terms, max_gap):
    tokens = normalized_title.split()
    sen_pos = [p for t in seniority_terms for p in find_term_positions(t, tokens)]
    role_pos = [p for t in role_terms for p in find_term_positions(t, tokens)]
    return any(abs(sp - rp) <= max_gap for sp in sen_pos for rp in role_pos)


def is_junk(raw_title):
    return normalize_title(raw_title) in JUNK_TITLES


def match_title(raw_title):
    normalized = normalize_title(raw_title)
    matches = {}
    if not normalized or is_junk(raw_title):
        return matches

    if any(keyword_in_title(p, normalized) for p in EXCLUSION_PHRASES):
        return matches  # assistant/support titles never get auto-matched

    for phrases, persona in OVERRIDE_RULES:
        hit_phrases = [p for p in phrases if keyword_in_title(p, normalized)]
        if hit_phrases:
            return {persona: hit_phrases}

    qualifier_present = has_seniority_qualifier(normalized)
    for persona in PERSONA_PRECEDENCE:
        hits = []
        for kw in PERSONA_KEYWORDS[persona]:
            if not keyword_in_title(kw, normalized):
                continue
            if kw in GENERIC_KEYWORDS_NEED_QUALIFIER and not qualifier_present:
                continue
            hits.append(kw)
        if hits:
            matches[persona] = hits

    for sen_terms, role_terms, persona, gap in COMBO_RULES:
        if persona in matches:
            continue
        if combo_hit(normalized, sen_terms, role_terms, gap):
            matches[persona] = ["[combo match: seniority word + 'sales' nearby]"]

    return matches


def pick_persona(raw_title):
    matches = match_title(raw_title)
    if not matches:
        return None
    for persona in PERSONA_PRECEDENCE:
        if persona in matches:
            return persona
    return None


def match_method(raw_title, chosen_persona):
    if is_junk(raw_title):
        return "junk"

    if chosen_persona is None or pd.isna(chosen_persona):
        return "none"
    hits = match_title(raw_title).get(chosen_persona, [])
    if hits and str(hits[0]).startswith("[combo match"):
        return "combo"
    return "strong"



# Apply to blank-persona rows only (same behavior as your original script)

needs_fill = df["Persona"].isna() | (df["Persona"].astype(str).str.strip() == "")

df.loc[needs_fill, "Persona"] = df.loc[needs_fill, "Job Title"].apply(pick_persona)
df["Persona_Match_Method"] = ""
df.loc[needs_fill, "Persona_Match_Method"] = df.loc[needs_fill, "Job Title"].apply(
    lambda t: match_method(t, pick_persona(t))
)

filled = df.loc[needs_fill, "Persona"]
print(f"Blank contacts processed: {len(filled)}")
print(f"Matched (strong or combo): {filled.notna().sum()}")
print(f"Left blank (no match / junk): {filled.isna().sum()}")
print(df.loc[needs_fill, "Persona_Match_Method"].value_counts())

df["Persona"] = df["Persona"].fillna("")

# Flag rows that should go to stage 2 (LLM): blank persona, not junk
df["Needs_Stage2_LLM"] = needs_fill & (df["Persona"] == "") & (df["Persona_Match_Method"] != "junk")

df.to_csv(OUTPUT_PATH, index=False)
print(f"Saved to {OUTPUT_PATH}")
print(f"Rows flagged for stage 2 LLM classification: {df['Needs_Stage2_LLM'].sum()}")

#========================Stage 2================================

"""
Stage 2: LLM classification for whatever stage1_regex_match.py couldn't match.
"""

import pandas as pd
import json
import time
import re

try:
    import anthropic
except ImportError:
    import subprocess
    import sys
    print("Installing anthropic package...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "anthropic"], check=True)
    import anthropic

try:
    from google.colab import userdata
    API_KEY = userdata.get("ANTHROPIC_API_KEY")
except Exception:
    import os
    API_KEY = os.environ.get("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=API_KEY)
MODEL = "claude-haiku-4-5-20251001"

STAGE1_CSV = "contacts_with_persona.csv"
OUTPUT_PATH = "contacts_with_persona1.csv"

BATCH_SIZE = 25

PERSONA_DEFINITIONS = {
    "PE / Value Creation": "Private equity operating partners; portfolio company operations/value-creation roles; PE advisors.",
    "Sales Executive / CRO": "Sales leadership at director level and above: CRO, VP/SVP/EVP of Sales, Head of Sales, Regional VP of Sales, Sales Director. Does NOT include individual-contributor reps (Account Executive, SDR, BDR) or manager-level sales titles.",
    "Revenue Operations / Sales Operations": "RevOps, SalesOps, GTM Operations, Commercial Operations, Marketing Operations roles of any seniority.",
    "Sales Enablement / Learning": "Sales/Revenue/Field/GTM Enablement roles, and Learning & Development roles that support sales teams.",
    "CEO / Founder": "CEO, Founder, Co-Founder, or President at the company level (not a VP-level 'president' title).",
    "People / Talent / HR": "CHRO, Chief People Officer, People Operations, Talent Acquisition, HR roles.",
    "Product / Technology / Data": "CTO, Chief Product Officer, engineering, data science, analytics, or AI roles.",
    "IT / Security": "CIO, CISO, information security, IT infrastructure roles.",
    "Investor": "Venture capital partners/investors (not PE operating roles -- use PE / Value Creation for those).",
    "Advisor": "External advisors/consultants not otherwise covered above.",
    # COO / CFO / CMO / CPO and individual-contributor sales roles are
    # deliberately left uncovered -- see notes at top of file. The prompt
    # below instructs the model to return "None" for titles that don't
    # clearly fit one of the ten personas above.
}

PERSONA_LIST_TEXT = "\n".join(f"- {name}: {desc}" for name, desc in PERSONA_DEFINITIONS.items())

SYSTEM_PROMPT = f"""You are classifying B2B contact job titles into persona buckets for a CRM.

Here are the only valid personas:
{PERSONA_LIST_TEXT}

Rules:
- Pick the SINGLE best-fitting persona for each title.
- If a title genuinely doesn't fit any persona above (e.g. an individual
  contributor role, an unrelated function, or too vague to tell), return "None".
  Do not force a fit.
- Respond with ONLY a JSON array, no other text, no markdown fences.
- Each element: {{"id": <row id given>, "persona": <exact persona name from the list, or "None">}}
- The array must have exactly as many elements as titles given, in any order, matched by id.
"""


def is_blank(title):
    return pd.isna(title) or str(title).strip() == ""


def is_garbled(title):
    """Heuristic mojibake/garbage detector. Catches things like encoding
    round-trip corruption (Ã¢â‚¬..., control characters, unicode replacement
    chars) without flagging legitimate non-English titles (CJK, Korean,
    accented Latin, etc.)."""
    if is_blank(title):
        return False
    s = str(title)
    if "\ufffd" in s:  # unicode replacement character (�)
        return True
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", s):  # stray control chars
        return True
    if re.search(r"â€|[ÃÂ][€™¢œ¦°¯²³¡¢£¤¥¦§¨©ª«¬­®]", s):  # classic utf-8/windows-1252 mojibake
        return True
    non_ascii = sum(1 for c in s if ord(c) > 127)
    has_cjk_or_hangul = bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", s))
    if len(s) > 0 and non_ascii / len(s) > 0.5 and not has_cjk_or_hangul:
        return True
    return False


def classify_batch(rows):
    """rows: list of (row_id, job_title) tuples"""
    user_content = "Classify these job titles:\n\n" + "\n".join(
        f'{{"id": {rid}, "title": {json.dumps(title)}}}' for rid, title in rows
    )
    for attempt in range(4):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = resp.content[0].text.strip()
            text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(text)
            return {int(item["id"]): item["persona"] for item in parsed}
        except Exception as e:
            wait = 2 ** attempt
            print(f"  batch failed ({e}), retrying in {wait}s...")
            time.sleep(wait)
    print("  batch permanently failed, leaving these rows blank:", [r[0] for r in rows])
    return {}


def main():
    df = pd.read_csv(STAGE1_CSV)
    if "Needs_Stage2_LLM" not in df.columns:
        raise ValueError("Expected a Needs_Stage2_LLM column -- did you run stage1_regex_match.py first?")

    candidates = df[df["Needs_Stage2_LLM"] == True].copy()
    candidates = candidates.reset_index().rename(columns={"index": "_row_id"})
    print(f"Rows flagged after stage 1: {len(candidates)}")

    blank_mask = candidates["Job Title"].apply(is_blank)
    garbled_mask = candidates["Job Title"].apply(is_garbled) & ~blank_mask

    for row_id in candidates.loc[blank_mask, "_row_id"]:
        df.loc[row_id, "Persona_Match_Method"] = "skipped_blank"
    for row_id in candidates.loc[garbled_mask, "_row_id"]:
        df.loc[row_id, "Persona_Match_Method"] = "skipped_garbled"

    to_classify = candidates.loc[~blank_mask & ~garbled_mask]
    print(f"Skipped (blank): {blank_mask.sum()}")
    print(f"Skipped (garbled/mojibake): {garbled_mask.sum()}")
    print(f"Sending to LLM: {len(to_classify)}")

    results = {}
    rows = list(zip(to_classify["_row_id"], to_classify["Job Title"].fillna("")))
    n_batches = (len(rows) - 1) // BATCH_SIZE + 1 if rows else 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        print(f"Classifying batch {i // BATCH_SIZE + 1}/{n_batches}...")
        results.update(classify_batch(batch))
        time.sleep(0.5)  # light rate-limit courtesy

    matched = 0
    for row_id, persona in results.items():
        if persona and persona != "None":
            df.loc[row_id, "Persona"] = persona
            df.loc[row_id, "Persona_Match_Method"] = "llm"
            matched += 1
        else:
            df.loc[row_id, "Persona_Match_Method"] = "llm_none"

    print(f"LLM matched: {matched} / {len(to_classify)}")
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved final output to {OUTPUT_PATH}")
    print(df["Persona_Match_Method"].value_counts())


if __name__ == "__main__":
    main()
