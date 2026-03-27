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
import argparse
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

# ------------------------------------------------------------------
# CATEGORY : ANALYZER MAP
# NOTE: analyzer_id must use underscores only, NO hyphens
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
# Field extraction and display helpers
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
    {"name", "value", "type", "confidence"} dicts sorted by confidence.
    """
    # Thoroughly unwrap the SDK model bindings first
    result = unwrap_data(result)

    # Unwrap "extracted_fields" wrapper if present
    if "extracted_fields" in result:
        result = result["extracted_fields"]

    contents = result.get("result", result).get("contents", [])
    fields_dict = contents[0].get("fields", {}) if contents else {}

    rows = extract_fields_from_dict(fields_dict)

    # Do not sort rows here, so we preserve the original schema ordering returned by Azure API
    return rows


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
    """
    Classify the document using the classifier analyzer (enableSegment=true).
    Azure splits the PDF into segments and classifies each one independently.
    We also check for 'multiple_categories_found' to route a single page to multiple analyzers.
    Returns: (list of segments, raw_classification_result_dict)
    """
    print(f"\nClassifying (with segment splitting): {file_path}")

    with open(file_path, "rb") as f:
        poller = client.begin_analyze_binary(CLASSIFIER_ANALYZER_ID, binary_input=f.read())
        result = poller.result()

    # Deep convert the SDK model to a standard dict for JSON serialization
    try:
        result_dict = dict(result)
        # Handle nested objects recursively if they aren't native dicts
        import json
        result_dict = json.loads(json.dumps(result_dict, default=lambda x: getattr(x, '__dict__', str(x))))
        result_dict = unwrap_data(result_dict)
    except Exception:
        result_dict = dict(result)
        result_dict = unwrap_data(result_dict)

    # Segments are natively inside the first content item
    contents = result_dict.get("contents", [])
    segments = contents[0].get("segments", []) if contents else []

    # Check for multiple categories found on the same page
    fields = contents[0].get("fields", {}) if contents else {}
    mult_array = fields.get("multiple_categories_found", {}).get("valueArray", [])
    
    extracted_cats = []
    for item in mult_array:
        if "valueString" in item:
            extracted_cats.append(item["valueString"])
            
    existing_cats = set(s.get("category") for s in segments)
    
    # Append any categories that the classifier found but didn't segment natively
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
        category = seg.get("category", "unknown")
        start_pg = seg.get("startPageNumber", "?")
        end_pg   = seg.get("endPageNumber", "?")
        v_flag   = " (virtual routing)" if seg.pop("_virtual", False) else ""
        print(f"   Segment {i+1}: [{category}] (pages {start_pg}–{end_pg}){v_flag}")

    return segments, result_dict


def extract_fields(client, file_path: str, analyzer_id: str) -> dict:
    """Run the field extraction analyzer on the file."""
    print(f"Extracting fields using: {analyzer_id}")
    with open(file_path, "rb") as f:
        poller = client.begin_analyze_binary(analyzer_id, binary_input=f.read())
        result = poller.result()
    print(f"[OK] Extraction complete.")
    
    try:
        import json
        result_dict = json.loads(json.dumps(dict(result), default=lambda x: getattr(x, '__dict__', str(x))))
    except Exception:
        result_dict = dict(result)
        
    return result_dict


def save_output(data: dict, filename: str):
    """Save result dict to output/ folder as JSON."""
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved JSON → {output_path}")


def process_file(client, file_path: str) -> dict:
    """Full pipeline: classify all segments → route each → extract → save & print."""
    print("\n" + "=" * 60)
    print(f"  Processing: {file_path}")
    print("=" * 60)

    if not os.path.exists(file_path):
        print(f"[FAIL] File not found: {file_path}")
        return {}

    base_name = os.path.splitext(os.path.basename(file_path))[0]

    # Step 1: Classify — returns ALL segments
    segments, classification_result = classify_document(client, file_path)
    save_output(classification_result, f"{base_name}_classification.json")

    if not segments:
        print("[ WARN ]  No segments returned from classifier.")
        return {}

    # Step 2: Loop over every segment and route independently
    all_segment_results = []

    for i, segment in enumerate(segments):
        segment_num = i + 1
        category    = segment.get("category", "unknown")
        start_pg    = segment.get("startPageNumber", "?")
        end_pg      = segment.get("endPageNumber", "?")

        print(f"\n--- Segment {segment_num}/{len(segments)}: [{category}] (pages {start_pg}–{end_pg}) ---")

        analyzer_id = CATEGORY_ANALYZER_MAP.get(category)
        
        extracted_fields_list = []

        if not analyzer_id:
            print(f"[ WARN ]  No analyzer mapped for category: '{category}' — skipping.")
            segment_result = {
                "segment":          segment_num,
                "category":         category,
                "pages":            f"{start_pg}–{end_pg}",
                "analyzer_used":    None,
                "extracted_fields": None,
                "note": f"No analyzer registered for category '{category}'"
            }
        else:
            extraction_result = extract_fields(client, file_path, analyzer_id)
            segment_result = {
                "segment":          segment_num,
                "category":         category,
                "pages":            f"{start_pg}–{end_pg}",
                "analyzer_used":    analyzer_id,
                "extracted_fields": extraction_result
            }
            save_output(segment_result, f"{base_name}_segment{segment_num}_{category}_result.json")
            
            extracted_fields_list = extract_fields_from_result(extraction_result)

        # Print beautifully to console
        print(f"\n{'=' * 60}")
        print(f"  EXTRACTED FIELDS  --  Segment {segment_num}")
        print(f"{'=' * 60}")
        print_and_save_segment_fields(base_name, segment_num, category, f"{start_pg}–{end_pg}", extracted_fields_list)

        all_segment_results.append(segment_result)

    # Step 3: Save combined result
    final_result = {
        "file":           file_path,
        "total_segments": len(segments),
        "segments":       all_segment_results
    }
    save_output(final_result, f"{base_name}_all_segments_result.json")
    print(f"\nDone! {len(segments)} segment(s) processed for: {file_path}")
    return final_result


def main():
    parser = argparse.ArgumentParser(
        description="Classify and extract fields from PDF documents, then display results.",
        epilog=(
            "Examples:\n"
            "  python scripts/02_classify_and_route.py\n"
            "  python scripts/02_classify_and_route.py --file data/report.pdf\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", nargs="+", required=False, help="Path(s) to PDF file(s)")
    args = parser.parse_args()

    client = make_client()
    all_results = []
    
    file_paths = getattr(args, "file", None)

    if file_paths:
        for file_path in file_paths:
            result = process_file(client, file_path)
            all_results.append(result)
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
            
        result = process_file(client, file_path)
        all_results.append(result)

    if len(all_results) > 1:
        save_output(all_results, "combined_results.json")
        print(f"\nCombined results JSON → output/combined_results.json")

    print("\n[OK] All files processed.")


if __name__ == "__main__":
    main()