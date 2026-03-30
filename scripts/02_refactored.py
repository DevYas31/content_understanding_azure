import os
import json
import argparse
from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential

# Load env
load_dotenv()

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
ENDPOINT = os.getenv("AZURE_AI_ENDPOINT")
API_KEY = os.getenv("AZURE_AI_API_KEY")

CLASSIFIER_ID = "myClassifier"

CATEGORY_ANALYZER_MAP = {
    "loan_application": "myLoanApplicationAnalyzer",
    "invoice": "myInvoiceAnalyzer",
    "contract": "myContractAnalyzer",
    "purchase_order": "myPurchaseOrderAnalyzer",
    "kyc_document": "myKycAnalyzer",
    "medical_report": "myMedicalReportAnalyzer",
    "bank_statement": "myBankStatementAnalyzer",
}

# ------------------------------------------------------------------
# CLIENT
# ------------------------------------------------------------------
def create_client():
    return ContentUnderstandingClient(
        endpoint=ENDPOINT,
        credential=AzureKeyCredential(API_KEY)
    )

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
def get_field_value(field):
    for key in ["valueString", "valueNumber", "valueDate", "valueBoolean"]:
        if key in field:
            return str(field[key])
    return "(not found)"


def extract_fields(result):
    documents = result.get("documents", [])
    extracted = []

    for doc in documents:
        fields = doc.get("fields", {})
        cleaned = {k: get_field_value(v) for k, v in fields.items()}
        extracted.append(cleaned)

    return extracted

# ------------------------------------------------------------------
# CLASSIFICATION
# ------------------------------------------------------------------
def classify_document(client, file_path):
    with open(file_path, "rb") as f:
        poller = client.begin_analyze(
            analyzer_id=CLASSIFIER_ID,
            body=f,
            content_type="application/octet-stream",
            features=["enableSegment"]
        )
    return poller.result()

# ------------------------------------------------------------------
# PROCESSING
# ------------------------------------------------------------------
def process_file(client, file_path):
    print("\n" + "="*60)
    print(f"📄 Processing: {file_path}")
    print("="*60)

    result = classify_document(client, file_path)

    segments = result.get("segments", [])
    if not segments:
        print("❌ No segments detected")
        return

    for i, segment in enumerate(segments, 1):
        category = segment.get("category")

        if not category:
            print(f"⚠️ Segment {i}: No category")
            continue

        analyzer_id = CATEGORY_ANALYZER_MAP.get(category)

        if not analyzer_id:
            print(f"⚠️ Segment {i}: No analyzer mapped for '{category}'")
            continue

        print(f"\n➡️ Segment {i} → {category}")

        # ✅ TEMP FIX: Use full file again (safe approach)
        with open(file_path, "rb") as f:
            poller = client.begin_analyze(
                analyzer_id=analyzer_id,
                body=f
            )

        analysis = poller.result()

        fields = extract_fields(analysis)

        print("📊 Extracted Fields:")
        print(json.dumps(fields, indent=2, ensure_ascii=False))

# ------------------------------------------------------------------
# MAIN (Interactive + CLI)
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", nargs="+", help="PDF file(s)")

    args = parser.parse_args()
    client = create_client()

    # CLI mode
    if args.file:
        file_paths = args.file
    else:
        # Interactive mode
        user_input = input("Enter file path(s): ").strip()

        if not user_input:
            print("⚠️ No input provided")
            return

        file_paths = [f.strip() for f in user_input.split(",")]

    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            continue

        process_file(client, file_path)

# ------------------------------------------------------------------
if __name__ == "__main__":
    main()