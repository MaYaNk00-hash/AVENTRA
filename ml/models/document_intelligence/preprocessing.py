import io
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import pypdf


class DocumentInput(BaseModel):
    document_text: Optional[str] = None
    pdf_bytes_base64: Optional[str] = None
    filename: str = "document.txt"


class PreprocessedDocument(BaseModel):
    filename: str
    extracted_text: str
    line_count: int


def preprocess_document(data: Dict[str, Any]) -> PreprocessedDocument:
    doc = DocumentInput(**data)
    text = doc.document_text or ""
    
    # If base64 pdf provided, decode and extract
    if not text and doc.pdf_bytes_base64:
        import base64
        pdf_bytes = base64.b64decode(doc.pdf_bytes_base64)
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text = [p.extract_text() or "" for p in reader.pages]
        text = "\n".join(pages_text)

    cleaned_text = text.strip()
    return PreprocessedDocument(
        filename=doc.filename,
        extracted_text=cleaned_text,
        line_count=len(cleaned_text.splitlines())
    )

