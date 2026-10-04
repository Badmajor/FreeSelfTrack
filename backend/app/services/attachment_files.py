import hashlib
import unicodedata
import warnings
from dataclasses import dataclass
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

from app.core.object_storage import CHUNK_SIZE
from app.services.errors import DomainError, InvalidWorkflowError

MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_FILES = 5
MAX_PIXELS = 40_000_000
SAFE_IMAGES = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}


class FileTooLarge(DomainError):
    status_code = 413


def normalized_filename(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\\", "/").split("/")[-1])
    value = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    return value.strip(" .")[:255] or "file"


def media_type(stream: BinaryIO) -> str:
    stream.seek(0)
    signature = stream.read(12)
    stream.seek(0)
    looks_raster = signature.startswith((b"\x89PNG", b"\xff\xd8", b"GIF87a", b"GIF89a")) or (
        signature.startswith(b"RIFF") and signature[8:12] == b"WEBP"
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                kind = SAFE_IMAGES.get(image.format or "")
                if kind is None:
                    return "application/octet-stream"
                pixels = 0
                frame = 0
                while True:
                    pixels += image.width * image.height
                    if pixels > MAX_PIXELS:
                        raise InvalidWorkflowError("Image exceeds pixel limit")
                    image.load()
                    frame += 1
                    try:
                        image.seek(frame)
                    except EOFError:
                        break
            stream.seek(0)
            with Image.open(stream) as image:
                image.verify()
            return kind
    except UnidentifiedImageError:
        if looks_raster:
            raise InvalidWorkflowError("Invalid image content") from None
        return "application/octet-stream"
    except (
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise InvalidWorkflowError("Invalid or oversized image") from None
    finally:
        stream.seek(0)


@dataclass
class Uploaded:
    filename: str
    stream: BinaryIO
    size: int
    sha256: str
    media_type: str
    original_filename: str


def inspect_file(filename: str, stream: BinaryIO) -> Uploaded:
    stream.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHUNK_SIZE):
        size += len(chunk)
        if size > MAX_FILE_SIZE:
            raise FileTooLarge("File exceeds 25 MB")
        digest.update(chunk)
    return Uploaded(
        normalized_filename(filename),
        stream,
        size,
        digest.hexdigest(),
        media_type(stream),
        filename,
    )
