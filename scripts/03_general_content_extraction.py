"""
03_general_content_extraction.py
---------------------------------
Uses Azure's PREBUILT analyzer for general content extraction (OCR, text, tables).

Usage:
    python scripts/03_general_content_extraction.py --file data/sample.pdf
"""

import os
import sys
import json
import argparse
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from client.content_understanding_client import AzureContentUnderstandingClient

load_dotenv()

PREBUILT_ANALYZER_ID = "prebuilt-documentSearch"


def main():
    parser = argparse.ArgumentParser(description="General content extraction from PDF.")
    parser.add_argument("--file", required=True, help="Path to the PDF file")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"[FAIL] File not found: {args.file}")
        sys.exit(1)

    client = AzureContentUnderstandingClient(
        endpoint=os.environ["AZURE_AI_ENDPOINT"],
        api_version=os.environ["AZURE_AI_API_VERSION"],
        subscription_key=os.environ["AZURE_AI_API_KEY"],
    )

    print(f"\nExtracting content from: {args.file}")
    print(f"Using prebuilt analyzer:  {PREBUILT_ANALYZER_ID}")

    operation_url = client.begin_analyze_binary(PREBUILT_ANALYZER_ID, args.file)
    result = client.poll_result(operation_url)

    os.makedirs("output", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(args.file))[0]
    output_path = f"output/{base_name}_content.json"

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"[OK] Done! Content saved → {output_path}")

    try:
        contents = result.get("result", {}).get("contents", [])
        print(f"\nSummary: {len(contents)} content block(s) extracted.")
        for i, block in enumerate(contents[:3]):
            print(f"  Block {i+1}: {str(block)[:120]}...")
    except Exception:
        pass


if __name__ == "__main__":
    main()