import os
import json
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

client = ContentUnderstandingClient(
    endpoint=os.environ["AZURE_AI_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["AZURE_AI_API_KEY"])
)

with open("data/1738127724775.pdf", "rb") as f:
    poller = client.begin_analyze_binary("prebuilt-documentSearch", binary_input=f.read())
    result = poller.result()
    
    # Check if result has a direct .contents attribute or dict access
    info = {
        "type": str(type(result)),
        "keys": list(result.keys()) if hasattr(result, "keys") else dir(result),
        "contents_length": len(result.get("contents", [])),
    }
    
    with open("sdk_test_res.json", "w") as out:
        json.dump(info, out, indent=2)
