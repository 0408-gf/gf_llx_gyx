from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable

from models.match import Match
from services.importer import FIELD_ALIASES, REQUIRED, _ALIAS_TO_FIELD, _mapped

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
OCR_SOURCE_PREFIX = "截图OCR:"


@dataclass(slots=True)
class OCRToken:
    text: str
    box: tuple[tuple[float, float], ...]
    confidence: float

    @property
    def center_x(self) -> float:
        return sum(point[0] for point in self.box) / len(self.box)

    @property
    def left_x(self) -> float:
        return min(point[0] for point in self.box)

    @property
    def center_y(self) -> float:
        return sum(point[1] for point in self.box) / len(self.box)

    @property
    def height(self) -> float:
        return max(point[1] for point in self.box) - min(point[1] for point in self.box)


@dataclass(slots=True)
class OCRPreviewRow:
    values: dict[str, str]
    confidences: dict[str, float] = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        scores = [score for key, score in self.confidences.items() if self.values.get(key)]
        return min(scores) if scores else 0.0

    def missing_required(self) -> list[str]:
        return [key for key in REQUIRED if not self.values.get(key, "").strip()]


class ScreenshotOCRError(ValueError):
    pass


def is_screenshot(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def _default_engine() -> Callable[[Any], Any]:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except (ImportError, OSError) as exc:
        raise ScreenshotOCRError("截图 OCR 组件未正确打包，请重新安装完整发布包；程序不会联网下载模型。") from exc
    return RapidOCR()


def _prepare_image(path: Path) -> Any:
    try:
        import numpy as np
        from PIL import Image, ImageEnhance, ImageOps

        with Image.open(path) as source:
            source.verify()
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("L")
            if max(image.size) < 2200:
                image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
            return np.asarray(ImageEnhance.Contrast(image).enhance(1.35).convert("RGB"))
    except (OSError, ValueError) as exc:
        raise ScreenshotOCRError("无法读取截图图片；请确认文件未损坏，并使用 JPG、JPEG 或 PNG 格式。") from exc


def _as_tokens(result: Any) -> list[OCRToken]:
    raw = result[0] if isinstance(result, tuple) else result
    if not raw:
        return []
    tokens: list[OCRToken] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        box, text, score = item[:3]
        try:
            points = tuple((float(point[0]), float(point[1])) for point in box)
            confidence = float(score)
        except (TypeError, ValueError, IndexError):
            continue
        cleaned = " ".join(str(text).split())
        if cleaned and len(points) >= 4:
            tokens.append(OCRToken(cleaned, points, confidence))
    return tokens


def cluster_token_rows(tokens: Iterable[OCRToken]) -> list[list[OCRToken]]:
    ordered = sorted(tokens, key=lambda token: (token.center_y, token.center_x))
    if not ordered:
        return []
    tolerance = max(8.0, median(max(token.height, 1.0) for token in ordered) * 0.7)
    rows: list[list[OCRToken]] = []
    centers: list[float] = []
    for token in ordered:
        target = min(range(len(centers)), key=lambda index: abs(centers[index] - token.center_y)) if centers else -1
        if target < 0 or abs(centers[target] - token.center_y) > tolerance:
            rows.append([token])
            centers.append(token.center_y)
        else:
            rows[target].append(token)
            centers[target] = sum(item.center_y for item in rows[target]) / len(rows[target])
    return [sorted(row, key=lambda token: token.center_x) for _, row in sorted(zip(centers, rows), key=lambda item: item[0])]


def _header_field(text: str) -> str | None:
    return _ALIAS_TO_FIELD.get(text.strip().lstrip("\ufeff").casefold())


def tokens_to_preview(tokens: Iterable[OCRToken], filename: str) -> list[OCRPreviewRow]:
    rows = cluster_token_rows(tokens)
    header_index = -1
    columns: list[tuple[float, str]] = []
    for index, row in enumerate(rows):
        recognized = [(token.left_x, field) for token in row if (field := _header_field(token.text))]
        fields = {field for _, field in recognized}
        # 来源可以从文件名如实补齐，其余四项必须由截图表头确认。
        if set(REQUIRED) - {"source"} <= fields and len(fields) == len(recognized):
            header_index, columns = index, sorted(recognized)
            break
    if header_index < 0:
        raise ScreenshotOCRError("未识别到清晰的比赛表头。请保留时间、联赛、主队、客队列，裁掉无关区域并提高截图清晰度后重试。")

    preview: list[OCRPreviewRow] = []
    for row in rows[header_index + 1:]:
        buckets: dict[str, list[OCRToken]] = {field: [] for _, field in columns}
        for token in row:
            _, field = min(columns, key=lambda column: abs(column[0] - token.left_x))
            buckets[field].append(token)
        values = {field: " ".join(token.text for token in items).strip() for field, items in buckets.items()}
        confidences = {field: min((token.confidence for token in items), default=0.0) for field, items in buckets.items()}
        if not any(values.values()):
            continue
        if "source" not in values or not values["source"]:
            values["source"] = f"{OCR_SOURCE_PREFIX}{filename}"
            confidences["source"] = 1.0
        preview.append(OCRPreviewRow(values, confidences))
    if not preview:
        raise ScreenshotOCRError("已识别表头，但没有找到可可靠分列的比赛数据行；请使用完整、清晰且未严重裁剪的表格截图。")
    return preview


def recognize_screenshot(path: str | Path, engine: Callable[[Any], Any] | None = None) -> list[OCRPreviewRow]:
    path = Path(path)
    if not is_screenshot(path):
        raise ScreenshotOCRError("截图 OCR 仅支持 JPG、JPEG 和 PNG 文件。")
    image = _prepare_image(path)
    result = (engine or _default_engine())(image)
    tokens = _as_tokens(result)
    if not tokens:
        raise ScreenshotOCRError("截图中没有识别到清晰文字。请提高分辨率和对比度，避免模糊、反光或严重裁剪后重试。")
    return tokens_to_preview(tokens, path.name)


def preview_rows_to_matches(rows: Iterable[OCRPreviewRow]) -> list[Match]:
    matches: list[Match] = []
    for line, row in enumerate(rows, 1):
        if row.missing_required():
            raise ScreenshotOCRError(f"截图识别第 {line} 行仍缺少必填字段，必须校对完整后才能导入。")
        cleaned = dict(row.values)
        cleaned["match_time"] = (cleaned["match_time"].replace("：", ":").replace("／", "/")
                                 .replace("－", "-").replace("—", "-").strip())
        for key in ("home_odds", "draw_odds", "away_odds", "asian_line", "asian_home_odds",
                    "asian_away_odds", "total_line", "over_odds", "under_odds"):
            value = cleaned.get(key, "").strip().replace("，", ".")
            if value.count(",") == 1 and "." not in value:
                value = value.replace(",", ".")
            cleaned[key] = value
        matches.append(_mapped(cleaned, line))
    if not matches:
        raise ScreenshotOCRError("没有可导入的截图识别数据。")
    return matches
