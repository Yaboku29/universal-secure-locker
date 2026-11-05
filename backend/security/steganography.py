import os
import re
import tempfile
from pathlib import Path

from PIL import Image


_MAGIC = b"USLSTG\x01"
_HEADER_SIZE = len(_MAGIC) + 4
_MAX_CIPHERTEXT_CHARS = 64 * 1024
_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]+$")
_MAX_IMAGE_PIXELS = 40_000_000


def _validate_ciphertext(ciphertext: str) -> bytes:
    if (
        not isinstance(ciphertext, str)
        or not ciphertext
        or len(ciphertext) > _MAX_CIPHERTEXT_CHARS
        or len(ciphertext) % 2
        or not _HEX_PATTERN.fullmatch(ciphertext)
    ):
        raise ValueError(
            "Pesan harus berupa ciphertext heksadesimal dari fitur super enkripsi."
        )
    return ciphertext.encode("ascii")


def _load_png(image_path: Path) -> Image.Image:
    try:
        image = Image.open(image_path)
    except (OSError, ValueError) as error:
        raise ValueError("File gambar tidak dapat dibuka.") from error
    if image.format != "PNG":
        image.close()
        raise ValueError("Steganografi hanya mendukung gambar PNG.")
    if image.width * image.height > _MAX_IMAGE_PIXELS:
        image.close()
        raise ValueError("Ukuran gambar melebihi batas 40 megapiksel.")
    try:
        image.load()
    except (OSError, ValueError) as error:
        image.close()
        raise ValueError("Data gambar PNG rusak atau tidak lengkap.") from error
    return image


def _read_bits(pixels: bytes, channel_count: int, bit_count: int) -> bytes:
    result = bytearray((bit_count + 7) // 8)
    for bit_index in range(bit_count):
        channel_index = (bit_index // 3) * channel_count + bit_index % 3
        bit = pixels[channel_index] & 1
        result[bit_index // 8] |= bit << (7 - bit_index % 8)
    return bytes(result)


def hide_message(
    image_path: str | Path,
    secret_text: str,
    output_path: str | Path,
) -> Path:
    """Hide a super-encryption hex ciphertext in a lossless PNG image."""
    source = Path(image_path)
    destination = Path(output_path)
    if not destination.suffix.lower() == ".png":
        raise ValueError("File hasil steganografi harus menggunakan ekstensi .png.")
    if source.resolve() == destination.resolve():
        raise ValueError("Gambar sumber dan tujuan tidak boleh sama.")

    ciphertext = _validate_ciphertext(secret_text)
    if len(ciphertext) > 0xFFFFFFFF:
        raise ValueError("Pesan terlalu besar untuk format steganografi.")
    payload = _MAGIC + len(ciphertext).to_bytes(4, "big") + ciphertext

    with _load_png(source) as image:
        preserve_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
        mode = "RGBA" if preserve_alpha else "RGB"
        channels = 4 if mode == "RGBA" else 3
        capacity_bits = image.width * image.height * 3
        if len(payload) * 8 > capacity_bits:
            raise ValueError(
                "Kapasitas gambar tidak cukup untuk menyimpan ciphertext ini."
            )

        with image.convert(mode) as normalized:
            pixels = bytearray(normalized.tobytes())
            bit_index = 0
            for value in payload:
                for shift in range(7, -1, -1):
                    channel_index = (bit_index // 3) * channels + bit_index % 3
                    pixels[channel_index] = (
                        pixels[channel_index] & 0xFE
                    ) | ((value >> shift) & 1)
                    bit_index += 1

        output = Image.frombytes(mode, image.size, bytes(pixels))
        save_options: dict[str, object] = {}
        if "icc_profile" in image.info:
            save_options["icc_profile"] = image.info["icc_profile"]
        if "dpi" in image.info:
            save_options["dpi"] = image.info["dpi"]

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=".usl-steg-",
            suffix=".png",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        output.save(temporary_path, format="PNG", **save_options)
        os.replace(temporary_path, destination)
    finally:
        output.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return destination


def reveal_message(image_path: str | Path) -> str:
    """Extract the original super-encryption hex ciphertext from a PNG."""
    source = Path(image_path)
    with _load_png(source) as image:
        preserve_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
        mode = "RGBA" if preserve_alpha else "RGB"
        channels = 4 if mode == "RGBA" else 3
        capacity_bits = image.width * image.height * 3
        if capacity_bits < _HEADER_SIZE * 8:
            raise ValueError("Gambar tidak memiliki data steganografi yang valid.")
        with image.convert(mode) as normalized:
            pixels = normalized.tobytes()
            header = _read_bits(pixels, channels, _HEADER_SIZE * 8)
            if not header.startswith(_MAGIC):
                raise ValueError("Pesan steganografi tidak ditemukan pada gambar.")
            payload_length = int.from_bytes(header[len(_MAGIC):], "big")
            if (
                payload_length == 0
                or payload_length > _MAX_CIPHERTEXT_CHARS
                or (payload_length + _HEADER_SIZE) * 8 > capacity_bits
            ):
                raise ValueError("Header atau panjang pesan steganografi tidak valid.")

            encoded = _read_bits(
                pixels,
                channels,
                (_HEADER_SIZE + payload_length) * 8,
            )[_HEADER_SIZE:]

    try:
        ciphertext = encoded.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("Pesan steganografi bukan ciphertext heksadesimal.") from error
    if not _HEX_PATTERN.fullmatch(ciphertext):
        raise ValueError("Pesan steganografi bukan ciphertext heksadesimal.")
    return ciphertext
