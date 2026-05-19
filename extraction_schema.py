import re
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean_string(value, max_length: int) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = str(value)
    return str(value).strip()[:max_length]


def _clean_http_url(value) -> str:
    url = _clean_string(value, 500)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return url


def _clean_string_list(value, max_items: int = 30, max_item_length: int = 120) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]

    result = []
    seen = set()
    for item in value:
        text = _clean_string(item, max_item_length)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
        if len(result) >= max_items:
            break
    return result


class ExtractedScholarship(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scholarship_code: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=200)
    link: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=100)
    education_system: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    identity: list[str] = Field(default_factory=list)
    registered_residence: list[str] = Field(default_factory=list)
    nationality: list[str] = Field(default_factory=list)
    amount_summary: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=5000)
    application_date_text: str = Field(default="", max_length=1000)
    contact: str = Field(default="", max_length=1000)
    markdown_content: str = Field(default="", max_length=200000)

    @field_validator(
        "title",
        "category",
        "amount_summary",
        "description",
        "application_date_text",
        "contact",
        "markdown_content",
        mode="before",
    )
    @classmethod
    def normalize_text_field(cls, value, info):
        max_lengths = {
            "title": 200,
            "category": 100,
            "amount_summary": 1000,
            "description": 5000,
            "application_date_text": 1000,
            "contact": 1000,
            "markdown_content": 200000,
        }
        return _clean_string(value, max_lengths[info.field_name])

    @field_validator("scholarship_code", mode="before")
    @classmethod
    def normalize_code(cls, value):
        cleaned = _clean_string(value, 80)
        if not re.match(r"^[a-zA-Z0-9\-_]+$", cleaned):
            return ""
        return cleaned

    @field_validator("link", mode="before")
    @classmethod
    def normalize_link(cls, value):
        return _clean_http_url(value)

    @field_validator(
        "education_system",
        "tags",
        "identity",
        "registered_residence",
        "nationality",
        mode="before",
    )
    @classmethod
    def normalize_list_field(cls, value):
        return _clean_string_list(value)

    @model_validator(mode="after")
    def ensure_markdown_content(self):
        if not self.markdown_content:
            pieces = [self.title, self.description, self.amount_summary, self.application_date_text, self.contact]
            self.markdown_content = "\n\n".join(piece for piece in pieces if piece).strip()
        if not self.markdown_content:
            self.markdown_content = self.title or "未提供內容"
        return self


def normalize_extracted_scholarship(
    raw_data: dict,
    *,
    fallback_code: str | None = None,
    fallback_url: str | None = None,
) -> dict:
    data = raw_data if isinstance(raw_data, dict) else {}
    normalized = ExtractedScholarship.model_validate(data)
    result = normalized.model_dump()

    if fallback_code:
        result["scholarship_code"] = fallback_code
    elif not result["scholarship_code"]:
        result.pop("scholarship_code", None)

    if fallback_url and not result["link"]:
        result["link"] = _clean_http_url(fallback_url)

    return result
