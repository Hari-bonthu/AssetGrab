#!/usr/bin/env python3
"""
Document Image Extractor
A highly optimized command-line tool and Python library for extracting images
from PDFs and Office documents (DOCX, PPTX, XLSX, ODT, etc.).
"""

import os
import sys
import re
import zlib
import mmap
import hashlib
import argparse
import zipfile
from typing import List, Dict, Set, Tuple, Optional, BinaryIO
from pathlib import Path

# Try importing Pillow for validation and image reconstruction
try:
    from PIL import Image, ImageOps
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# Try importing third-party PDF engines
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


class ConsoleColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_status(msg: str, status_type: str = "info"):
    """Print formatted log messages to stderr."""
    if os.name == 'nt':  # Windows command prompt might not support ANSI colors by default
        # Just print clean text or enable colors via colorama if available
        # Since we want zero-dependency standard formatting, we will print clean prefixes
        prefix = f"[{status_type.upper()}] "
        print(f"{prefix}{msg}", file=sys.stderr)
        return

    if status_type == "info":
        print(f"{ConsoleColors.OKBLUE}[*]{ConsoleColors.ENDC} {msg}", file=sys.stderr)
    elif status_type == "success":
        print(f"{ConsoleColors.OKGREEN}[+]{ConsoleColors.ENDC} {msg}", file=sys.stderr)
    elif status_type == "warning":
        print(f"{ConsoleColors.WARNING}[!]{ConsoleColors.ENDC} {msg}", file=sys.stderr)
    elif status_type == "error":
        print(f"{ConsoleColors.FAIL}[-]{ConsoleColors.ENDC} {msg}", file=sys.stderr)
    elif status_type == "header":
        print(f"{ConsoleColors.BOLD}{ConsoleColors.HEADER}{msg}{ConsoleColors.ENDC}", file=sys.stderr)


class ImageProcessor:
    """Handles image validation, deduplication, and size filtering."""

    def __init__(self, min_size: int = 5000, deduplicate: bool = True, output_format: Optional[str] = None):
        self.min_size = min_size
        self.deduplicate = deduplicate
        self.output_format = output_format.lower() if output_format else None
        self.seen_hashes: Set[str] = set()

    def process_image(self, image_data: bytes, ext: str) -> Tuple[bool, Optional[bytes], str]:
        """
        Validate, check size, deduplicate, and optionally convert image data.
        Returns: (is_valid, processed_data, final_extension)
        """
        # 1. Check basic size of raw data first
        if len(image_data) < self.min_size:
            return False, None, ext

        # 2. Check deduplication
        if self.deduplicate:
            img_hash = hashlib.sha256(image_data).hexdigest()
            if img_hash in self.seen_hashes:
                return False, None, ext
            self.seen_hashes.add(img_hash)

        # 3. Validate and convert image if Pillow is available
        if HAS_PILLOW:
            try:
                import io
                image = Image.open(io.BytesIO(image_data))
                image.verify()  # Fast check for corruption
                
                # Re-open for actual processing (verify closes/invalidates the file pointer)
                image = Image.open(io.BytesIO(image_data))
                
                # Check dimensions (filter out 1x1 or tiny spacer pixels)
                if image.width < 10 or image.height < 10:
                    return False, None, ext

                # Format conversion if output_format is specified
                if self.output_format and self.output_format != ext.lower():
                    # Check compatibility
                    out_io = io.BytesIO()
                    # Handle RGBA/LA transparency conversion for JPEGs
                    if self.output_format in ['jpg', 'jpeg'] and image.mode in ('RGBA', 'LA'):
                        # Paste onto white background
                        background = Image.new("RGB", image.size, (255, 255, 255))
                        background.paste(image, mask=image.split()[-1])
                        image = background
                    
                    image.save(out_io, format=self.output_format.upper())
                    return True, out_io.getvalue(), self.output_format

            except Exception as e:
                # Pillow failed to open or verify image (might be corrupt or unsupported format)
                return False, None, ext

        return True, image_data, ext


class ZipExtractor:
    """Extracts images from ZIP-based document formats (DOCX, PPTX, XLSX, ODT, etc.)."""

    # Folders inside ZIPs where media is typically stored
    MEDIA_FOLDERS = [
        re.compile(r'^word/media/.*'),       # Word
        re.compile(r'^ppt/media/.*'),        # PowerPoint
        re.compile(r'^xl/media/.*'),         # Excel
        re.compile(r'^Pictures/.*'),         # OpenDocument (ODT, ODP, ODS)
    ]

    @staticmethod
    def is_supported(file_path: Path) -> bool:
        return zipfile.is_zipfile(file_path)

    def extract(self, file_path: Path, output_dir: Path, processor: ImageProcessor) -> int:
        count = 0
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # Find all files matching media patterns
                media_files = []
                for name in z.namelist():
                    for pattern in self.MEDIA_FOLDERS:
                        if pattern.match(name):
                            media_files.append(name)
                            break

                if not media_files:
                    return 0

                for member in media_files:
                    try:
                        # Extract suffix/extension
                        p = Path(member)
                        ext = p.suffix.lstrip('.').lower()
                        if not ext:
                            ext = 'png' # default fallback

                        image_data = z.read(member)
                        is_valid, processed_data, final_ext = processor.process_image(image_data, ext)
                        if is_valid and processed_data:
                            count += 1
                            safe_name = f"{file_path.stem}_extracted_{count}.{final_ext}"
                            out_path = output_dir / safe_name
                            out_path.write_bytes(processed_data)
                    except Exception as e:
                        print_status(f"Error extracting ZIP member {member}: {e}", "warning")
        except Exception as e:
            print_status(f"Error reading ZIP document {file_path}: {e}", "error")
        return count


class PdfExtractorPyMuPDF:
    """PDF Image Extraction using PyMuPDF (fitz) - the fastest and most robust engine."""

    def extract(self, file_path: Path, output_dir: Path, processor: ImageProcessor) -> int:
        if not HAS_PYMUPDF:
            raise RuntimeError("PyMuPDF is not installed.")

        count = 0
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            
            for page_idx in range(total_pages):
                page = doc[page_idx]
                image_list = page.get_images(full=True)
                
                for img_idx, img in enumerate(image_list):
                    xref = img[0]
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]

                        is_valid, processed_data, final_ext = processor.process_image(image_bytes, image_ext)
                        if is_valid and processed_data:
                            count += 1
                            out_name = f"{file_path.stem}_page{page_idx+1}_img{img_idx+1}.{final_ext}"
                            out_path = output_dir / out_name
                            out_path.write_bytes(processed_data)
                    except Exception as e:
                        print_status(f"Error extracting image xref {xref} on page {page_idx+1}: {e}", "warning")
        except Exception as e:
            print_status(f"PyMuPDF failed to process {file_path}: {e}", "error")
        return count


class PdfExtractorPyPDF:
    """PDF Image Extraction using PyPDF - pure-Python alternative."""

    def extract(self, file_path: Path, output_dir: Path, processor: ImageProcessor) -> int:
        if not HAS_PYPDF:
            raise RuntimeError("pypdf is not installed.")

        count = 0
        try:
            reader = pypdf.PdfReader(file_path)
            for page_idx, page in enumerate(reader.pages):
                # Retrieve images on page
                try:
                    images = page.images
                except Exception:
                    continue

                for img_idx, img_file in enumerate(images):
                    try:
                        image_bytes = img_file.data
                        name = img_file.name
                        
                        # Guess extension
                        ext = Path(name).suffix.lstrip('.').lower()
                        if not ext:
                            ext = 'png' # standard default

                        is_valid, processed_data, final_ext = processor.process_image(image_bytes, ext)
                        if is_valid and processed_data:
                            count += 1
                            out_name = f"{file_path.stem}_page{page_idx+1}_img{img_idx+1}.{final_ext}"
                            out_path = output_dir / out_name
                            out_path.write_bytes(processed_data)
                    except Exception as e:
                        print_status(f"Error extracting image {img_idx+1} on page {page_idx+1}: {e}", "warning")
        except Exception as e:
            print_status(f"PyPDF failed to process {file_path}: {e}", "error")
        return count


class PdfExtractorNative:
    """
    Pure Python PDF XObject stream parser.
    Doesn't require external PDF libraries. Parses structures looking for XObject Image streams,
    resolving /Filter (FlateDecode, DCTDecode, JPXDecode).
    """

    def _find_xref_table(self, data: bytes) -> Dict[int, int]:
        """Attempts to parse the XRef table to find byte offsets of objects."""
        # Find startxref
        xref_offsets = {}
        startxref_matches = list(re.finditer(br"startxref\s+(\d+)", data))
        if not startxref_matches:
            return xref_offsets

        # Start from the last startxref
        last_xref_pos = int(startxref_matches[-1].group(1))
        
        # Simple scan of xref section
        # Note: A fully compliant parser follows chains, but this simple one handles standard layouts
        pos = last_xref_pos
        xref_match = re.match(br"\s*xref\s*", data[pos:pos+20])
        if xref_match:
            pos += len(xref_match.group(0))
            # Scan lines
            line_re = re.compile(br"(\d+)\s+(\d+)\s+([fn])")
            # Get subsection header
            header_re = re.compile(br"(\d+)\s+(\d+)\s*")
            while pos < len(data):
                hm = header_re.match(data, pos)
                if not hm:
                    break
                pos += len(hm.group(0))
                start_obj = int(hm.group(1))
                count = int(hm.group(2))
                for idx in range(count):
                    # check next line: 20 bytes (offset gen f/n)
                    line_data = data[pos:pos+20]
                    lm = line_re.match(line_data)
                    if lm:
                        offset = int(lm.group(1))
                        gen = int(lm.group(2))
                        status = lm.group(3)
                        if status == b'n':
                            xref_offsets[start_obj + idx] = offset
                        pos += 20
                    else:
                        break
        return xref_offsets

    def extract(self, file_path: Path, output_dir: Path, processor: ImageProcessor) -> int:
        count = 0
        try:
            with open(file_path, "rb") as f:
                # We memory-map or read the whole file. Since we parse, we read it.
                data = f.read()

            # Find all objects using pattern matching
            # Objects are: X Y obj << dict >> stream ... endstream endobj
            # We search for dictionaries first
            dict_re = re.compile(br"(\d+)\s+(\d+)\s+obj\s*<<\s*(.*?)\s*>>\s*stream", re.DOTALL)
            
            # To handle indirect lengths or missing endstream, we do a scan
            for match in dict_re.finditer(data):
                obj_id = int(match.group(1))
                gen_id = int(match.group(2))
                dict_content = match.group(3)
                stream_start = match.end()

                # Check if it is an Image XObject
                if b"/Subtype" not in dict_content or b"/Image" not in dict_content:
                    continue

                # Parse basic dictionary values
                filters = []
                filter_match = re.search(br"/Filter\s*(/?[a-zA-Z0-9_]+|\[.*?\])", dict_content)
                if filter_match:
                    filter_val = filter_match.group(1)
                    if filter_val.startswith(b"["):
                        # Array of filters
                        filters = [f.strip(b"/ ") for f in re.findall(b"/[a-zA-Z0-9_]+", filter_val)]
                    else:
                        filters = [filter_val.strip(b"/ ")]

                # Extract Length
                length = None
                length_match = re.search(br"/Length\s+(\d+)", dict_content)
                if length_match:
                    length = int(length_match.group(1))
                else:
                    # Length might be an indirect reference: /Length 15 0 R
                    ind_length_match = re.search(br"/Length\s+(\d+)\s+(\d+)\s+R", dict_content)
                    if ind_length_match:
                        # Indirect lookup - we can scan for that object
                        target_id = int(ind_length_match.group(1))
                        len_obj_re = re.compile(rb"%d\s+\d+\s+obj\s*(\d+)\s*endobj" % target_id)
                        lom = len_obj_re.search(data)
                        if lom:
                            length = int(lom.group(1))

                # Determine stream bounds
                stream_data = b""
                if length is not None:
                    stream_data = data[stream_start : stream_start + length]
                else:
                    # Fallback: scan for endstream
                    endstream_pos = data.find(b"endstream", stream_start)
                    if endstream_pos != -1:
                        stream_data = data[stream_start:endstream_pos]
                        # Trim optional leading/trailing CRLFs
                        if stream_data.startswith(b"\r\n"):
                            stream_data = stream_data[2:]
                        elif stream_data.startswith(b"\n"):
                            stream_data = stream_data[1:]
                        if stream_data.endswith(b"\r\n"):
                            stream_data = stream_data[:-2]
                        elif stream_data.endswith(b"\n"):
                            stream_data = stream_data[:-1]

                if not stream_data:
                    continue

                # Decompress stream based on filters
                decompressed = stream_data
                is_decompressed = True
                ext = 'bin'

                for f in filters:
                    if f in (b"FlateDecode", b"Flate", b"Fl"):
                        try:
                            # zlib decompress (ignore leading bytes if PDF stream contains headers)
                            decompressed = zlib.decompress(decompressed)
                        except Exception:
                            # Try with negative wbits to ignore headers
                            try:
                                decompressed = zlib.decompress(decompressed, -15)
                            except Exception:
                                is_decompressed = False
                                break
                    elif f in (b"DCTDecode", b"DCT"):
                        ext = 'jpg'
                    elif f in (b"JPXDecode", b"JPX"):
                        ext = 'jp2'

                if not is_decompressed:
                    continue

                # If FlateDecoded and raw, it might be a PNG/bitmap.
                # Reconstructing raw bitmaps is tricky without width/height/colorspace.
                # However, if it's DCTDecode, it's a direct JPEG.
                if ext == 'jpg':
                    # Validate and save
                    is_valid, processed_data, final_ext = processor.process_image(decompressed, ext)
                    if is_valid and processed_data:
                        count += 1
                        out_path = output_dir / f"{file_path.stem}_native_obj{obj_id}.{final_ext}"
                        out_path.write_bytes(processed_data)
                elif ext == 'jp2':
                    is_valid, processed_data, final_ext = processor.process_image(decompressed, ext)
                    if is_valid and processed_data:
                        count += 1
                        out_path = output_dir / f"{file_path.stem}_native_obj{obj_id}.{final_ext}"
                        out_path.write_bytes(processed_data)
                elif ext == 'bin' and HAS_PILLOW:
                    # Let's try to see if Pillow can load it (if it contains headers)
                    # Often flate-encoded streams are raw raster pixels, but sometimes they embed full PNGs
                    try:
                        import io
                        image = Image.open(io.BytesIO(decompressed))
                        is_valid, processed_data, final_ext = processor.process_image(decompressed, image.format.lower())
                        if is_valid and processed_data:
                            count += 1
                            out_path = output_dir / f"{file_path.stem}_native_obj{obj_id}.{final_ext}"
                            out_path.write_bytes(processed_data)
                    except Exception:
                        # Try decoding raw pixel format if we can extract width/height/colorspace
                        width_m = re.search(br"/Width\s+(\d+)", dict_content)
                        height_m = re.search(br"/Height\s+(\d+)", dict_content)
                        bpc_m = re.search(br"/BitsPerComponent\s+(\d+)", dict_content)
                        cs_m = re.search(br"/ColorSpace\s*(/DeviceRGB|/DeviceGray|/DeviceCMYK)", dict_content)
                        
                        if width_m and height_m:
                            width = int(width_m.group(1))
                            height = int(height_m.group(1))
                            bpc = int(bpc_m.group(1)) if bpc_m else 8
                            cs = cs_m.group(1) if cs_m else b"/DeviceRGB"
                            
                            mode = "RGB"
                            if cs == b"/DeviceGray":
                                mode = "L"
                            elif cs == b"/DeviceCMYK":
                                mode = "CMYK"
                            
                            try:
                                # Create raw image from bytes
                                image = Image.frombytes(mode, (width, height), decompressed)
                                out_io = io.BytesIO()
                                image.save(out_io, format="PNG")
                                is_valid, processed_data, final_ext = processor.process_image(out_io.getvalue(), "png")
                                if is_valid and processed_data:
                                    count += 1
                                    out_path = output_dir / f"{file_path.stem}_native_obj{obj_id}.{final_ext}"
                                    out_path.write_bytes(processed_data)
                            except Exception:
                                pass

        except Exception as e:
            print_status(f"Native parser failed on {file_path}: {e}", "error")
        return count


class PdfExtractorBinary:
    """
    Highly optimized memory-mapped binary scanner.
    Scans raw bytes for JPEG headers (\xff\xd8\xff) and footers (\xff\xd9).
    This acts as a robust fallback for corrupted or badly structured PDFs.
    """

    def extract(self, file_path: Path, output_dir: Path, processor: ImageProcessor) -> int:
        count = 0
        start_marker = b"\xff\xd8\xff"
        end_marker = b"\xff\xd9"
        
        try:
            with open(file_path, "rb") as f:
                # Use memory mapping to search files efficiently without high memory pressure
                # Handles files of several GBs seamlessly
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    return 0
                
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    pos = 0
                    while True:
                        start_idx = mm.find(start_marker, pos)
                        if start_idx == -1:
                            break
                        
                        # Find corresponding end marker
                        end_idx = mm.find(end_marker, start_idx)
                        if end_idx == -1:
                            # Move pos past start marker to avoid infinite loops
                            pos = start_idx + len(start_marker)
                            continue
                        
                        # Extract JPEG bytes
                        jpeg_len = end_idx - start_idx + len(end_marker)
                        jpeg_data = mm[start_idx : start_idx + jpeg_len]
                        
                        # Validate JPEG via processor (filters size, deduplicates, verifies structure)
                        is_valid, processed_data, final_ext = processor.process_image(jpeg_data, "jpg")
                        if is_valid and processed_data:
                            count += 1
                            out_path = output_dir / f"{file_path.stem}_binscan_{count}.{final_ext}"
                            out_path.write_bytes(processed_data)
                        
                        # Next scan position
                        pos = end_idx + len(end_marker)
        except Exception as e:
            print_status(f"Binary scanner failed on {file_path}: {e}", "error")
        return count


class ImageExtractor:
    """Main coordinator class for image extraction tasks."""

    def __init__(self, output_dir: str, min_size: int = 5000, deduplicate: bool = True,
                 pdf_engine: str = "auto", output_format: Optional[str] = None, overwrite: bool = False):
        self.output_dir = Path(output_dir)
        self.processor = ImageProcessor(min_size=min_size, deduplicate=deduplicate, output_format=output_format)
        self.pdf_engine = pdf_engine.lower()
        self.overwrite = overwrite

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_from_file(self, file_path: Path) -> int:
        """Extracts images from a single document file."""
        if not file_path.exists():
            print_status(f"File not found: {file_path}", "error")
            return 0

        ext = file_path.suffix.lower()
        
        # 1. ZIP-based Document Formats
        if ZipExtractor.is_supported(file_path) and ext in ('.docx', '.pptx', '.xlsx', '.odt', '.ods', '.odp', '.zip'):
            print_status(f"Extracting images from ZIP archive: {file_path.name}")
            extractor = ZipExtractor()
            return extractor.extract(file_path, self.output_dir, self.processor)

        # 2. PDF Document Formats
        elif ext == '.pdf':
            print_status(f"Extracting images from PDF: {file_path.name} using engine: '{self.pdf_engine}'")
            
            # Resolve Engine
            engine = self.pdf_engine
            if engine == "auto":
                if HAS_PYMUPDF:
                    engine = "pymupdf"
                elif HAS_PYPDF:
                    engine = "pypdf"
                else:
                    engine = "native"
                print_status(f"Auto-selected engine: '{engine}'")

            # Run chosen engine
            if engine == "pymupdf":
                if not HAS_PYMUPDF:
                    print_status("PyMuPDF requested but not available. Falling back to native.", "warning")
                    return self.extract_from_file_with_engine(file_path, "native")
                return PdfExtractorPyMuPDF().extract(file_path, self.output_dir, self.processor)
            
            elif engine == "pypdf":
                if not HAS_PYPDF:
                    print_status("pypdf requested but not available. Falling back to native.", "warning")
                    return self.extract_from_file_with_engine(file_path, "native")
                return PdfExtractorPyPDF().extract(file_path, self.output_dir, self.processor)
            
            elif engine == "native":
                return PdfExtractorNative().extract(file_path, self.output_dir, self.processor)
            
            elif engine == "binary":
                return PdfExtractorBinary().extract(file_path, self.output_dir, self.processor)
            
            else:
                print_status(f"Unknown PDF engine '{engine}'. Falling back to native.", "warning")
                return PdfExtractorNative().extract(file_path, self.output_dir, self.processor)

        else:
            print_status(f"Unsupported file format: {ext}", "warning")
            return 0

    def extract_from_file_with_engine(self, file_path: Path, engine: str) -> int:
        """Utility function to run a specific PDF engine directly."""
        old_engine = self.pdf_engine
        self.pdf_engine = engine
        res = self.extract_from_file(file_path)
        self.pdf_engine = old_engine
        return res


def main():
    parser = argparse.ArgumentParser(
        description="Document Image Extractor - Extract images from PDFs and Office Documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported formats:
  - PDF (.pdf) via PyMuPDF, PyPDF, Native decoding, or Raw binary scan
  - Word (.docx), PowerPoint (.pptx), Excel (.xlsx)
  - OpenDocument (.odt, .ods, .odp)
  - Generic ZIP files (.zip)
"""
    )
    parser.add_argument("input", help="Path to input document file or directory containing files")
    parser.add_argument("-o", "--output", required=True, help="Output directory where images will be saved")
    parser.add_argument("-m", "--min-size", type=int, default=5000, help="Minimum image file size in bytes (default: 5000)")
    parser.add_argument("-e", "--engine", choices=["auto", "pymupdf", "pypdf", "native", "binary"], default="auto",
                        help="PDF extraction engine (default: auto). 'native' decodes object streams. 'binary' scans raw file markers.")
    parser.add_argument("-f", "--format", choices=["jpg", "png", "bmp", "tiff"], default=None,
                        help="Convert output images to a specific format (requires Pillow)")
    parser.add_argument("-d", "--no-dedup", action="store_false", dest="deduplicate",
                        help="Disable image deduplication based on cryptographic hash")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose log output")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)

    print_status("Document Image Extractor starting...", "header")
    print_status(f"Input path: {input_path}")
    print_status(f"Output directory: {output_dir}")
    print_status(f"Validation library (Pillow): {'FOUND' if HAS_PILLOW else 'MISSING (No image validation/conversion)'}")
    
    if args.format and not HAS_PILLOW:
        print_status("Warning: Format conversion requires Pillow. Falling back to native formats.", "warning")
        args.format = None

    extractor = ImageExtractor(
        output_dir=str(output_dir),
        min_size=args.min_size,
        deduplicate=args.deduplicate,
        pdf_engine=args.engine,
        output_format=args.format,
        overwrite=args.overwrite
    )

    total_extracted = 0
    
    if input_path.is_file():
        total_extracted = extractor.extract_from_file(input_path)
    elif input_path.is_dir():
        print_status(f"Scanning directory {input_path} for documents...")
        extensions = ('.pdf', '.docx', '.pptx', '.xlsx', '.odt', '.ods', '.odp', '.zip')
        files = [p for p in input_path.rglob('*') if p.suffix.lower() in extensions and p.is_file()]
        
        print_status(f"Found {len(files)} files to process.")
        for file in files:
            try:
                count = extractor.extract_from_file(file)
                total_extracted += count
            except Exception as e:
                print_status(f"Error processing {file.name}: {e}", "error")
    else:
        print_status(f"Invalid input path: {input_path}", "error")
        sys.exit(1)

    print_status(f"Extraction complete. Total unique images saved: {total_extracted}", "success")


if __name__ == "__main__":
    main()
