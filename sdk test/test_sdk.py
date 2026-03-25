import os
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

client = ContentUnderstandingClient(
    endpoint=os.environ["AZURE_AI_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["AZURE_AI_API_KEY"])
)

print("Client created.")
try:
    with open("data/1738127724775.pdf", "rb") as f:
        body_bytes = f.read()
        poller = client.begin_analyze_binary("prebuilt-documentSearch", binary_input=body_bytes)
        result = poller.result()
        print(f"Analyze success! Result type: {type(result)}")
        print(f"Keys: {dir(result)}")
except Exception as e:
    print(f"Error analyzing: {e}")
