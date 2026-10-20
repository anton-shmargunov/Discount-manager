"""
Google Drive upload / list / download / rename. No Streamlit imports.

Credentials are a plain dict (from ``st.secrets['gdrive']`` in the UI).
All file operations stay inside the folder tree under ``root_folder_id``:
a folder is usable only after it was reached from the root through this store.
"""

from __future__ import annotations

import functools
import io
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol, TypeVar

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
TOKEN_URI = "https://oauth2.googleapis.com/token"
FOLDER_MIME = "application/vnd.google-apps.folder"
_NAME_UNSAFE = re.compile(r"[\\/]")
_FILE_FIELDS = "id, name, modifiedTime, createdTime, size, parents, mimeType"


class DriveClientError(RuntimeError):
    """Drive API or configuration error."""


@dataclass(frozen=True)
class DriveConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    root_folder_id: str
    token_uri: str = TOKEN_URI
    scopes: tuple[str, ...] = (DRIVE_SCOPE,)


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    modified_time: str = ""
    size: int = 0
    parent_id: str = ""
    created_time: str = ""
    is_folder: bool = False


class DriveClient(Protocol):
    def list_children(self, folder_id: str, mime_type: Optional[str] = None) -> list[DriveFile]:
        ...

    def get_file(self, file_id: str) -> DriveFile:
        ...

    def download(self, file_id: str) -> bytes:
        ...

    def create_file(
        self, folder_id: str, name: str, data: bytes, mime_type: str
    ) -> DriveFile:
        ...

    def update_file(self, file_id: str, data: bytes, mime_type: str) -> DriveFile:
        ...

    def rename(self, file_id: str, new_name: str) -> DriveFile:
        ...

    def create_folder(self, parent_id: str, name: str) -> DriveFile:
        ...


def parse_drive_config(secrets: Mapping[str, Any] | None) -> Optional[DriveConfig]:
    """Return a config when every required field is present and non-empty."""
    if not secrets:
        return None
    try:
        raw = dict(secrets)
    except (TypeError, ValueError):
        return None
    required = ("client_id", "client_secret", "refresh_token", "root_folder_id")
    values = {key: str(raw.get(key) or "").strip() for key in required}
    if not all(values.values()):
        return None
    token_uri = str(raw.get("token_uri") or TOKEN_URI).strip() or TOKEN_URI
    return DriveConfig(token_uri=token_uri, **values)


def safe_drive_filename(name: str) -> str:
    text = _NAME_UNSAFE.sub("_", str(name or "").strip()) or "file"
    return text.rstrip(". ") or "file"


def _oldest_first(items: list[DriveFile]) -> list[DriveFile]:
    return sorted(items, key=lambda item: (item.created_time or item.modified_time, item.id))


class DriveStore:
    """Drive access restricted to the tree under the configured root folder."""

    def __init__(self, config: DriveConfig, client: DriveClient) -> None:
        self.config = config
        self.client = client
        self._allowed: set[str] = {config.root_folder_id}
        self.warnings: list[str] = []

    @property
    def root_id(self) -> str:
        return self.config.root_folder_id

    def _require_allowed_folder(self, folder_id: str) -> str:
        folder = str(folder_id or "").strip()
        if folder not in self._allowed:
            raise DriveClientError("Folder is not inside the configured PBA Drive folder.")
        return folder

    def list_subfolders(self, parent_id: str) -> list[DriveFile]:
        parent = self._require_allowed_folder(parent_id)
        folders = self.client.list_children(parent, mime_type=FOLDER_MIME)
        self._allowed.update(item.id for item in folders)
        return folders

    def find_subfolder(self, parent_id: str, name: str) -> Optional[str]:
        """Id of the child folder ``name`` (oldest one when duplicated), or ``None``."""
        folder_name = safe_drive_filename(name)
        matches = [item for item in self.list_subfolders(parent_id) if item.name == folder_name]
        if not matches:
            return None
        ordered = _oldest_first(matches)
        if len(ordered) > 1:
            self.warnings.append(
                f"Drive has {len(ordered)} folders named '{folder_name}'; "
                "using the oldest. Remove the duplicates in Drive."
            )
        return ordered[0].id

    def ensure_subfolder(self, parent_id: str, name: str) -> str:
        """Create or reuse a child folder of an allowed folder."""
        existing = self.find_subfolder(parent_id, name)
        if existing:
            return existing
        created = self.client.create_folder(parent_id, safe_drive_filename(name))
        self._allowed.add(created.id)
        return self.find_subfolder(parent_id, name) or created.id

    def folder_path(self, names: list[str], *, create: bool) -> Optional[str]:
        """Resolve ``root / names[0] / names[1] ...``; ``None`` when missing and not creating."""
        folder = self.root_id
        for name in names:
            next_id = (
                self.ensure_subfolder(folder, name)
                if create
                else self.find_subfolder(folder, name)
            )
            if not next_id:
                return None
            folder = next_id
        return folder

    def list_files(
        self,
        folder_id: str,
        *,
        name_suffix: Optional[str] = None,
    ) -> list[DriveFile]:
        folder = self._require_allowed_folder(folder_id)
        files = [
            item
            for item in self.client.list_children(folder)
            if item.name and not item.is_folder
        ]
        if name_suffix:
            suffix = name_suffix.lower()
            files = [item for item in files if item.name.lower().endswith(suffix)]
        return sorted(files, key=lambda item: (item.modified_time, item.name), reverse=True)

    def download_file(self, folder_id: str, file_id: str) -> bytes:
        folder = self._require_allowed_folder(folder_id)
        info = self.client.get_file(file_id)
        if info.parent_id != folder:
            raise DriveClientError("File is not in the expected Drive folder.")
        return self.client.download(file_id)

    def upload_bytes(
        self,
        folder_id: str,
        filename: str,
        data: bytes,
        mime_type: str = "application/octet-stream",
        *,
        overwrite: bool = False,
    ) -> DriveFile:
        """Create a file. An existing name is refused unless ``overwrite``."""
        folder = self._require_allowed_folder(folder_id)
        name = safe_drive_filename(filename)
        existing = [
            item
            for item in self.client.list_children(folder)
            if item.name == name and not item.is_folder
        ]
        if existing:
            if not overwrite:
                raise DriveClientError(f"'{name}' already exists in Drive; files are never overwritten.")
            return self.client.update_file(existing[0].id, data, mime_type)
        return self.client.create_file(folder, name, data, mime_type)

    def rename_file(self, folder_id: str, file_id: str, new_name: str) -> DriveFile:
        folder = self._require_allowed_folder(folder_id)
        info = self.client.get_file(file_id)
        if info.parent_id != folder:
            raise DriveClientError("File is not in the expected Drive folder.")
        name = safe_drive_filename(new_name)
        clash = [
            item
            for item in self.client.list_children(folder)
            if item.name == name and item.id != file_id
        ]
        if clash:
            raise DriveClientError(f"'{name}' already exists in Drive.")
        return self.client.rename(file_id, name)


class InMemoryDriveClient:
    """Test double that stores files in memory."""

    def __init__(self) -> None:
        self._seq = 0
        self.files: dict[str, dict[str, Any]] = {}

    def _next_id(self) -> str:
        self._seq += 1
        return f"id{self._seq}"

    def list_children(self, folder_id: str, mime_type: Optional[str] = None) -> list[DriveFile]:
        items: list[DriveFile] = []
        for file_id, rec in self.files.items():
            if rec.get("trashed") or rec.get("parent_id") != folder_id:
                continue
            if mime_type and rec.get("mime_type") != mime_type:
                continue
            items.append(self._to_file(file_id, rec))
        return items

    def get_file(self, file_id: str) -> DriveFile:
        rec = self.files.get(file_id)
        if rec is None or rec.get("trashed"):
            raise DriveClientError(f"File not found: {file_id}")
        return self._to_file(file_id, rec)

    def download(self, file_id: str) -> bytes:
        rec = self.files.get(file_id)
        if rec is None or rec.get("trashed"):
            raise DriveClientError(f"File not found: {file_id}")
        return bytes(rec.get("data") or b"")

    def create_file(
        self, folder_id: str, name: str, data: bytes, mime_type: str
    ) -> DriveFile:
        file_id = self._next_id()
        self.files[file_id] = {
            "name": name,
            "parent_id": folder_id,
            "data": bytes(data),
            "mime_type": mime_type,
            "modified_time": f"{self._seq:04d}",
            "created_time": f"{self._seq:04d}",
            "trashed": False,
        }
        return self.get_file(file_id)

    def update_file(self, file_id: str, data: bytes, mime_type: str) -> DriveFile:
        rec = self.files.get(file_id)
        if rec is None or rec.get("trashed"):
            raise DriveClientError(f"File not found: {file_id}")
        self._seq += 1
        rec["data"] = bytes(data)
        rec["mime_type"] = mime_type
        rec["modified_time"] = f"{self._seq:04d}"
        return self.get_file(file_id)

    def rename(self, file_id: str, new_name: str) -> DriveFile:
        rec = self.files.get(file_id)
        if rec is None or rec.get("trashed"):
            raise DriveClientError(f"File not found: {file_id}")
        self._seq += 1
        rec["name"] = new_name
        rec["modified_time"] = f"{self._seq:04d}"
        return self.get_file(file_id)

    def create_folder(self, parent_id: str, name: str) -> DriveFile:
        return self.create_file(parent_id, name, b"", FOLDER_MIME)

    def _to_file(self, file_id: str, rec: dict[str, Any]) -> DriveFile:
        data = rec.get("data") or b""
        return DriveFile(
            id=file_id,
            name=str(rec.get("name") or ""),
            modified_time=str(rec.get("modified_time") or ""),
            size=len(data),
            parent_id=str(rec.get("parent_id") or ""),
            created_time=str(rec.get("created_time") or ""),
            is_folder=rec.get("mime_type") == FOLDER_MIME,
        )


_F = TypeVar("_F", bound=Callable[..., Any])


def _api_call(method: _F) -> _F:
    """Turn network / API failures into ``DriveClientError`` so pages can show a message."""

    @functools.wraps(method)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return method(*args, **kwargs)
        except DriveClientError:
            raise
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            if "CERTIFICATE_VERIFY_FAILED" in detail:
                detail += (
                    " — HTTPS is intercepted (antivirus, VPN or proxy) and its certificate "
                    "is not trusted by Python."
                )
            raise DriveClientError(f"Google Drive request failed. {detail}") from exc

    return wrapper  # type: ignore[return-value]


class GoogleDriveClient:
    """Drive API client using a refresh-token credential."""

    def __init__(self, service: Any) -> None:
        self._service = service

    @_api_call
    def list_children(self, folder_id: str, mime_type: Optional[str] = None) -> list[DriveFile]:
        query = f"'{folder_id}' in parents and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
        items: list[DriveFile] = []
        page_token: Optional[str] = None
        while True:
            response = (
                self._service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields=f"nextPageToken, files({_FILE_FIELDS})",
                    pageToken=page_token,
                    pageSize=200,
                )
                .execute()
            )
            for raw in response.get("files") or []:
                items.append(_file_from_api(raw, folder_id))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    @_api_call
    def get_file(self, file_id: str) -> DriveFile:
        raw = self._service.files().get(fileId=file_id, fields=_FILE_FIELDS).execute()
        return _file_from_api(raw, "")

    @_api_call
    def download(self, file_id: str) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        request = self._service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    @_api_call
    def create_file(
        self, folder_id: str, name: str, data: bytes, mime_type: str
    ) -> DriveFile:
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
        raw = (
            self._service.files()
            .create(
                body={"name": name, "parents": [folder_id]},
                media_body=media,
                fields=_FILE_FIELDS,
            )
            .execute()
        )
        return _file_from_api(raw, folder_id)

    @_api_call
    def update_file(self, file_id: str, data: bytes, mime_type: str) -> DriveFile:
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
        raw = (
            self._service.files()
            .update(fileId=file_id, media_body=media, fields=_FILE_FIELDS)
            .execute()
        )
        return _file_from_api(raw, "")

    @_api_call
    def rename(self, file_id: str, new_name: str) -> DriveFile:
        raw = (
            self._service.files()
            .update(fileId=file_id, body={"name": new_name}, fields=_FILE_FIELDS)
            .execute()
        )
        return _file_from_api(raw, "")

    @_api_call
    def create_folder(self, parent_id: str, name: str) -> DriveFile:
        raw = (
            self._service.files()
            .create(
                body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
                fields=_FILE_FIELDS,
            )
            .execute()
        )
        return _file_from_api(raw, parent_id)


def _file_from_api(raw: Mapping[str, Any], fallback_parent: str) -> DriveFile:
    parents = raw.get("parents") or []
    parent_id = str(parents[0]) if parents else fallback_parent
    try:
        size = int(raw.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    return DriveFile(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        modified_time=str(raw.get("modifiedTime") or ""),
        size=size,
        parent_id=parent_id,
        created_time=str(raw.get("createdTime") or ""),
        is_folder=raw.get("mimeType") == FOLDER_MIME,
    )


_CA_BUNDLE_PATH: Optional[str] = None


def windows_ca_bundle() -> Optional[str]:
    """PEM file with certifi roots plus the Windows certificate stores (Windows only).

    httplib2 ignores the Windows store, so HTTPS interception by antivirus, VPN or a
    proxy fails certificate checks unless its root comes from Windows.
    """
    global _CA_BUNDLE_PATH
    if sys.platform != "win32":
        return None
    if _CA_BUNDLE_PATH and os.path.exists(_CA_BUNDLE_PATH):
        return _CA_BUNDLE_PATH
    import ssl

    parts: list[str] = []
    try:
        import certifi

        with open(certifi.where(), encoding="utf-8") as handle:
            parts.append(handle.read())
    except Exception:
        pass
    for store in ("ROOT", "CA"):
        try:
            certificates = ssl.enum_certificates(store)  # type: ignore[attr-defined]
        except Exception:
            continue
        for cert, encoding, _trust in certificates:
            if encoding == "x509_asn":
                parts.append(ssl.DER_cert_to_PEM_cert(cert))
    if not parts:
        return None
    path = os.path.join(tempfile.gettempdir(), "pba_ca_bundle.pem")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(parts))
    _CA_BUNDLE_PATH = path
    return path


def build_google_client(config: DriveConfig) -> GoogleDriveClient:
    """Build a live Drive client. Raises DriveClientError if libraries or tokens fail."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise DriveClientError(
            "Google Drive libraries are not installed. "
            "Add google-api-python-client and google-auth-oauthlib."
        ) from exc
    creds = Credentials(
        token=None,
        refresh_token=config.refresh_token,
        token_uri=config.token_uri,
        client_id=config.client_id,
        client_secret=config.client_secret,
        scopes=list(config.scopes),
    )
    try:
        creds.refresh(Request())
        bundle = windows_ca_bundle()
        if bundle:
            import httplib2
            from google_auth_httplib2 import AuthorizedHttp

            http = AuthorizedHttp(creds, http=httplib2.Http(ca_certs=bundle, timeout=120))
            service = build("drive", "v3", http=http, cache_discovery=False)
        else:
            service = build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        raise DriveClientError(f"Could not connect to Google Drive: {exc}") from exc
    return GoogleDriveClient(service)


def open_drive_store(config: DriveConfig) -> DriveStore:
    return DriveStore(config, build_google_client(config))
