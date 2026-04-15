"""
02_classify_and_route.py
------------------------
THE MAIN FILE.

Uses enableSegment=true — Azure splits the PDF into segments automatically.
Each segment is classified independently and routed to its own field extractor.

It can be run interactively or by passing arguments.

Example: A loan bundle PDF with 3 pages gets split into:
  Segment 1 → loan_application → my_loan_application_analyzer
  Segment 2 → kyc_document     → my_kyc_analyzer
  Segment 3 → invoice          → my_invoice_analyzer

Usage:
    python scripts/02_classify_and_route.py
    python scripts/02_classify_and_route.py --file data/sample.pdf
    python scripts/02_classify_and_route.py --file data/doc1.pdf data/doc2.pdf
"""

import os
import sys
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

# ------------------------------------------------------------------
# CATEGORY : ANALYZER MAP
# analyzer_id : Classifier 
# NOTE: analyzer_id must use underscores only, NO hyphens but classifier must use camilcase without spaces,hyphens or underscores.
# ------------------------------------------------------------------
CATEGORY_ANALYZER_MAP = {
    "loan_application": "myLoanApplicationAnalyzer",
    "invoice":          "myInvoiceAnalyzer",
    "contract":         "myContractAnalyzer",
    "purchase_order":   "myPurchaseOrderAnalyzer",
    "kyc_document":     "myKycAnalyzer",
    "medical_report":   "myMedicalReportAnalyzer",
    "bank_statement":   "myBankStatementAnalyzer",
}

CLASSIFIER_ANALYZER_ID = "myClassifier"


def make_client() -> ContentUnderstandingClient:
    return ContentUnderstandingClient(
        endpoint=os.environ["AZURE_AI_ENDPOINT"],
        credential=AzureKeyCredential(os.environ["AZURE_AI_API_KEY"])
    )


# ---------------------------------------------------------------------------
# Utility & Extraction Helpers
# ---------------------------------------------------------------------------

def to_dict(obj):
    """Deep convert SDK models to dicts and remove '_data' wrappers."""
    if isinstance(obj, (dict, list)):
        # If it's already a dict or list, we still want to unwrap the internal values
        if isinstance(obj, dict):
            if "_data" in obj: return to_dict(obj["_data"])
            return {k: to_dict(v) for k, v in obj.items()}
        return [to_dict(i) for i in obj]
    
    # Check if it's an SDK object with a dict representation
    if hasattr(obj, "__dict__") or hasattr(obj, "items"):
        try:
            # Most Azure SDK objects can be serialized via json.dumps/loads loop
            # to get a clean, nested dictionary structure.
            raw = json.loads(json.dumps(obj, default=lambda x: getattr(x, '__dict__', str(x))))
            return to_dict(raw)
        except Exception:
            return str(obj)
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
        cleaned_list = []
        for item in field_data["valueArray"]:
            if "valueObject" in item:
                # Map inner properties cleanly
                cleaned = {k: get_field_value(v) for k, v in item["valueObject"].items()}
                cleaned_list.append(cleaned)
            else:
                cleaned_list.append(get_field_value(item))
        return json.dumps(cleaned_list, ensure_ascii=False)
    # Field was recognised but no value extracted
    return "(not found)"


def extract_fields_from_dict(fields_dict: dict, prefix="") -> list:
    """Helper to recursively extract fields, especially flattening object arrays."""
    rows = []
    for name, data in fields_dict.items():
        if not isinstance(data, dict):
            continue
            
        full_name = f"{prefix}{name}"
        
        # If it's an array of objects, unpack it so we don't lose confidence scores
        if data.get("type") == "array" and "valueArray" in data:
            is_object_array = any(isinstance(item, dict) and "valueObject" in item for item in data["valueArray"])
            if is_object_array:
                for idx, item in enumerate(data["valueArray"]):
                    if isinstance(item, dict) and "valueObject" in item:
                        rows.extend(extract_fields_from_dict(item["valueObject"], prefix=f"{full_name}[{idx+1}]."))
                continue
                
        # If it's a single object (not in an array), we could also unpack it
        if data.get("type") == "object" and "valueObject" in data:
            rows.extend(extract_fields_from_dict(data["valueObject"], prefix=f"{full_name}."))
            continue
            
        rows.append({
            "name":       full_name,
            "value":      get_field_value(data),
            "type":       data.get("type", "?"),
            "confidence": data.get("confidence", 0.0),
        })
    return rows

def extract_fields_from_result(result: dict) -> list:
    """
    Navigate the nested API result structure and return a flat list of
    {"name", "value", "type", "confidence"} dicts sorted by schema order.
    """
    # Thoroughly unwrap the SDK model bindings and _data markers
    result = to_dict(result)

    # Unwrap "extracted_fields" wrapper if it's a saved JSON format
    if "extracted_fields" in result:
        result = result["extracted_fields"]

    contents = result.get("result", result).get("contents", [])
    fields_dict = contents[0].get("fields", {}) if contents else {}

    # Return nested items in document order (no sort)
    return extract_fields_from_dict(fields_dict)


def print_and_save_segment_fields(base_filename: str, seg_num, category: str, pages: str, fields: list):
    """Print one segment's fields as an aligned table and save it to a text file."""
    lines = []
    lines.append(f"Segment {seg_num}: [{category}]  (pages {pages})")
    lines.append("")

    if not fields:
        lines.append("  (no fields extracted)")
    else:
        name_w  = max(len(f["name"]) for f in fields) if fields else 20

        for f in fields:
            val = f["value"]
            conf = f["confidence"]
            lines.append(f"{f['name']:<{name_w}} : {val} ({conf:.3f})")

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
# Core pipeline logic
# ---------------------------------------------------------------------------

def classify_document(client, file_path: str) -> tuple:
    """Classify the document and check for multiple overlapping categories."""
    print(f"\nClassifying (with segment splitting): {file_path}")

    t0 = time.perf_counter()
    with open(file_path, "rb") as f:
        poller = client.begin_analyze_binary(CLASSIFIER_ANALYZER_ID, binary_input=f.read())
        result_dict = to_dict(poller.result())
    print(f" Classification completed in {time.perf_counter() - t0:.1f}s")

    # Segments are natively inside the first content item
    contents = result_dict.get("contents", [])
    segments = contents[0].get("segments", []) if contents else []

    # Check for multiple categories found on the same page via our custom field
    fields = contents[0].get("fields", {}) if contents else {}
    mult_array = fields.get("multiple_categories_found", {}).get("valueArray", [])
    
    extracted_cats = [item.get("valueString") for item in mult_array if "valueString" in item]
    existing_cats = set(s.get("category") for s in segments)
    
    # Append 'virtual' segments for categories found by the AI but not segmented by page
    for c in extracted_cats:
        if c not in existing_cats and c in CATEGORY_ANALYZER_MAP:
            segments.append({
                "category": c,
                "startPageNumber": 1,
                "endPageNumber": contents[0].get("pages", [{}])[-1].get("pageNumber", 1) if contents else 1,
                "_virtual": True
            })

    print(f"[OK] Found {len(segments)} segment(s) to process:")
    for i, seg in enumerate(segments):
        cat, start, end = seg.get("category"), seg.get("startPageNumber"), seg.get("endPageNumber")
        v_flag = " (virtual routing)" if seg.pop("_virtual", False) else ""
        print(f"   Segment {i+1}: [{cat}] (pages {start}–{end}){v_flag}")

    return segments, result_dict


def extract_fields_from_binary(client, file_content: bytes, analyzer_id: str, start_page: int = None, end_page: int = None) -> dict:
    """Run the field extraction analyzer on a specific page range (thread-safe, no printing)."""
    content_range = f"{start_page}-{end_page}" if start_page and end_page else None
    poller = client.begin_analyze_binary(analyzer_id, binary_input=file_content, content_range=content_range)
    return to_dict(poller.result())


def save_output(data: dict, filename: str):
    """Save result dict to output/ folder as JSON."""
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    out_dir = os.path.join(project_root, "output")
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _process_analyzer_group(client, file_content: bytes, analyzer_id: str, seg_items: list, results: dict):
    """
    Process a group of segments that share the same analyzer — SERIALLY.
    Called from a thread. Stores results in the shared `results` dict keyed by segment index.
    """
    for seg_index, seg in seg_items:
        cat   = seg["category"]
        start = seg["startPageNumber"]
        end   = seg["endPageNumber"]

        if not analyzer_id:                       # unmapped category
            results[seg_index] = {
                "segment": seg_index + 1, "category": cat,
                "pages": f"{start}–{end}", "note": "Unmapped"
            }
            continue

        extraction = extract_fields_from_binary(client, file_content, analyzer_id, start, end)
        results[seg_index] = {
            "segment": seg_index + 1, "category": cat,
            "pages": f"{start}–{end}", "analyzer_used": analyzer_id,
            "extracted_fields": extraction
        }


def process_file(client, file_path: str) -> dict:
    """
    Full pipeline: classify → route → extract (parallel by analyzer) → save & print.

    Segments that use DIFFERENT analyzers run in PARALLEL.
    Segments that share the SAME analyzer run SERIALLY within their group.
    All output is printed cleanly AFTER extraction completes.
    """
    print(f"\n{'='*60}\n  Processing: {file_path}\n{'='*60}")

    if not os.path.exists(file_path):
        print(f"[FAIL] File not found: {file_path}"); return {}

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    segments, class_res = classify_document(client, file_path)
    save_output(class_res, f"{base_name}_classification.json")

    if not segments:
        print("[ WARN ] No segments found."); return {}

    # Read file once — shared across all threads (bytes are immutable, thread-safe)
    with open(file_path, "rb") as f:
        file_content = f.read()

    # ── Group segments by analyzer ──────────────────────────────────────
    analyzer_groups = defaultdict(list)       # analyzer_id → [(seg_index, seg), ...]
    for i, seg in enumerate(segments):
        analyzer_id = CATEGORY_ANALYZER_MAP.get(seg["category"])
        key = analyzer_id or ""               # empty string = unmapped
        analyzer_groups[key].append((i, seg))

    unique_analyzers = [k for k in analyzer_groups if k]   # non-empty = real analyzers
    print(f"\n Launching {len(unique_analyzers)} analyzer group(s) in parallel "
          f"({len(segments)} segment(s) total)…")
    for aid, items in analyzer_groups.items():
        label = aid if aid else "(unmapped)"
        seg_list = ", ".join(f"Seg {i+1}" for i, _ in items)
        print(f"   {label}: {seg_list}  [serial within group]")

    # ── Run groups in parallel ──────────────────────────────────────────
    results = {}                              # seg_index → result dict
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=max(len(analyzer_groups), 1)) as pool:
        futures = {
            pool.submit(_process_analyzer_group, client, file_content, aid, items, results): aid
            for aid, items in analyzer_groups.items()
        }
        for future in as_completed(futures):
            future.result()                   # re-raise any thread exceptions

    elapsed = time.perf_counter() - t0
    print(f"\n All extractions completed in {elapsed:.1f}s")

    # ── Print & save results IN SEGMENT ORDER ───────────────────────────
    all_segment_results = []
    for i in range(len(segments)):
        res = results.get(i, {})
        seg_num = i + 1
        cat   = segments[i]["category"]
        start = segments[i]["startPageNumber"]
        end   = segments[i]["endPageNumber"]

        print(f"\n--- Segment {seg_num}/{len(segments)}: [{cat}] (pages {start}–{end}) ---")

        if res.get("note") == "Unmapped":
            print(f"[ WARN ] No analyzer for '{cat}' — skipped.")
        elif "extracted_fields" in res:
            save_output(res, f"{base_name}_segment{seg_num}_{cat}_result.json")
            print(f"Saved JSON → output/{base_name}_segment{seg_num}_{cat}_result.json")

            print(f"\n{'='*60}\n  EXTRACTED FIELDS -- Segment {seg_num}\n{'='*60}")
            print_and_save_segment_fields(
                base_name, seg_num, cat, f"{start}–{end}",
                extract_fields_from_result(res["extracted_fields"])
            )

        all_segment_results.append(res)

    final = {"file": file_path, "total_segments": len(segments), "segments": all_segment_results}
    save_output(final, f"{base_name}_all_segments_result.json")
    print(f"\nDone! {len(segments)} segment(s) processed for: {file_path}")
    return final


def main():
    print("\n--- Azure Content Understanding: Multi-File Input ---")
    print("Enter a file path, a folder path, or a comma-separated list of paths.")
    user_input = input("Target path(s): ").strip().strip("\"'")
    
    if not user_input:
        print("No input provided. Exiting."); return

    client = make_client(); all_results = []
    
    # 1. Split by commas for multiple explicit paths
    raw_paths = [p.strip().strip("\"'") for p in user_input.split(",")]
    
    # 2. Expand folder paths if provided
    final_paths = []
    for p in raw_paths:
        if os.path.isdir(p):
            for f in os.listdir(p):
                if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                    final_paths.append(os.path.join(p, f))
        elif os.path.isfile(p):
            final_paths.append(p)
        else:
            print(f"[WARN] Path not found or unsupported: {p}")

    if not final_paths:
        print("No valid files found. Exiting."); return

    print(f"\nProcessing {len(final_paths)} file(s)...")
    for path in final_paths:
        result = process_file(client, path)
        if result: all_results.append(result)

    if len(all_results) > 1:
        save_output(all_results, "combined_results.json")
        print("\n[Succeeded] Combined results saved → output/combined_results.json")

    print(f"\n[Succeeded] All {len(all_results)} files processed successfully.")


if __name__ == "__main__":
    start_time = time.time()
    main()
    end_time = time.time()
    print(f"\n[Succeeded] All files processed successfully in {end_time - start_time:.2f} seconds.")