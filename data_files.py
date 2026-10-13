import io
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO

import zstandard

# Downloaded files are saved zstd-compressed with a `.zst` suffix.
COMPRESSED_SUFFIX = ".zst"


@contextmanager
def open_compressed_writer(filename: str) -> Iterator[BinaryIO]:
    """
    Open a zstd-compressed file for writing. The file is written to a temporary path
    and only moved into place once it's complete, so an interrupted download doesn't
    leave a partial file behind.
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    tmp_filename = filename + ".tmp"
    try:
        with (
            open(tmp_filename, "wb") as f,
            zstandard.ZstdCompressor(level=19, threads=-1).stream_writer(f) as writer,
        ):
            yield writer
        os.replace(tmp_filename, filename)
    finally:
        if os.path.exists(tmp_filename):
            os.remove(tmp_filename)


def write_compressed(filename: str, content: bytes):
    with open_compressed_writer(filename) as f:
        f.write(content)


def read_compressed(filename: str) -> bytes:
    with open(filename, "rb") as f:
        return zstandard.ZstdDecompressor().stream_reader(f).read()


def open_compressed(filename: str) -> io.BytesIO:
    return io.BytesIO(read_compressed(filename))
