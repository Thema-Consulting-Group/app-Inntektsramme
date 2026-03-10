import os
import pandas as pd
import re

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FILE = os.path.join(_BASE, "Data", "kundetillegg_raw.csv")
OUTPUT_FILE = os.path.join(_BASE, "Data", "kundetillegg.csv")

def clean_numeric(value):
    """Strip whitespace, remove thousands-separator spaces, and convert '-' to 0."""
    s = str(value).strip()
    if s == "-":
        return 0
    # Remove spaces used as thousands separators (e.g. "1 000" -> "1000")
    s = re.sub(r"(\d)\s+(\d)", r"\1\2", s)
    # Try to convert to int; fall back to original cleaned string
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s

df = pd.read_csv(INPUT_FILE, sep=";", encoding="cp1252")

numeric_cols = ["Tillegg i K*", "Tillegg i IR"]
for col in numeric_cols:
    if col in df.columns:
        df[col] = df[col].apply(clean_numeric)

df.to_csv(OUTPUT_FILE, sep=";", index=False, encoding="utf-8-sig")
print(f"Saved cleaned file to {OUTPUT_FILE}")
  