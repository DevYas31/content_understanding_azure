"""
04_manage_analyzers.py
-----------------------
Utility: list and delete analyzers on Azure.
Calls the REST API directly since the client does not expose list_analyzers().

Usage:
    python scripts/04_manage_analyzers.py --list
    python scripts/04_manage_analyzers.py --delete myInvoiceAnalyzer
    python scripts/04_manage_analyzers.py --delete-all
"""

import os
import sys
import argparse
import requests
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential
load_dotenv()


def get_client() -> ContentUnderstandingClient:
    return ContentUnderstandingClient(
        endpoint=os.environ["AZURE_AI_ENDPOINT"],
        credential=AzureKeyCredential(os.environ["AZURE_AI_API_KEY"])
    )


def list_analyzers() -> list:
    """Call the REST API directly to list all analyzers."""
    endpoint   = os.environ["AZURE_AI_ENDPOINT"].rstrip("/")
    api_version = os.environ["AZURE_AI_API_VERSION"]
    api_key    = os.environ["AZURE_AI_API_KEY"]

    url = f"{endpoint}/contentunderstanding/analyzers?api-version={api_version}"
    headers = {"Ocp-Apim-Subscription-Key": api_key}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("value", [])


def main():
    parser = argparse.ArgumentParser(description="Manage Azure Content Understanding analyzers.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list",       action="store_true",   help="List all registered analyzers")
    group.add_argument("--delete",     metavar="ANALYZER_ID", help="Delete a specific analyzer by ID")
    group.add_argument("--delete-all", action="store_true",   help="Delete all custom analyzers")
    args = parser.parse_args()

    if args.list:
        try:
            analyzers = list_analyzers()

            custom   = [a for a in analyzers if not a.get("analyzerId", "").startswith("prebuilt")]
            prebuilt = [a for a in analyzers if a.get("analyzerId", "").startswith("prebuilt")]

            print(f"\nCustom Analyzers ({len(custom)}):")
            print("=" * 40)
            if not custom:
                print("  (none found)")
            for a in custom:
                print(f"  {a.get('analyzerId', 'unknown')}  [{a.get('status', 'unknown')}]")

            print(f"\nPrebuilt Analyzers ({len(prebuilt)}):")
            print("=" * 40)
            if not prebuilt:
                print("  (none found)")
            for a in prebuilt:
                print(f"  {a.get('analyzerId', 'unknown')}  [{a.get('status', 'unknown')}]")

            print(f"\nTotal: {len(analyzers)}  (Custom: {len(custom)}, Prebuilt: {len(prebuilt)})")

        except Exception as e:
            print(f"[FAIL] Could not list analyzers: {e}")

    elif args.delete:
        client = get_client()
        print(f"\nDeleting: {args.delete}")
        try:
            client.delete_analyzer(args.delete)
            print(f"[OK]   Deleted: {args.delete}")
        except Exception as e:
            print(f"[FAIL] {e}")

    elif args.delete_all:
        client = get_client()
        try:
            analyzers = list_analyzers()
            custom = [a for a in analyzers if not a.get("analyzerId", "").startswith("prebuilt")]
            print(f"\nDeleting {len(custom)} custom analyzer(s)...")
            for a in custom:
                aid = a.get("analyzerId")
                print(f"  Deleting {aid}...")
                try:
                    client.delete_analyzer(aid)
                    print(f"  [OK]   Deleted {aid}")
                except Exception as e:
                    print(f"  [FAIL] {aid}: {e}")
            print("\nDone.")
        except Exception as e:
            print(f"[FAIL] Could not fetch analyzers: {e}")


if __name__ == "__main__":
    main()