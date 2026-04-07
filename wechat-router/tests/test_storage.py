"""Tests for StorageManager."""

import os
import tempfile
import unittest

from src.storage import StorageManager


class TestStorageManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.storage = StorageManager(self.db_path)

    def tearDown(self):
        self.storage.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_contact(self):
        cid = self.storage.get_or_create_contact("张三", "contact")
        self.assertIsNotNone(cid)
        cid2 = self.storage.get_or_create_contact("张三", "contact")
        self.assertEqual(cid, cid2)

    def test_insert_message(self):
        mid = self.storage.insert_message(
            contact_name="张三",
            contact_type="contact",
            sender=None,
            content_type="text",
            text_content="Hello world",
            timestamp_ocr="14:30",
        )
        self.assertIsNotNone(mid)

    def test_deduplication(self):
        kwargs = dict(
            contact_name="张三",
            contact_type="contact",
            sender=None,
            content_type="text",
            text_content="Same message",
            timestamp_ocr="14:30",
        )
        mid1 = self.storage.insert_message(**kwargs)
        mid2 = self.storage.insert_message(**kwargs)
        self.assertIsNotNone(mid1)
        self.assertIsNone(mid2)

    def test_different_messages_not_deduped(self):
        mid1 = self.storage.insert_message(
            contact_name="张三", contact_type="contact",
            sender=None, content_type="text",
            text_content="Message A", timestamp_ocr="14:30",
        )
        mid2 = self.storage.insert_message(
            contact_name="张三", contact_type="contact",
            sender=None, content_type="text",
            text_content="Message B", timestamp_ocr="14:31",
        )
        self.assertIsNotNone(mid1)
        self.assertIsNotNone(mid2)
        self.assertNotEqual(mid1, mid2)

    def test_insert_attachment(self):
        mid = self.storage.insert_message(
            contact_name="工作群", contact_type="group",
            sender="李四", content_type="image",
        )
        aid = self.storage.insert_attachment(mid, "image", "/path/to/img.png", "img.png")
        self.assertIsNotNone(aid)

    def test_get_messages(self):
        self.storage.insert_message(
            contact_name="张三", contact_type="contact",
            sender=None, content_type="text",
            text_content="Hello", timestamp_ocr="14:30",
        )
        msgs = self.storage.get_messages("张三", limit=10)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["text_content"], "Hello")

    def test_get_messages_all(self):
        self.storage.insert_message(
            contact_name="张三", contact_type="contact",
            sender=None, content_type="text",
            text_content="Msg 1", timestamp_ocr="14:30",
        )
        self.storage.insert_message(
            contact_name="工作群", contact_type="group",
            sender="李四", content_type="text",
            text_content="Msg 2", timestamp_ocr="14:31",
        )
        msgs = self.storage.get_messages(limit=50)
        self.assertEqual(len(msgs), 2)

    def test_recent_hashes(self):
        self.storage.insert_message(
            contact_name="张三", contact_type="contact",
            sender=None, content_type="text",
            text_content="Test", timestamp_ocr="14:30",
        )
        hashes = self.storage.get_recent_hashes("张三")
        self.assertEqual(len(hashes), 1)


if __name__ == "__main__":
    unittest.main()
