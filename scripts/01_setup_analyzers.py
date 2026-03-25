"""
01_setup_analyzers.py
---------------------
Run this to register all analyzers on Azure.
If an analyzer already exists (409 Conflict), it will be deleted and recreated
so your latest JSON schema changes are always applied.

Usage:
    python scripts/01_setup_analyzers.py
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

# ------------------------------------------------------------------
# All analyzers to register: (analyzer_id, schema_file_path)
# analyzer_id must be camelCase with no hyphens or underscores
# ------------------------------------------------------------------
ANALYZERS = [
    ("myClassifier",                "analyzers/classifier_analyzer.json"),
    ("myLoanApplicationAnalyzer",   "analyzers/loan_application_analyzer.json"),
    ("myInvoiceAnalyzer",           "analyzers/invoice_analyzer.json"),
    ("myContractAnalyzer",          "analyzers/contract_analyzer.json"),
    ("myPurchaseOrderAnalyzer",     "analyzers/purchase_order_analyzer.json"),
    ("myKycAnalyzer",               "analyzers/kyc_analyzer.json"),
    ("myMedicalReportAnalyzer",     "analyzers/medical_report_analyzer.json"),
    ("myBankStatementAnalyzer",     "analyzers/bank_statement_analyzer.json"),
]


def make_client() -> ContentUnderstandingClient:
    return ContentUnderstandingClient(
        endpoint=os.environ["AZURE_AI_ENDPOINT"],
        credential=AzureKeyCredential(os.environ["AZURE_AI_API_KEY"]),
    )


def main():
    client = make_client()

    print("=" * 50)
    print("Registering analyzers on Azure...")
    print("=" * 50)

    for analyzer_id, schema_path in ANALYZERS:
        print(f"\nCreating/Updating: {analyzer_id}")
        try:
            import json
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_dict = json.load(f)

            poller = client.begin_create_analyzer(
                analyzer_id,
                resource=schema_dict,
                allow_replace=True
            )
            poller.result()
            print(f"[OK]   {analyzer_id}")
            
        except Exception as e:
            print(f"[FAIL] {analyzer_id}: {e}")

    print("\n" + "=" * 50)
    print("Setup complete.")
    print("=" * 50)


if __name__ == "__main__":
    main()
