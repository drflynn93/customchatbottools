from pathlib import Path
import re
import sys

# --- Adjust ONLY this base folder if your Desktop path is different ---
BASE = Path(r"C:\Users\KAFLYNN\Desktop\chatgpt_transcripts")

SRC = BASE / "transcripts_raw"   # your raw transcripts
OUT = BASE / "TXT_users"         # user-only output (LIWC-ready)
GLOB = "*.txt"                   # only plain .txt files in SRC (no recursion)

# --- Speaker markers ---
# Primary pattern: "You said:" (user), "<anything> said:" (agent)
USER_SAID = re.compile(r"^\s*You\s+said:\s*$", re.IGNORECASE)
AGENT_SAID = re.compile(r"^\s*(?!You\b)[\w\s]+said:\s*$", re.IGNORECASE)

# Alternative format pattern: "User:" (user), "Assistant:" or "ChatGPT:" etc. (agent)
USER_COLON = re.compile(r"^\s*(You|User)\s*:\s*$", re.IGNORECASE)
AGENT_COLON = re.compile(r"^\s*(Assistant|ChatGPT|AI|Breakeven)\s*:\s*$", re.IGNORECASE)

def extract_user_text(lines):
    """
    Extract only the user's text given a list of lines from one transcript.
    Supports both "... said:" and "User:/Assistant:" styles.
    """
    current = None
    out = []

    for raw in lines:
        ln = raw.rstrip("\n\r")

        # Switch on markers (order matters: check for explicit markers first)
        if USER_SAID.match(ln) or USER_COLON.match(ln):
            current = "user"
            continue
        if AGENT_SAID.match(ln) or AGENT_COLON.match(ln):
            current = "agent"
            continue

        if current == "user":
            out.append(ln)

    return "\n".join(out).strip()

def main():
    # Make sure folders exist
    OUT.mkdir(parents=True, exist_ok=True)
    if not SRC.exists():
        print(f"[ERROR] Source folder not found: {SRC}", file=sys.stderr)
        sys.exit(1)

    paths = list(SRC.glob(GLOB))
    if not paths:
        print(f"[WARN] No .txt files found in: {SRC}")
        sys.exit(0)

    total = 0
    wrote = 0

    for p in paths:
        if not p.is_file():
            continue
        total += 1

        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[WARN] Could not read {p}: {e}", file=sys.stderr)
            continue

        # Normalize newlines and strip BOM if present
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")

        user_text = extract_user_text(text.split("\n"))

        out_name = f"{p.stem}_user.txt"
        out_path = OUT / out_name

        try:
            out_path.write_text(user_text, encoding="utf-8", errors="ignore")
            wrote += 1
        except Exception as e:
            print(f"[WARN] Could not write {out_path}: {e}", file=sys.stderr)

    print(f"Processed {total} file(s); wrote {wrote} user-only file(s) to: {OUT}")

if __name__ == "__main__":
    main()
