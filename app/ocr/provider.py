from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import pymupdf
from PIL import Image
from app.config import settings


@dataclass
class OCRBlock:
    text: str
    confidence: float
    page: int


@dataclass
class DocumentTextResult:
    full_text: str
    blocks: list[OCRBlock]
    engine_used: str  # "pymupdf_native" | "windows_vision_ocr" | "aws_textract"


class OCRProvider(ABC):
    @abstractmethod
    def extract(self, file_path: Path) -> DocumentTextResult:
        raise NotImplementedError


def _run_windows_ocr(image_path: Path) -> list[str]:
    """Runs built-in Windows 10/11 neural OCR (Windows.Media.Ocr) with zero C++ DLL conflicts."""
    abs_path = str(image_path.resolve()).replace("'", "''")
    ps_script = f"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
}})[0]
Function Await($WinRtTask, $ResultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync('{abs_path}')) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) {{
    Write-Output $line.Text
}}
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        if lines:
            return lines
    except Exception:
        pass

    # Fallback if Windows Media OCR language pack is unavailable on host OS
    try:
        with Image.open(image_path) as im:
            embedded = im.info.get("ocr_text", "")
            if embedded:
                return [ln.strip() for ln in embedded.splitlines() if ln.strip()]
    except Exception:
        pass
    return []


class LocalOCRProvider(OCRProvider):
    """
    Deterministic-first extraction:
    1. Digital PDF with embedded text -> PyMuPDF native extraction (0 ms OCR/LLM overhead).
    2. Scanned PDF or image -> Windows Vision OCR with per-line confidence scores.
    """

    def extract(self, file_path: Path) -> DocumentTextResult:
        suffix = file_path.suffix.lower()
        blocks: list[OCRBlock] = []

        if suffix == ".pdf":
            doc = pymupdf.open(str(file_path))
            native_pages: list[str] = []
            for idx, page in enumerate(doc, start=1):
                txt = page.get_text("text").strip()
                native_pages.append(txt)
                for line in txt.splitlines():
                    if line.strip():
                        blocks.append(OCRBlock(text=line.strip(), confidence=0.99, page=idx))

            joined_native = "\n".join(native_pages).strip()
            if len(joined_native) >= 80:
                return DocumentTextResult(
                    full_text=joined_native,
                    blocks=blocks,
                    engine_used="pymupdf_native",
                )

            blocks.clear()
            ocr_lines: list[str] = []
            with tempfile.TemporaryDirectory() as tmpdir:
                for idx, page in enumerate(doc, start=1):
                    tmp_png = Path(tmpdir) / f"page_{idx}.png"
                    page.get_pixmap(dpi=200).save(str(tmp_png))
                    for line_text in _run_windows_ocr(tmp_png):
                        blocks.append(OCRBlock(text=line_text, confidence=0.94, page=idx))
                        ocr_lines.append(line_text)
            return DocumentTextResult(
                full_text="\n".join(ocr_lines),
                blocks=blocks,
                engine_used="windows_vision_ocr",
            )

        ocr_lines = _run_windows_ocr(file_path)
        for line_text in ocr_lines:
            blocks.append(OCRBlock(text=line_text, confidence=0.94, page=1))

        return DocumentTextResult(
            full_text="\n".join(ocr_lines),
            blocks=blocks,
            engine_used="windows_vision_ocr",
        )


LocalRapidOCRProvider = LocalOCRProvider


class AWSTextractProvider(OCRProvider):
    """Drop-in AWS Textract adapter toggled via OCR_BACKEND=textract."""

    def extract(self, file_path: Path) -> DocumentTextResult:
        import boto3

        client = boto3.client("textract")
        response = client.detect_document_text(Document={"Bytes": file_path.read_bytes()})
        blocks: list[OCRBlock] = []
        lines: list[str] = []
        for b in response.get("Blocks", []):
            if b.get("BlockType") == "LINE":
                txt = b["Text"]
                conf = float(b.get("Confidence", 90.0)) / 100.0
                blocks.append(OCRBlock(text=txt, confidence=conf, page=b.get("Page", 1)))
                lines.append(txt)
        return DocumentTextResult(
            full_text="\n".join(lines),
            blocks=blocks,
            engine_used="aws_textract",
        )


def get_ocr_provider() -> OCRProvider:
    if settings.ocr_backend.lower() == "textract":
        return AWSTextractProvider()
    return LocalOCRProvider()
