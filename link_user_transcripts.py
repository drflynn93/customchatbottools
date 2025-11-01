from pathlib import Path
import re
import sys
import argparse
import pandas as pd
from difflib import get_close_matches

# --------------------------
# CONFIG DEFAULTS (Windows)
# --------------------------
DEFAULT_BASE = r"C:\Users\KAFLYNN\Desktop\chatgpt_transcripts"
DEFAULT_TXT_DIR = "TXT_users"
DEFAULT_MASTER_XLSX = "Master10212025matching.xlsx"  # adjust if needed
DEFAULT_OUT_CSV = "transcript_user_links.csv"
DEFAULT_RENAMED_DIR = "TXT_users_named"

# --------------------------
# Regex helpers
# --------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# common "name" line patterns to search near top or near email lines
NAME_HINTS = [
    re.compile(r"^\s*name\s*:?\s*(.+)$", re.IGNORECASE),
    re.compile(r"^\s*my\s+name\s+is\s+(.+)$", re.IGNORECASE),
    re.compile(r"^\s*i\s*am\s+(.+)$", re.IGNORECASE),
]

# A loose "looks like a person name" filter (Firstname Lastname, 2–4 words, mostly letters/-.')
def looks_like_name(text: str) -> bool:
    tokens = re.split(r"\s+", text.strip())
    if not (2 <= len(tokens) <= 4):
        return False
    for t in tokens:
        if not re.match(r"^[A-Za-z][A-Za-z\.'\-]*$", t):
            return False
    # Avoid sentences
    if any(p in text for p in [".", "!", "?","@"]):
        return False
    return True

def clean_name(n: str) -> str:
    # Strip trailing punctuation and extra spaces; Title Case
    n = re.sub(r"[\s,]+$", "", n.strip())
    return " ".join(w.capitalize() for w in n.split())

def normalize_email(e: str) -> str:
    return e.strip().lower()

def username_part(e: str) -> str:
    e = normalize_email(e)
    return e.split("@")[0] if "@" in e else e

# --------------------------
# Extraction from transcript
# --------------------------
def extract_email_and_name(text: str):
    # emails
    emails = EMAIL_RE.findall(text)
    emails = list(dict.fromkeys(emails))  # de-dup preserve order

    # try name hints line-by-line
    name = None
    for line in text.splitlines():
        ln = line.strip()
        for pat in NAME_HINTS:
            m = pat.match(ln)
            if m:
                candidate = m.group(1).strip(" :-\t")
                # Stop at first delimiter like "email:" inside name lines
                candidate = re.split(r"(?:email|mail)\s*:?", candidate, flags=re.I)[0].strip()
                if looks_like_name(candidate):
                    name = clean_name(candidate)
                    break
        if name:
            break

    # If still no name, guess using a line near the first email
    if not name and emails:
        first_email = emails[0]
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if first_email in line:
                # look a couple of lines above for a likely name
                window = lines[max(0, i-3):i]
                for cand in reversed(window):
                    cand = cand.strip(" :-\t")
                    if looks_like_name(cand):
                        name = clean_name(cand)
                        break
                break

    return emails, name

# --------------------------
# Matching to master
# --------------------------
def load_master(master_path: Path):
    # Try to be flexible on column names
    df = pd.read_excel(master_path, engine="openpyxl")
    cols = {c.lower(): c for c in df.columns}

    # Expected columns (customize these if your sheet differs)
    name_col = cols.get("name") or cols.get("student_name") or cols.get("fullname") or list(df.columns)[0]
    email_col = cols.get("email") or cols.get("e-mail") or cols.get("mail")
    id_col = cols.get("studentid") or cols.get("student_id") or cols.get("id")

    # Create a normalized view
    def low(s): 
        return s.astype(str).str.strip().str.lower()

    df["_name_norm"]  = low(df[name_col]) if name_col else ""
    df["_email_norm"] = low(df[email_col]) if email_col else ""
    df["_user_norm"]  = df["_email_norm"].str.split("@").str[0]
    df["_id"]         = df[id_col] if id_col else ""

    return df, name_col, email_col, id_col

def fuzzy_match_name(candidate_name: str, master_df: pd.DataFrame, cutoff=0.85):
    if not candidate_name:
        return None
    master_names = master_df["_name_norm"].tolist()
    cand = candidate_name.strip().lower()
    hits = get_close_matches(cand, master_names, n=1, cutoff=cutoff)
    if hits:
        match = hits[0]
        row = master_df.loc[master_df["_name_norm"] == match].head(1)
        if not row.empty:
            return row.iloc[0]
    return None

def match_record(emails, name, master_df: pd.DataFrame):
    # 1) exact email match
    for e in emails:
        e_norm = normalize_email(e)
        row = master_df.loc[master_df["_email_norm"] == e_norm].head(1)
        if not row.empty:
            return "email_exact", row.iloc[0]

    # 2) username (before @) match
    for e in emails:
        u = username_part(e)
        if not u:
            continue
        row = master_df.loc[master_df["_user_norm"] == u].head(1)
        if not row.empty:
            return "email_username", row.iloc[0]

    # 3) fuzzy name match
    row = fuzzy_match_name(name, master_df, cutoff=0.86) if name else None
    if row is not None:
        return "name_fuzzy", row

    return None, None

# --------------------------
# Main
# --------------------------
def main():
    parser = argparse.ArgumentParser(description="Link user-only transcript .txt files to master roster by email/name.")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Base folder (default: your Desktop chatgpt_transcripts).")
    parser.add_argument("--txt_dir", default=DEFAULT_TXT_DIR, help="Folder under base containing user-only .txt files.")
    parser.add_argument("--master", default=DEFAULT_MASTER_XLSX, help="Master Excel filename under base.")
    parser.add_argument("--out_csv", default=DEFAULT_OUT_CSV, help="Output mapping CSV filename under base.")
    parser.add_argument("--rename", action="store_true", help="Also rename files into a new folder using matched IDs/names.")
    parser.add_argument("--renamed_dir", default=DEFAULT_RENAMED_DIR, help="Folder for renamed files (under base).")
    args = parser.parse_args()

    base = Path(args.base)
    txt_dir = base / args.txt_dir
    master_path = base / args.master
    out_csv = base / args.out_csv
    renamed_dir = base / args.renamed_dir

    if not txt_dir.exists():
        print(f"[ERROR] Transcript folder not found: {txt_dir}", file=sys.stderr)
        sys.exit(1)
    if not master_path.exists():
        print(f"[ERROR] Master Excel not found: {master_path}", file=sys.stderr)
        sys.exit(1)

    master_df, name_col, email_col, id_col = load_master(master_path)

    rows = []
    files = sorted(txt_dir.glob("*.txt"))
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            # normalize newlines
            text = text.replace("\r\n","\n").replace("\r","\n")
        except Exception as e:
            print(f"[WARN] Could not read {p}: {e}", file=sys.stderr)
            continue

        emails, guessed_name = extract_email_and_name(text)
        method, matched = match_record(emails, guessed_name, master_df)

        mapped = {
            "filename": p.name,
            "filepath": str(p),
            "extracted_email": ";".join(emails) if emails else "",
            "extracted_name": guessed_name or "",
            "match_method": method or "",
            "matched_name": (matched[name_col] if (matched is not None and name_col) else ""),
            "matched_email": (matched[email_col] if (matched is not None and email_col) else ""),
            "matched_student_id": (matched["_id"] if (matched is not None and "_id" in matched) else ""),
        }
        rows.append(mapped)

        # Optional rename/copy into named folder
        if args.rename and matched is not None:
            renamed_dir.mkdir(parents=True, exist_ok=True)
            # Build a safe filename: ID_FirstLast_user.txt if ID exists, else FirstLast_user.txt
            firstlast = clean_name(str(matched[name_col])) if name_col else ""
            sid = str(matched["_id"]) if matched["_id"] != "" else ""
            if sid and sid.lower() != "nan":
                new_stem = f"{sid}_{firstlast}".strip("_")
            else:
                new_stem = firstlast or p.stem
            safe = re.sub(r"[^A-Za-z0-9_\- ]", "", new_stem).strip().replace(" ", "")
            new_name = f"{safe}_user.txt"
            target = renamed_dir / new_name
            try:
                # write (not move) so original remains
                target.write_text(text, encoding="utf-8", errors="ignore")
            except Exception as e:
                print(f"[WARN] Could not write {target}: {e}", file=sys.stderr)

    out_df = pd.DataFrame(rows)
    out_df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[DONE] Wrote mapping for {len(rows)} file(s) to: {out_csv}")
    if args.rename:
        print(f"[DONE] Renamed copies written to: {renamed_dir}")

if __name__ == "__main__":
    main()
