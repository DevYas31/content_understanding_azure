"""
02_classify_and_route.py
------------------------
THE MAIN FILE.

Uses enableSegment=true — Azure splits the PDF into segments automatically.
Each segment is classified independently and routed to its own field extractor.

Example: A loan bundle PDF with 3 pages gets split into:
  Segment 1 → loan_application → my_loan_application_analyzer
  Segment 2 → kyc_document     → my_kyc_analyzer
  Segment 3 → invoice          → my_invoice_analyzer

Usage:
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


def classify_document(client, file_path: str) -> tuple:
    """
    Classify the document using the classifier analyzer (enableSegment=true).
    Azure splits the PDF into segments and classifies each one independently.
    Returns: (list of segments, raw_classification_result_dict)
    """
    print(f"\nClassifying (with segment splitting): {file_path}")

    with open(file_path, "rb") as f:
        poller = client.begin_analyze_binary(CLASSIFIER_ANALYZER_ID, binary_input=f.read())
        result = poller.result()

    # The SDK result is a dict-like AnalysisResult object
    # Segments are natively inside the first content item
    contents = result.get("contents", [])
    segments = contents[0].get("segments", []) if contents else []

    print(f"[OK] Found {len(segments)} segment(s):")
    for i, seg in enumerate(segments):
        category = seg.get("category", "unknown")
        start_pg = seg.get("startPageNumber", "?")
        end_pg   = seg.get("endPageNumber", "?")
        print(f"   Segment {i+1}: [{category}] (pages {start_pg}–{end_pg})")

    # Deep convert the SDK model to a standard dict for JSON serialization
    try:
        result_dict = dict(result)
        # Handle nested objects recursively if they aren't native dicts
        import json
        result_dict = json.loads(json.dumps(result_dict, default=lambda x: getattr(x, '__dict__', str(x))))
    except Exception:
        result_dict = str(result)

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
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved → {output_path}")


def process_file(client, file_path: str) -> dict:
    """Full pipeline: classify all segments → route each → extract → save."""
    print("\n" + "=" * 55)
    print(f"Processing: {file_path}")
    print("=" * 55)

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
    parser = argparse.ArgumentParser(description="Classify and extract fields from PDF documents.")
    parser.add_argument("--file", nargs="+", required=True, help="Path(s) to PDF file(s)")
    args = parser.parse_args()

    client = make_client()
    all_results = []

    for file_path in args.file:
        result = process_file(client, file_path)
        all_results.append(result)

    if len(args.file) > 1:
        save_output(all_results, "combined_results.json")
        print(f"\nCombined results → output/combined_results.json")

    print("\n[OK] All files processed.")


if __name__ == "__main__":
    main()