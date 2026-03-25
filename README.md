# Azure AI Content Understanding — Document Processing Pipeline

A robust, "Two-Pass" Proof of Concept for automatically classifying mixed PDF documents (e.g., invoices, medical reports, bank statements) and routing them to specialized field extractors using the Azure AI Content Understanding service.

---

## 🏗️ Architecture: The Two-Pass Strategy

1. **Pass 1 (Classification & Segmentation):** The document is analyzed by a custom "Router" analyzer. It figures out where one logical document ends and another begins (page segmentation) and assigns a doc-type category (e.g., `invoice`).
2. **Pass 2 (Targeted Extraction):** Based on the category, each segment is dynamically routed to a highly specialized custom analyzer (e.g., `myInvoiceAnalyzer`) to extract specific structured fields with high accuracy.

---

## 📂 Folder Structure

```
cu_poc_studio/ContentUnderstanding/
├── .env                                  ← Your Azure API keys
├── client/
│   └── content_understanding_client.py   ← Core REST API communication layer
├── analyzers/                            
│   ├── classifier_analyzer.json          ← The Router Schema (categories & segmentation config)
│   ├── loan_application_analyzer.json    ← Field definitions for loan applications
│   ├── invoice_analyzer.json             ← Field definitions for invoices
│   └── ...                               ← Other specialized field schemas
├── scripts/
│   ├── 01_setup_analyzers.py             ← Deploys local schemas to Azure Cloud
│   ├── 02_classify_and_route.py          ← Core Engine: Executes the two-pass routing logic
│   ├── 03_extract_and_display.py         ← CLI Tool: Runs pipeline & outputs clean ASCII tables
│   ├── 03_general_content_extraction.py  ← Utility: Raw OCR extraction (no custom schema)
│   └── 04_manage_analyzers.py            ← Admin Tool: List/Delete Azure analyzers
├── data/                                 ← Input folder for your PDFs/images
└── output/                               ← Output folder for raw JSONs and readable text files
```

---

## ⚙️ Setup and Prerequisites

### 1. Install dependencies
```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Create a `.env` file in the root directory and add your Azure credentials. Ensure you are using the GA API version:
```ini
AZURE_AI_ENDPOINT=https://your-resource-name.services.ai.azure.com/
AZURE_AI_API_VERSION=2025-11-01
AZURE_AI_API_KEY=your-super-secret-api-key
```

### 3. Deploy Schemas to Azure
Before you can analyze documents, Azure must be aware of your field schemas and classifications. Run this once (or whenever you alter the JSON schemas in `analyzers/`):
```bash
python scripts/01_setup_analyzers.py
```

---

## 🚀 How to Run the Pipeline

The primary tool you will use is `03_extract_and_display.py`. This script handles calling the core pipeline and formatting the results.

### Option A: Interactive Mode
Simply run the script. It will prompt you to enter the path to your PDF.
```bash
python scripts/03_extract_and_display.py
```

### Option B: Command-Line Arguments
Provide the file directly as an argument. You can pass multiple files at once.
```bash
python scripts/03_extract_and_display.py --file data/1738127724775.pdf
```

### Option C: View Previous Results (Offline)
If you already processed a document and just want to re-generate the readable text table without hitting the Azure API again:
```bash
python scripts/03_extract_and_display.py --json output/mixed_financial_docs_all_segments_result.json
```

**Outputs:**
For every document processed, the pipeline will generate nested JSONs with raw bounding boxes AND highly readable text files representing the extracted tabular data (e.g., `output/filename_segment1_medical_report_fields.txt`).

---

## 🛠️ Modifying the Pipeline (Adding New Categories)

If you want to support a new document type (e.g., `tax_form`):

1. **Create the Extractor Schema**: Create `analyzers/tax_analyzer.json` describing the fields you want extracted.
2. **Update the Deployment Script**: Add `"tax_analyzer.json"` to the `ANALYZERS` array at the top of `scripts/01_setup_analyzers.py`.
3. **Update the Router Registry**: Open `analyzers/classifier_analyzer.json`. Add the new category under `contentCategories`:
   ```json
   "tax_form": { "description": "Annual end-of-year tax returns and W2s" }
   ```
4. **Update the Python Mapper**: Open `scripts/02_classify_and_route.py`. Add the mapping to `CATEGORY_ANALYZER_MAP`:
   ```python
   "tax_form": "myTaxAnalyzer"
   ```
5. **Re-deploy!**: Run `python scripts/01_setup_analyzers.py` to push changes to Azure.
