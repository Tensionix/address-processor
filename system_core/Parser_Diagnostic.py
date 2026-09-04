import pandas as pd
import sys
from pathlib import Path
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core.Ultimate_GT_Aligner import parse_address

tqdm.pandas()

def parse_like_a_human(address):
    ter, street_words, street_nums, house_base, house_mods = parse_address(address)
    visible_words = " ".join(part for part in (ter, street_words) if part)
    return visible_words, ", ".join(sorted(street_nums)), house_base, house_mods

def run_diagnostic(input_file, output_file):
    print(f"\n[INFO] Analyzing {input_file.name}...")
    df = pd.read_excel(input_file, header=None)
    
    ref_col_name = df.columns[1] # Берем Столбец B как базу для теста
    target_data = df[[ref_col_name]].copy().dropna()
    
    results = []
    print("[INFO] Parsing addresses...")
    for orig in tqdm(target_data[ref_col_name], desc="Extracting"):
        w, n, hb, hm = parse_like_a_human(orig)
        results.append({
            "Original_Address": orig,
            "Street_Words": w,
            "Street_Numbers": n,
            "House_Base": hb,
            "House_Mods": hm
        })
        
    out_df = pd.DataFrame(results)
    out_df.to_excel(output_file, index=False)
    print(f"[SUCCESS] Diagnostic saved to {output_file.name}")

if __name__ == "__main__":
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    for file_path in in_dir.glob("*.xlsx"):
        out_file = out_dir / f"Diagnostic_{file_path.name}"
        run_diagnostic(file_path, out_file)
        from system_core.excel_layout import format_workbook

        format_workbook(out_file)
        print(f"[INFO] Auto-layout applied: {out_file.name}")
