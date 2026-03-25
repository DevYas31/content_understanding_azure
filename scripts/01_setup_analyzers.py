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
from client.content_understanding_client import AzureContentUnderstandingClient

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
]


def make_client():
    return AzureContentUnderstandingClient(
        endpoint=os.environ["AZURE_AI_ENDPOINT"],
        api_version=os.environ["AZURE_AI_API_VERSION"],
        subscription_key=os.environ["AZURE_AI_API_KEY"],
    )


def main():
    client = make_client()

    print("=" * 50)
    print("Registering analyzers on Azure...")
    print("=" * 50)

    for analyzer_id, schema_path in ANALYZERS:
        print(f"\nCreating: {analyzer_id}")
        try:
            client.begin_create_analyzer(
                analyzer_id,
                analyzer_template_path=schema_path
            )
            print(f"[OK]   {analyzer_id}")

        except Exception as e:
            error_str = str(e)

            # 409 Conflict means it already exists — delete and recreate
            if "409" in error_str or "ModelExists" in error_str or "Conflict" in error_str:
                print(f"[WARN] Already exists. Deleting and recreating: {analyzer_id}")
                try:
                    client.delete_analyzer(analyzer_id)
                    client.begin_create_analyzer(
                        analyzer_id,
                        analyzer_template_path=schema_path
                    )
                    print(f"[OK]   Recreated: {analyzer_id}")
                except Exception as e2:
                    print(f"[FAIL] Could not recreate {analyzer_id}: {e2}")
            else:
                print(f"[FAIL] {analyzer_id}: {e}")

    print("\n" + "=" * 50)
    print("Setup complete.")
    print("=" * 50)


if __name__ == "__main__":
    main()
