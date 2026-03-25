"""
03_extract_and_display.py
--------------------------
End-to-end script: classify a document, extract fields, and print
them in a clean, readable table with field names, values, and
confidence scores.

Also saves the output of each segment to its own text file.

Three modes:
  Interactive : Run the script with no arguments. It will prompt for a PDF file.
  --file      : Run the full pipeline (classify + extract via Azure API),
                then display the extracted fields.
  --json      : Read a previously saved output JSON and display fields
                offline (no Azure API call needed).

Usage:
    python scripts/03_extract_and_display.py
    python scripts/03_extract_and_display.py --file data/1738127724775.pdf
    python scripts/03_extract_and_display.py --json output/mixed_financial_docs_all_segments_result.json
"""

import os
import sys
import json
import argparse
import subprocess

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def unwrap_data(obj):
    """Recursively removes the Azure SDK '_data' wrapper if present."""
    if isinstance(obj, dict):
        if "_data" in obj:
            return unwrap_data(obj["_data"])
        return {k: unwrap_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [unwrap_data(i) for i in obj]
    return obj


def get_field_value(field_data: dict) -> str:
    """Extract the display value from a field dict, regardless of type."""
    if "valueString"  in field_data:
        return str(field_data["valueString"])
    if "valueNumber"  in field_data:
        return str(field_data["valueNumber"])
    if "valueDate"    in field_data:
        return str(field_data["valueDate"])
    if "valueBoolean" in field_data:
        return str(field_data["valueBoolean"])
    if "valueArray"   in field_data:
        return json.dumps(field_data["valueArray"], ensure_ascii=False)
    # Field was recognised but no value extracted
    return "(not found)"


def extract_fields_from_result(result: dict) -> list:
    """
    Navigate the nested API result structure and return a flat list of
    {"name", "value", "type", "confidence"} dicts sorted by confidence.
    """
    # Thoroughly unwrap the SDK model bindings first
    result = unwrap_data(result)

    # Unwrap "extracted_fields" wrapper if present
    if "extracted_fields" in result:
        result = result["extracted_fields"]

    contents = result.get("result", result).get("contents", [])
    fields_dict = contents[0].get("fields", {}) if contents else {}

    rows = []
    for name, data in fields_dict.items():
        if not isinstance(data, dict):
            continue
        rows.append({
            "name":       name,
            "value":      get_field_value(data),
            "type":       data.get("type", "?"),
            "confidence": data.get("confidence", 0.0),
        })

    rows.sort(key=lambda r: r["confidence"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Display & Saving helpers
# ---------------------------------------------------------------------------

def print_and_save_segment_fields(base_filename: str, seg_num, category: str, pages: str, fields: list):
    """Print one segment's fields as an aligned table and save it to a text file."""
    lines = []
    lines.append(f"Segment {seg_num}: [{category}]  (pages {pages})")
    lines.append("")

    if not fields:
        lines.append("  (no fields extracted)")
    else:
        # Column widths
        name_w  = max(max(len(f["name"])  for f in fields), 20)
        value_w = min(max(max(len(f["value"]) for f in fields), 15), 60)

        sep  = "+" + "-" * (name_w + 2) + "+" + "-" * (value_w + 2) + \
               "+" + "-" * 12 + "+"
        hdr  = (f"| {'Field':<{name_w}} | {'Value':<{value_w}} "
                f"| {'Confidence':>10} |")

        lines.append(sep)
        lines.append(hdr)
        lines.append(sep)

        for f in fields:
            val = f["value"]
            if len(val) > value_w:
                val = val[:value_w - 3] + "..."

            conf = f["confidence"]

            lines.append(
                f"| {f['name']:<{name_w}} "
                f"| {val:<{value_w}} "
                f"| {conf:>10.3f} |"
            )

        lines.append(sep)

    output_str = "\n".join(lines)
    
    # Indent it slightly for terminal printing
    print("\n  " + output_str.replace("\n", "\n  "))

    # Save to a text file
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    out_dir = os.path.join(project_root, "output")
    os.makedirs(out_dir, exist_ok=True)

    out_file_name = f"{base_filename}_segment{seg_num}_{category}_fields.txt"
    out_path = os.path.join(out_dir, out_file_name)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output_str + "\n")
    
    print(f"  -> Saved text output to: output/{out_file_name}")


# ---------------------------------------------------------------------------
# Mode 1: Run classify-and-route pipeline, then display
# ---------------------------------------------------------------------------

def run_pipeline_and_display(file_paths: list):
    """Call 02_classify_and_route.py via subprocess, then display results."""
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    pipeline     = os.path.join(script_dir, "02_classify_and_route.py")
    project_root = os.path.dirname(script_dir)

    for file_path in file_paths:
        print(f"\n{'=' * 60}")
        print(f"  Running pipeline: {file_path}")
        print(f"{'=' * 60}\n")

        proc = subprocess.run(
            [sys.executable, pipeline, "--file", file_path],
            cwd=project_root,
        )

        if proc.returncode != 0:
            print(f"[FAIL] Pipeline exited with errors for: {file_path}")
            continue

        base = os.path.splitext(os.path.basename(file_path))[0]
        out_json = os.path.join(project_root, "output",
                                f"{base}_all_segments_result.json")

        if not os.path.exists(out_json):
            print(f"[FAIL] Output JSON not found: {out_json}")
            continue

        display_from_json([out_json])


# ---------------------------------------------------------------------------
# Mode 2: Read existing output JSON and display
# ---------------------------------------------------------------------------

def display_from_json(json_paths: list):
    """Parse saved output JSONs and print/save extracted fields."""
    for json_path in json_paths:
        if not os.path.exists(json_path):
            print(f"[FAIL] File not found: {json_path}")
            continue

        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        title = os.path.basename(json_path)
        base_filename = title.replace("_all_segments_result.json", "")
        base_filename = base_filename.replace("_result.json", "")

        print(f"\n{'=' * 60}")
        print(f"  EXTRACTED FIELDS  --  {title}")
        print(f"{'=' * 60}")

        # --- "all_segments" format: top-level has "segments" list ---
        if "segments" in data and isinstance(data["segments"], list):
            for seg in data["segments"]:
                seg_num    = seg.get("segment", "?")
                category   = seg.get("category", "unknown")
                pages      = seg.get("pages", "?")
                extraction = seg.get("extracted_fields")

                if not extraction:
                    print(f"\n  Segment {seg_num}: [{category}] (pages {pages})")
                    print("    (no extraction — no analyzer mapped for this category)")
                    continue

                fields = extract_fields_from_result(extraction)
                print_and_save_segment_fields(base_filename, seg_num, category, pages, fields)

        # --- single segment format: top-level has "extracted_fields" ---
        elif "extracted_fields" in data:
            seg_num  = data.get("segment", 1)
            category = data.get("category", "unknown")
            pages    = data.get("pages", "?")
            fields   = extract_fields_from_result(data["extracted_fields"])
            print_and_save_segment_fields(base_filename, seg_num, category, pages, fields)

        # --- raw API result format ---
        elif "result" in data:
            fields = extract_fields_from_result(data)
            print_and_save_segment_fields(base_filename, 1, "raw", "?", fields)

        else:
            print("  [WARN] Unrecognised JSON format — cannot display fields.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Classify and extract fields from PDF documents, then display results.",
        epilog=(
            "Examples:\n"
            "  python scripts/03_extract_and_display.py\n"
            "  python scripts/03_extract_and_display.py --file data/report.pdf\n"
            "  python scripts/03_extract_and_display.py "
            "--json output/report_all_segments_result.json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--file", nargs="+", metavar="PDF",
        help="PDF(s) to classify and extract via the Azure API"
    )
    group.add_argument(
        "--json", nargs="+", metavar="JSON",
        help="Previously saved output JSON(s) to display (no API call)"
    )

    args = parser.parse_args()

    if args.file:
        run_pipeline_and_display(args.file)
    elif args.json:
        display_from_json(args.json)
    else:
        # Interactive mode
        file_path = input("Enter the path to the PDF file to process: ").strip()
        
        # Remove any surrounding quotes if they dragged and dropped the file
        file_path = file_path.strip("\"'")
        
        if not file_path:
            print("No file path provided. Exiting.")
            sys.exit(0)
            
        if not os.path.exists(file_path):
            print(f"[FAIL] File not found: {file_path}")
            sys.exit(1)
            
        run_pipeline_and_display([file_path])

    print("\n[OK] Done.")


if __name__ == "__main__":
    main()
