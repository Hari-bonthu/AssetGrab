# AssetGrab | Document Image Extractor Web Tool

AssetGrab is a premium, local web application and library for extracting high-fidelity images from PDF documents and Office files (Word `.docx`, PowerPoint `.pptx`, Excel `.xlsx`, OpenDocument `.odt`, `.ods`, `.odp`, and standard `.zip` files). 

It features a modern frosted-glass dark UI, multi-engine PDF parsing, smart size/dimension filtering, and cryptographic deduplication.

---

## Features

- **Modern Frosted-Glass UI**: Drag-and-drop file upload, dynamic settings dashboard, live gallery grid, and full-screen preview modal.
- **Run-Specific Output Folder**: Every extraction task creates a new, isolated directory under `results/` containing the extracted images, labeled by the document name and timestamp (e.g., `results/SHIVA_PORTFOLIO_20260623_153418/`).
- **Explorer Integration**: Click a button directly in the web UI to open the specific extraction folder on your local Windows system.
- **Multiple PDF Engines**:
  - **PyMuPDF**: Ultra-fast and high fidelity. Handles complex layouts.
  - **PyPDF**: Pure Python parser.
  - **Native Decoder**: Custom pure-Python XObject parser that decodes compressed streams (`zlib/FlateDecode`, `DCTDecode/JPEG`). Excellent for zero-dependency parsing.
  - **Binary Scanner**: Memory-mapped fallback scanner searching for raw JPEG markers (`\xff\xd8\xff` to `\xff\xd9`). Works on corrupted files.
- **Smart Image Processing**:
  - **Deduplication**: Cryptographic hash filtering prevents saving duplicate images (like header/footer logos).
  - **Validation**: Verifies image integrity using Pillow (PIL) and filters out broken/corrupt segments.
  - **Size / Dimension Gating**: Filters out layout thumbnails and tiny icons.
  - **Format Conversion**: Allows exporting all output images directly to a chosen format (e.g., PNG or JPEG).

---

## Installation

Ensure you have Python 3.10+ installed.

### 1. Install Dependencies
Install the required libraries (including FastAPI, Uvicorn, Pillow, PyMuPDF, and PyPDF):

```bash
pip install -r requirements.txt fastapi uvicorn
```

---

## How to Run

1. Open your terminal in the `doc-image-extractor` project folder.
2. Run the FastAPI server:
   ```bash
   python app.py
   ```
3. Your default web browser will automatically open to `http://127.0.0.1:8000`.
4. Drag and drop any document into the upload zone to start extracting!

---

## Project Structure

- **`app.py`**: The FastAPI backend server. Handles uploads, calls the extractor, lists results, and mounts the explorer opening endpoint.
- **`extractor.py`**: Core extraction engine containing ZIP and PDF parsers.
- **`static/`**: Frontend files.
  - `index.html`: Responsive HTML5 markup using Lucide Icons.
  - `style.css`: Premium dark theme styling with animations.
  - `script.js`: Fetch operations, drop handlers, and modal logic.
- **`results/`**: Global folder containing all extracted image runs.
