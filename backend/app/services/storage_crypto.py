"""Encryption at rest for stored uploads (AES-256-GCM, chunked).

File layout (version 1):

    header  = b"MTENC\\x01" | key_id (8) | nonce_prefix (7) | chunk_size (4, BE) | plaintext_size (8, BE)
    chunk_i = AESGCM(key).encrypt(nonce_prefix | i (4, BE) | last (1), plaintext_i, aad=header)

Each chunk is authenticated with the header as associated data. The nonce binds
the chunk's position and whether it is the final chunk, so modification,
truncation, reordering and appended data all fail authentication. Large DICOM or
NIfTI files are streamed chunk by chunk; nothing loads a whole file into memory.

Keys never live in the repository. They come from MEDTWIN_STORAGE_KEY_FILE (a JSON
file outside the repo: {"active": "<id>", "keys": {"<id>": "<base64 32 bytes>"}})
or MEDTWIN_STORAGE_KEYS ("base64key[,base64key...]", first is active). A key's id
is the first 8 bytes of SHA-256(key), so rotation only needs the old key kept
available until files are re-encrypted (scripts/storage_keys.py rotate).

Files without the magic header are legacy plaintext and remain readable; with
MEDTWIN_STORAGE_ENCRYPTION=required new writes are always encrypted.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import secrets
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"MTENC\x01"
HEADER = struct.Struct(">6s8s7sIQ")
TAG_BYTES = 16
DEFAULT_CHUNK = 1024 * 1024


class StorageCryptoError(Exception):
    """Encrypted content failed authentication or cannot be decrypted."""


class StorageKeyError(StorageCryptoError):
    """No key is configured, or the file was encrypted with a key that is not available."""


@dataclass(frozen=True)
class KeyRing:
    keys: dict[bytes, bytes]  # key id -> 32-byte key
    active_id: Optional[bytes]

    @property
    def enabled(self) -> bool:
        return self.active_id is not None

    def active(self) -> tuple[bytes, bytes]:
        if self.active_id is None:
            raise StorageKeyError("Storage encryption is not configured (set MEDTWIN_STORAGE_KEY_FILE or MEDTWIN_STORAGE_KEYS).")
        return self.active_id, self.keys[self.active_id]

    def get(self, key_id: bytes) -> bytes:
        try:
            return self.keys[key_id]
        except KeyError:
            raise StorageKeyError(f"File was encrypted with key {key_id.hex()}, which is not configured.") from None


def key_id_for(key: bytes) -> bytes:
    return hashlib.sha256(key).digest()[:8]


def _decode_key(text: str) -> bytes:
    key = base64.b64decode(text.strip(), validate=True)
    if len(key) != 32:
        raise StorageKeyError("Storage keys must be 32 bytes (base64-encoded).")
    return key


def load_keyring(environ: Optional[dict] = None) -> KeyRing:
    environ = os.environ if environ is None else environ
    keys: dict[bytes, bytes] = {}
    active: Optional[bytes] = None
    key_file = environ.get("MEDTWIN_STORAGE_KEY_FILE", "").strip()
    if key_file:
        payload = json.loads(Path(key_file).read_text(encoding="utf-8"))
        for _name, encoded in payload.get("keys", {}).items():
            key = _decode_key(encoded)
            keys[key_id_for(key)] = key
        if payload.get("active"):
            active = key_id_for(_decode_key(payload["keys"][payload["active"]]))
    inline = environ.get("MEDTWIN_STORAGE_KEYS", "").strip()
    if inline:
        for index, encoded in enumerate(part for part in inline.split(",") if part.strip()):
            key = _decode_key(encoded)
            keys[key_id_for(key)] = key
            if index == 0 and active is None:
                active = key_id_for(key)
    return KeyRing(keys=keys, active_id=active)


def generate_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def is_encrypted(path: Path) -> bool:
    with open(path, "rb") as handle:
        return handle.read(len(MAGIC)) == MAGIC


def _nonce(prefix: bytes, index: int, last: bool) -> bytes:
    return prefix + struct.pack(">IB", index, 1 if last else 0)


def encrypt_stream(source: BinaryIO, sink: BinaryIO, plaintext_size: int, keyring: KeyRing, chunk_size: int = DEFAULT_CHUNK) -> None:
    key_id, key = keyring.active()
    prefix = secrets.token_bytes(7)
    header = HEADER.pack(MAGIC, key_id, prefix, chunk_size, plaintext_size)
    sink.write(header)
    aead = AESGCM(key)
    chunks = max(1, -(-plaintext_size // chunk_size))
    written = 0
    for index in range(chunks):
        block = source.read(chunk_size) if plaintext_size else b""
        written += len(block)
        last = index == chunks - 1
        if (len(block) != chunk_size and not last) or (last and written != plaintext_size):
            raise StorageCryptoError("Source changed size while being encrypted.")
        sink.write(aead.encrypt(_nonce(prefix, index, last), block, header))
    if source.read(1):
        raise StorageCryptoError("Source is longer than the declared size.")


def encrypt_file(plain: Path, target: Path, keyring: KeyRing, chunk_size: int = DEFAULT_CHUNK) -> None:
    """Encrypts plain into target atomically (temporary file + os.replace)."""
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(6)}.enc-part")
    try:
        with open(plain, "rb") as source, open(temporary, "xb") as sink:
            encrypt_stream(source, sink, plain.stat().st_size, keyring, chunk_size)
            sink.flush()
            os.fsync(sink.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def iter_plaintext(path: Path, keyring: KeyRing) -> Iterator[bytes]:
    """Yields authenticated plaintext chunks; raises StorageCryptoError on any tampering."""
    with open(path, "rb") as handle:
        raw = handle.read(HEADER.size)
        if raw[: len(MAGIC)] != MAGIC:
            yield raw
            yield from iter(lambda: handle.read(DEFAULT_CHUNK), b"")
            return
        if len(raw) != HEADER.size:
            raise StorageCryptoError("Encrypted file header is truncated.")
        _magic, key_id, prefix, chunk_size, plaintext_size = HEADER.unpack(raw)
        if chunk_size <= 0 or chunk_size > 64 * 1024 * 1024:
            raise StorageCryptoError("Encrypted file header is invalid.")
        aead = AESGCM(keyring.get(key_id))
        chunks = max(1, -(-plaintext_size // chunk_size))
        produced = 0
        for index in range(chunks):
            last = index == chunks - 1
            expected = (plaintext_size - chunk_size * index if last else chunk_size) + TAG_BYTES
            sealed = handle.read(expected)
            if len(sealed) != expected:
                raise StorageCryptoError("Encrypted file is truncated.")
            try:
                block = aead.decrypt(_nonce(prefix, index, last), sealed, raw)
            except InvalidTag:
                raise StorageCryptoError("Encrypted file failed authentication (modified or wrong key).") from None
            produced += len(block)
            yield block
        if handle.read(1):
            raise StorageCryptoError("Encrypted file has trailing data.")
        if produced != plaintext_size:
            raise StorageCryptoError("Decrypted size does not match the header.")


def read_plaintext(path: Path, keyring: KeyRing) -> bytes:
    return b"".join(iter_plaintext(path, keyring))


def file_key_id(path: Path) -> Optional[bytes]:
    """The key id in an encrypted file's header, or None for legacy plaintext."""
    with open(path, "rb") as handle:
        raw = handle.read(HEADER.size)
    return HEADER.unpack(raw)[1] if raw[: len(MAGIC)] == MAGIC and len(raw) == HEADER.size else None


class _BlockReader:
    """read(n) over an iterator of byte blocks, so plaintext can stream from one file into encrypt_stream."""

    def __init__(self, blocks: Iterator[bytes]):
        self._blocks, self._buffer = blocks, b""

    def read(self, size: int = -1) -> bytes:
        while size < 0 or len(self._buffer) < size:
            block = next(self._blocks, None)
            if block is None:
                break
            self._buffer += block
        size = len(self._buffer) if size < 0 else size
        data, self._buffer = self._buffer[:size], self._buffer[size:]
        return data


def reencrypt_in_place(path: Path, keyring: KeyRing, chunk_size: int = DEFAULT_CHUNK) -> str:
    """Encrypts a legacy plaintext file, or re-encrypts a file under the active key.

    Plaintext streams from the old file into the new ciphertext without touching disk.
    The new file is decrypted and compared (SHA-256) with the original plaintext before
    it atomically replaces the old one. Returns the plaintext SHA-256."""
    keyring.active()  # fail before writing anything when no key is configured
    key_id = file_key_id(path)
    if key_id is None:
        size = path.stat().st_size
    else:
        with open(path, "rb") as handle:
            size = HEADER.unpack(handle.read(HEADER.size))[4]
    original = hashlib.sha256()

    def blocks() -> Iterator[bytes]:
        for block in iter_plaintext(path, keyring):
            original.update(block)
            yield block

    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.enc-part")
    try:
        with open(temporary, "xb") as sink:
            encrypt_stream(_BlockReader(blocks()), sink, size, keyring, chunk_size)
            sink.flush()
            os.fsync(sink.fileno())
        rewritten = hashlib.sha256()
        for block in iter_plaintext(temporary, keyring):
            rewritten.update(block)
        if rewritten.hexdigest() != original.hexdigest():
            raise StorageCryptoError("Re-encrypted content does not match the original; the original was kept.")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return original.hexdigest()


@contextlib.contextmanager
def plaintext_path(path: Path, keyring: KeyRing, work_dir: Path) -> Iterator[Path]:
    """A readable plaintext path for libraries that need a file (pydicom, nibabel, SimpleITK).

    Legacy plaintext files are yielded as-is. Encrypted files are decrypted into a
    private per-call directory under work_dir, keeping the original name and suffix
    (readers dispatch on extensions such as .nii.gz), and removed afterwards."""
    if not is_encrypted(path):
        yield path
        return
    work_dir.mkdir(parents=True, exist_ok=True)
    private = work_dir / secrets.token_hex(12)
    private.mkdir()
    target = private / path.name
    try:
        with open(target, "xb") as sink:
            for block in iter_plaintext(path, keyring):
                sink.write(block)
        yield target
    finally:
        shutil.rmtree(private, ignore_errors=True)


def purge_work_dir(work_dir: Path, older_than_seconds: float = 3600.0) -> int:
    """Removes decrypted copies left behind by an interrupted process. Entries younger
    than the threshold may belong to another live process (API or worker) and are kept.
    Returns the number of entries removed."""
    import time

    if not work_dir.exists():
        return 0
    removed = 0
    cutoff = time.time() - older_than_seconds
    for entry in work_dir.iterdir():
        try:
            if entry.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(entry, ignore_errors=True) if entry.is_dir() else entry.unlink(missing_ok=True)
        removed += 1
    return removed
