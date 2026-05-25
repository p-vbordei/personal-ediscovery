"""Tests for the new rich source adapters."""

from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

from personal_ediscovery.adapters import (
    FsDocAdapter,
    MailAdapter,
    PhotosExifAdapter,
    SignalExportAdapter,
    WhatsAppTextAdapter,
)

def test_fsdoc_adapter_discovery_skips_unsupported(tmp_path: Path) -> None:
    (tmp_path / "doc.txt").write_text("Hello")
    items = list(FsDocAdapter().discover(tmp_path))
    assert len(items) == 0  # .txt is not in FsDocAdapter.EXTENSIONS

def test_mail_adapter_eml(tmp_path: Path) -> None:
    # Construct a simple EML file
    msg = EmailMessage()
    msg.set_content("This is the email body.\nWith multiple lines.")
    msg["Subject"] = "Test Subject"
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    
    eml_path = tmp_path / "test.eml"
    with open(eml_path, "wb") as f:
        f.write(bytes(msg))

    items = list(MailAdapter().discover(tmp_path))
    assert len(items) == 1
    assert items[0].title == "Test Subject"
    assert "email body" in items[0].body
    assert items[0].meta["from"] == "alice@example.com"
    assert items[0].meta["to"] == "bob@example.com"

def test_signal_adapter(tmp_path: Path) -> None:
    # Construct a mock Signal export JSON
    data = [
        {
            "name": "Family Group",
            "messages": [
                {"body": "Hello family!", "timestamp": 123456789, "source": "Alice"},
                {"body": "Hi Alice", "timestamp": 123456790, "source": "Bob"},
            ]
        }
    ]
    (tmp_path / "signal.json").write_text(json.dumps(data))

    items = list(SignalExportAdapter().discover(tmp_path))
    assert len(items) == 2
    assert items[0].title == "Family Group"
    assert items[0].body == "Hello family!"
    assert items[0].meta["sender"] == "Alice"
    assert items[1].body == "Hi Alice"

def test_whatsapp_adapter(tmp_path: Path) -> None:
    # Construct a mock WhatsApp export text
    chat = (
        "1/15/26, 10:30 AM - Alice: Are we still meeting today?\n"
        "1/15/26, 10:31 AM - Bob: Yes, see you at 2.\n"
        "This is a continuation of Bob's message.\n"
        "1/15/26, 10:35 AM - System: Alice left the group.\n" # No colon after sender if system, but regex expects it
    )
    (tmp_path / "chat.txt").write_text(chat)

    items = list(WhatsAppTextAdapter().discover(tmp_path))
    # Alice's message
    assert len(items) == 3
    assert items[0].title == "WhatsApp chat with Alice"
    assert items[0].body == "Are we still meeting today?"
    
    # Bob's message
    assert items[1].title == "WhatsApp chat with Bob"
    assert "Yes, see you at 2." in items[1].body
    assert "continuation" in items[1].body

def test_photos_adapter_skips_unsupported(tmp_path: Path) -> None:
    (tmp_path / "img.bmp").write_bytes(b"fake bmp")
    items = list(PhotosExifAdapter().discover(tmp_path))
    assert len(items) == 0
