"""Document upload, listing, deletion."""
import io
import logging
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Form
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User
from app.models.document import Document
from app.schemas.document import DocumentResponse, DocumentUploadResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_TEXT_LENGTH = 500_000  # 500K chars — keep SQLite happy


def _extract_text_from_pdf(data: bytes) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n\n".join(pages), len(reader.pages)
    except ImportError:
        raise HTTPException(status_code=500, detail="PDF parser not installed. Run: pip install pypdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")


def _extract_text_from_docx(data: bytes) -> tuple[str, int]:
    try:
        from docx import Document as DocxDocument
        doc = DocxDocument(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs), 1
    except ImportError:
        raise HTTPException(status_code=500, detail="DOCX parser not installed. Run: pip install python-docx")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read DOCX: {e}")


def _extract_text_plain(data: bytes) -> tuple[str, int]:
    try:
        return data.decode("utf-8", errors="ignore"), 1
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read text file: {e}")


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 10 MB.")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    fname_lower = file.filename.lower()
    if fname_lower.endswith(".pdf"):
        text, pages = _extract_text_from_pdf(data)
    elif fname_lower.endswith(".docx"):
        text, pages = _extract_text_from_docx(data)
    elif fname_lower.endswith((".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".ts")):
        text, pages = _extract_text_plain(data)
    else:
        raise HTTPException(
            status_code=415,
            detail="Supported formats: .pdf, .docx, .txt, .md, .csv, .json, .log, .py, .js, .ts",
        )

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract any text. The file may be a scanned image (OCR not supported yet).",
        )

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "\n\n[Document truncated at 500,000 characters]"

    doc = Document(
        user_id=user.id,
        conversation_id=conversation_id,
        filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        text_content=text,
        page_count=pages,
        char_count=len(text),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return DocumentUploadResponse(
        document_id=doc.id,
        filename=doc.filename,
        page_count=doc.page_count,
        char_count=doc.char_count,
        preview=text[:300].strip(),
    )


@router.get("/", response_model=list[DocumentResponse])
def list_documents(
    conversation_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Document).filter(Document.user_id == user.id)
    if conversation_id:
        q = q.filter(Document.conversation_id == conversation_id)
    docs = q.order_by(Document.created_at.desc()).limit(50).all()
    return docs


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(Document, document_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    db.delete(doc)
    db.commit()
    return {"status": "deleted"}