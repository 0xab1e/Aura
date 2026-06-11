"""Per-user storage. Every login name gets its own directory under
.aura/users/<slug>/ holding that person's JD, resume, profile, flashcards,
reports, stories, and coding workspace — so each candidate preps for their
own role with their own history.

Logging in with an existing name opens that person's setup; a new name
creates a fresh one.
"""

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

USERS_DIR = Path(".aura") / "users"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:40]


def extract_text(filename: str, data: bytes) -> str:
    """Text from an uploaded JD/CV: PDFs via pypdf, anything else as UTF-8."""
    if filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("PDF support needs `pip install pypdf` on the server")
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise RuntimeError(f"couldn't read that PDF: {e}")
        if not text.strip():
            raise RuntimeError("that PDF has no extractable text (is it a scan?)")
        return text.strip()
    return data.decode("utf-8", errors="replace").strip()


class UserStore:
    """Paths + metadata for one login name."""

    def __init__(self, name: str):
        self.slug = slugify(name)
        if not self.slug:
            raise ValueError("name must contain at least one letter or digit")
        self.dir = USERS_DIR / self.slug
        self.display_name = name.strip()
        meta = self._read_meta()
        if meta.get("display_name"):
            self.display_name = meta["display_name"]

        self.jd_file = self.dir / "jd.md"
        self.resume_file = self.dir / "resume.md"
        self.profile_file = self.dir / "profile.json"
        self.deck_file = self.dir / "flashcards.json"
        self.reports_dir = self.dir / "reports"
        self.scores_file = self.dir / "scores.csv"
        self.stories_file = self.dir / "stories.md"
        self.workspace_dir = self.dir / "workspace"
        self.uploads_dir = self.dir / "uploads"
        self.session_log = self.dir / "session.md"

    @property
    def exists(self) -> bool:
        return self.dir.exists()

    @property
    def has_jd(self) -> bool:
        return self.jd_file.exists() and bool(self.jd_file.read_text().strip())

    @property
    def has_resume(self) -> bool:
        return self.resume_file.exists() and bool(self.resume_file.read_text().strip())

    def create(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        meta_file = self.dir / "meta.json"
        if not meta_file.exists():
            meta_file.write_text(json.dumps({
                "display_name": self.display_name,
                "created": datetime.now(timezone.utc).isoformat(),
            }, indent=2))

    def save_document(self, kind: str, filename: str, data: bytes) -> int:
        """Store an uploaded JD ('jd') or CV ('resume') for this user: the
        raw upload is kept in uploads/, the extracted text becomes the
        jd.md / resume.md the mentor actually reads. Returns chars saved."""
        if kind not in ("jd", "resume"):
            raise ValueError(f"unknown document kind: {kind}")
        if len(data) > MAX_UPLOAD_BYTES:
            raise RuntimeError("file too large (15 MB max)")
        text = extract_text(filename, data)
        if not text:
            raise RuntimeError("the file is empty")
        self.create()
        self.uploads_dir.mkdir(exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name) or kind
        (self.uploads_dir / f"{kind}_{safe_name}").write_bytes(data)
        target = self.jd_file if kind == "jd" else self.resume_file
        target.write_text(text)
        return len(text)

    def _read_meta(self) -> dict:
        meta_file = self.dir / "meta.json"
        if meta_file.exists():
            try:
                return json.loads(meta_file.read_text())
            except json.JSONDecodeError:
                pass
        return {}
