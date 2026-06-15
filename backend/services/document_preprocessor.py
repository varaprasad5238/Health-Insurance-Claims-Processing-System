from pathlib import Path


class UnsupportedFormatError(ValueError):
    def __init__(self, mime_type: str):
        super().__init__(f"Unsupported document format: {mime_type}")
        self.mime_type = mime_type


def prepare_for_vision_call(file_path: str, mime_type: str) -> list[bytes]:
    """Always return a list of image bytes (PNG/JPEG), never raw PDF bytes."""
    if mime_type.startswith("image/"):
        return [Path(file_path).read_bytes()]

    if mime_type == "application/pdf":
        import fitz

        doc = fitz.open(file_path)
        images: list[bytes] = []
        try:
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                images.append(pix.tobytes("png"))
        finally:
            doc.close()
        return images

    raise UnsupportedFormatError(mime_type)