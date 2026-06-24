import os
import re
import shutil
import tempfile
import webbrowser
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from PIL import Image

# Import extractor module from extractor.py
from extractor import ImageExtractor

app = FastAPI(title="AssetGrab Extractor Backend")

# Define base paths
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
RESULTS_DIR = BASE_DIR / "results"

# Ensure directories exist
STATIC_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Mount extracted files static server so the frontend can preview images
app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")


class OpenFolderRequest(BaseModel):
    folder_path: str


def clean_filename(filename: str) -> str:
    """Sanitize filename to use as a folder name."""
    name = Path(filename).stem
    # Replace non-alphanumeric characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized.strip('_')


@app.post("/api/extract")
async def extract_images(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
    min_size: int = Form(5000),
    format: Optional[str] = Form(None),
    deduplicate: bool = Form(True)
):
    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    allowed_exts = ('.pdf', '.docx', '.pptx', '.xlsx', '.odt', '.ods', '.odp', '.zip')
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Supported formats: PDF, DOCX, PPTX, XLSX, ODT, ZIP"
        )

    # 1. Save uploaded file to a temporary directory
    temp_dir = Path(tempfile.mkdtemp())
    temp_file_path = temp_dir / file.filename
    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    # 2. Setup run-specific output folder
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_slug = f"{clean_filename(file.filename)}_{timestamp}"
    run_output_dir = RESULTS_DIR / folder_slug
    run_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 3. Instantiate and run the image extractor
        extractor_format = format if format else None
        extractor = ImageExtractor(
            output_dir=str(run_output_dir),
            min_size=min_size,
            deduplicate=deduplicate,
            pdf_engine=engine,
            output_format=extractor_format,
            overwrite=True
        )

        extractor.extract_from_file(temp_file_path)

        # 4. Read the resulting images inside run_output_dir
        extracted_images = []
        for file_path in run_output_dir.glob("*"):
            if file_path.is_file():
                # Read dimensions if image is openable by Pillow
                dimensions = None
                try:
                    with Image.open(file_path) as img:
                        dimensions = f"{img.width}x{img.height}"
                except Exception:
                    pass # Keep dimensions None if not openable

                extracted_images.append({
                    "name": file_path.name,
                    "size": file_path.stat().st_size,
                    "dimensions": dimensions,
                    "url": f"/results/{folder_slug}/{file_path.name}"
                })

        # Sort images by name
        extracted_images.sort(key=lambda x: x["name"])

        return {
            "folder_name": folder_slug,
            "folder_path": str(run_output_dir.resolve()),
            "images": extracted_images
        }

    except Exception as e:
        # Cleanup folder if run crashed entirely
        if run_output_dir.exists():
            shutil.rmtree(run_output_dir)
        raise HTTPException(status_code=500, detail=f"Extraction error: {e}")

    finally:
        # Cleanup uploaded temp file
        if temp_file_path.exists():
            os.remove(temp_file_path)
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@app.post("/api/open-folder")
async def open_folder(request: OpenFolderRequest):
    path_to_open = Path(request.folder_path)
    if not path_to_open.exists() or not path_to_open.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    try:
        # Windows Explorer opening method
        if os.name == 'nt':
            subprocess.Popen(['explorer', str(path_to_open.resolve())])
        else:
            # Fallback for unix/mac just in case
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, str(path_to_open)])
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")


# Serve Frontend index.html statically
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


# Mount other static elements (style.css, script.js) at the root
app.mount("/", StaticFiles(directory=str(STATIC_DIR)), name="static")


def start_server():
    # Automatically open browser once server is running
    webbrowser.open("http://127.0.0.1:8000")
    # Start server
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    start_server()
