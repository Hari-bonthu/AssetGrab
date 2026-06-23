# Document Image Extractor

A robust, highly optimized Python CLI tool and library for extracting images from PDF documents and various Office/ZIP formats (Word `.docx`, PowerPoint `.pptx`, Excel `.xlsx`, OpenDocument `.odt`, `.ods`, `.odp`, and standard `.zip` files).

---

## Features

- **Multiple PDF Engines**:
  - **`pymupdf`**: Extremely fast, page-aware, supports all standard image formats (JPEG, PNG, JPX, TIFF).
  - **`pypdf`**: Pure-Python library approach (no native compilation dependencies).
  - **`native`**: Custom pure-Python XObject parser that decodes compressed streams (`zlib/FlateDecode`, `DCTDecode/JPEG`). Excellent for zero-dependency parsing.
  - **`binary`**: Memory-mapped fallback scanner searching for raw JPEG markers (`\xff\xd8\xff` to `\xff\xd9`). Works on corrupted files.
- **Office Document Support**: Extracts pictures directly from ZIP-based templates (`word/media/`, `ppt/media/`, `Pictures/`, etc.) with zero dependencies.
- **Smart Image Processing**:
  - **Deduplication**: Cryptographic hash filtering prevents saving duplicate images (like header/footer logos).
  - **Validation**: Verifies image integrity and filters out broken/corrupt segments.
  - **Size / Dimension Gating**: Filters out layout thumbnails and tiny icons.
  - **Format Conversion**: Allows exporting all output images directly to a chosen format (e.g., PNG or JPG).

---

## Installation

Ensure you have Python 3.10+ installed.

### 1. Clone or Copy the Files
Place `extractor.py` and `requirements.txt` into your project directory.

### 2. Install Dependencies
You can run the script in standard mode (no external PDF packages required, uses `native` or `binary` engines). For the best experience and performance, install the recommended packages:

```bash
pip install -r requirements.txt
```

---

## CLI Usage

### Basic Extraction
To extract all images from a PDF file and save them to a directory:

```bash
python extractor.py path/to/document.pdf -o path/to/output_dir
```

### Advanced CLI Arguments
```text
positional arguments:
  input                 Path to input document file or directory containing files

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output directory where images will be saved
  -m MIN_SIZE, --min-size MIN_SIZE
                        Minimum image file size in bytes (default: 5000)
  -e {auto,pymupdf,pypdf,native,binary}, --engine {auto,pymupdf,pypdf,native,binary}
                        PDF extraction engine (default: auto)
  -f {jpg,png,bmp,tiff}, --format {jpg,png,bmp,tiff}
                        Convert output images to a specific format (requires Pillow)
  -d, --no-dedup        Disable image deduplication based on cryptographic hash
  --overwrite           Overwrite existing output files
  -v, --verbose         Enable verbose log output
```

### Examples
1. **Extract from all documents in a directory**:
   ```bash
   python extractor.py C:\Users\ADMIN\Documents -o .\extracted_images
   ```
2. **Convert all extracted images to PNG and filter out small icons (<10KB)**:
   ```bash
   python extractor.py document.docx -o .\images -m 10000 -f png
   ```
3. **Use raw binary marker scanning for a corrupted PDF file**:
   ```bash
   python extractor.py broken.pdf -o .\recovered -e binary
   ```

---

## Programmatic API Usage

You can also use this tool as a Python library:

```python
from pathlib import Path
from extractor import ImageExtractor

extractor = ImageExtractor(
    output_dir="./extracted",
    min_size=10000,         # 10KB minimum
    deduplicate=True,       # filter duplicate images
    pdf_engine="auto",      # auto-detect best engine
    output_format="png"     # convert to png
)

# Extract from a single file
count = extractor.extract_from_file(Path("document.pdf"))
print(f"Extracted {count} images!")
```
