import unittest
import os
import base64
from pathlib import Path
import lgwks_inline

class TestInline(unittest.TestCase):
    def test_literal(self):
        self.assertEqual(lgwks_inline.resolve_payload("hello"), "hello")
        
    def test_escape(self):
        self.assertEqual(lgwks_inline.resolve_payload(r"\@hello"), "@hello")
        
    def test_text_file(self):
        p = Path("test_text.txt")
        p.write_text("file content", encoding="utf-8")
        try:
            self.assertEqual(lgwks_inline.resolve_payload("@test_text.txt"), "file content")
        finally:
            if p.exists(): p.unlink()
            
    def test_binary_file(self):
        p = Path("test_bin.bin")
        data = b"\x00\x01\x02\x03"
        p.write_bytes(data)
        try:
            result = lgwks_inline.resolve_payload("@test_bin.bin")
            self.assertTrue(result.startswith("data:application/octet-stream;base64,"))
            b64 = result.split(",")[1]
            self.assertEqual(base64.b64decode(b64), data)
        finally:
            if p.exists(): p.unlink()
            
    def test_data_uri(self):
        uri = "data:text/plain;base64,aGVsbG8="
        self.assertEqual(lgwks_inline.resolve_payload("@" + uri), uri)

    def test_precedence(self):
        self.assertEqual(lgwks_inline.get_precedence_payload(expr="expr"), "expr")
        # create temp file
        p = Path("test_precedence.txt")
        p.write_text("file_val")
        try:
            self.assertEqual(lgwks_inline.get_precedence_payload(file_at="test_precedence.txt"), "file_val")
            self.assertEqual(lgwks_inline.get_precedence_payload(expr="expr", file_at="test_precedence.txt"), "expr")
            self.assertEqual(lgwks_inline.get_precedence_payload(stdin_text="stdin_val"), "stdin_text" if False else "stdin_val")
        finally:
            if p.exists(): p.unlink()

if __name__ == "__main__":
    unittest.main()
