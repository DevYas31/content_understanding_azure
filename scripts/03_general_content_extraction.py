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
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

PREBUILT_ANALYZER_ID = "prebuilt-documentSearch"


def main():
    parser = argparse.ArgumentParser(description="General content extraction from PDF.")
    parser.add_argument("--file", required=True, help="Path to the PDF file")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"[FAIL] File not found: {args.file}")
        sys.exit(1)

    client = ContentUnderstandingClient(
        endpoint=os.environ["AZURE_AI_ENDPOINT"],
        credential=AzureKeyCredential(os.environ["AZURE_AI_API_KEY"])
    )

    print(f"\nExtracting content from: {args.file}")
    print(f"Using prebuilt analyzer:  {PREBUILT_ANALYZER_ID}")

    with open(args.file, "rb") as f:
        poller = client.begin_analyze_binary(PREBUILT_ANALYZER_ID, binary_input=f.read())
        result = poller.result()
        
    try:
        import json
        result_dict = json.loads(json.dumps(dict(result), default=lambda x: getattr(x, '__dict__', str(x))))
    except Exception:
        result_dict = dict(result)

    os.makedirs("output", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(args.file))[0]
    output_path = f"output/{base_name}_content.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2)

    print(f"[OK] Done! Content saved → {output_path}")

    try:
        contents = result_dict.get("contents", [])
        print(f"\nSummary: {len(contents)} content block(s) extracted.")
        for i, block in enumerate(contents[:3]):
            print(f"  Block {i+1}: {str(block)[:120]}...")
    except Exception:
        pass


if __name__ == "__main__":
    main()