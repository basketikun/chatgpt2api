"""youtube — lấy transcript video YouTube qua youtube-transcript-api.

Tools:
- get_transcript(video_id_or_url, lang): transcript theo ngôn ngữ
- list_available_languages(video_id_or_url): liệt kê ngôn ngữ có sẵn
"""

from __future__ import annotations

import logging
import re

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("youtube")

YT_ID_PATTERNS = [
    re.compile(r"(?:v=|/v/|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})"),
    re.compile(r"^([A-Za-z0-9_-]{11})$"),
]


def _extract_video_id(s: str) -> str | None:
    s = s.strip()
    for pat in YT_ID_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(1)
    return None


@mcp.tool()
def get_transcript(video: str, languages: str = "vi,en") -> str:
    """Lấy transcript một video YouTube.

    Args:
        video: ID video (11 ký tự) hoặc URL YouTube đầy đủ.
        languages: Danh sách mã ngôn ngữ ưu tiên, phân cách dấu phẩy (mặc định 'vi,en').

    Returns:
        Toàn văn transcript ghép các đoạn lại; hoặc thông báo lỗi nếu video không có transcript.
    """
    vid = _extract_video_id(video)
    if not vid:
        return f"Không nhận diện được video ID từ '{video}'."
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        langs = [s.strip() for s in languages.split(",") if s.strip()]
        # youtube-transcript-api >=0.6: API changed, try multiple patterns
        items = None
        errors = []
        # Pattern 1: new API (0.6+) — instance method
        try:
            yt = YouTubeTranscriptApi()
            items = yt.fetch(vid, languages=langs)
        except (TypeError, AttributeError) as e:
            errors.append(f"fetch: {e}")
        except Exception as e:
            errors.append(f"fetch: {e}")
        # Pattern 2: old API — class method with get_transcript
        if items is None:
            try:
                items = YouTubeTranscriptApi.get_transcript(vid, languages=langs)
            except (TypeError, AttributeError) as e:
                errors.append(f"get_transcript: {e}")
            except Exception as e:
                errors.append(f"get_transcript: {e}")
        # Pattern 3: direct list_transcripts + fetch
        if items is None:
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(vid)
                t = transcript_list.find_transcript(langs)
                items = t.fetch()
            except Exception as e:
                errors.append(f"list_transcripts: {e}")
        if items is None:
            return f"Không lấy được transcript cho video {vid}: {'; '.join(errors)}"
    except ImportError:
        return "Thiếu thư viện youtube-transcript-api."

    text_parts = []
    for it in items:
        if isinstance(it, dict):
            t = it.get("text", "").strip()
        else:
            t = getattr(it, "text", "").strip()
        if t:
            text_parts.append(t)
    full = " ".join(text_parts)
    if len(full) > 8000:
        full = full[:8000] + "\n\n[…đã cắt do quá dài]"
    return f"**Transcript video {vid}:**\n\n{full}"


@mcp.tool()
def list_available_languages(video: str) -> str:
    """Liệt kê ngôn ngữ transcript có sẵn cho một video YouTube.

    Args:
        video: ID hoặc URL video.

    Returns:
        Danh sách ngôn ngữ với mã (vd: vi, en, ja) và loại (auto-generated/manual).
    """
    vid = _extract_video_id(video)
    if not vid:
        return f"Không nhận diện được video ID từ '{video}'."
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcripts = YouTubeTranscriptApi.list_transcripts(vid)
    except Exception as exc:
        return f"Không lấy được danh sách ngôn ngữ cho {vid}: {exc}"

    lines = [f"**Ngôn ngữ transcript có sẵn cho video {vid}:**", ""]
    for t in transcripts:
        kind = "tự động" if t.is_generated else "thủ công"
        lines.append(f"- `{t.language_code}` ({t.language}, {kind})")
    return "\n".join(lines)
