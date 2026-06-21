"""Tests for lgwks_transcript — the Claude Code JSONL parser that feeds the
cortex/training corpus.

Regression guard for the extraction-quality fix: before it, the parser dropped
thinking/tool_use/tool_result blocks (96% of turns came out empty), mislabelled
every user turn as `unknown` (56% of turns), and ingested transcript metadata
lines as empty turns.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgwks_transcript as T


def _write(lines: list[dict]) -> str:
    fd = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    for d in lines:
        fd.write(json.dumps(d) + "\n")
    fd.close()
    return fd.name


# A realistic slice of a Claude Code transcript: real turns interleaved with
# the metadata bookkeeping lines the harness writes.
_FIXTURE = [
    {"type": "mode", "mode": "default"},                       # metadata
    {"type": "user", "uuid": "u1",
     "message": {"role": "user", "content": "fix lgwks_daemon.py"}},
    {"type": "ai-title", "title": "session"},                  # metadata
    {"type": "assistant", "uuid": "a1", "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "I should read the file first."},
        {"type": "text", "text": "Reading the daemon."},
        {"type": "tool_use", "name": "Read", "input": {"file_path": "lgwks_daemon.py"}},
    ]}},
    {"type": "user", "uuid": "u2", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "file contents here"},
    ]}},
    {"type": "pr-link", "url": "http://x"},                    # metadata
]


class TestTranscriptExtraction(unittest.TestCase):
    def setUp(self):
        self.path = _write(_FIXTURE)

    def test_metadata_lines_are_not_turns(self):
        turns = T.tail(self.path, n=0)
        # 3 real turns (user, assistant, tool_result-user); 3 metadata dropped.
        self.assertEqual(len(turns), 3)

    def test_roles_are_labelled_not_unknown(self):
        turns = T.tail(self.path, n=0)
        roles = [t["role"] for t in turns]
        self.assertNotIn("unknown", roles)
        self.assertEqual(roles, ["human", "assistant", "tool_result"])

    def test_thinking_and_tool_use_are_captured(self):
        turns = T.tail(self.path, n=0, include_content=True)
        asst = next(t for t in turns if t["role"] == "assistant")
        self.assertIn("I should read the file first.", asst["content"])  # thinking
        self.assertIn("[tool_use Read]", asst["content"])                # tool_use
        self.assertIn("lgwks_daemon.py", asst["content"])                # tool args

    def test_tool_result_content_is_captured(self):
        turns = T.tail(self.path, n=0, include_content=True)
        tr = next(t for t in turns if t["role"] == "tool_result")
        self.assertIn("file contents here", tr["content"])

    def test_human_message_content_preserved(self):
        turns = T.tail(self.path, n=0, include_content=True)
        human = next(t for t in turns if t["role"] == "human")
        self.assertEqual(human["content"], "fix lgwks_daemon.py")

    def test_content_len_reflects_extracted_text(self):
        turns = T.tail(self.path, n=0, include_content=True)
        asst = next(t for t in turns if t["role"] == "assistant")
        self.assertEqual(asst["content_len"], len(asst["content"].encode("utf-8")))
        self.assertGreater(asst["content_len"], 0)


if __name__ == "__main__":
    unittest.main()
