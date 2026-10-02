from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.elevenlabs_client import ElevenLabsClient
from core.subtitles import alignment_to_srt, clean_narration


class SubtitleTests(unittest.TestCase):
    def test_clean_narration_removes_markdown_and_sources(self):
        source = "**Hook:** Koty były święte. [1]\n\n**Finał:** To koniec.\n---\n*Uwagi do źródeł*"
        self.assertEqual(clean_narration(source), "Koty były święte. To koniec.")

    def test_alignment_creates_srt(self):
        text = "To jest test. Drugi napis."
        alignment = {
            "characters": list(text),
            "character_start_times_seconds": [index * 0.05 for index in range(len(text))],
            "character_end_times_seconds": [(index + 1) * 0.05 for index in range(len(text))],
        }
        with TemporaryDirectory() as temp:
            output = alignment_to_srt(alignment, Path(temp) / "narration.srt", words_per_caption=3)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("-->", rendered)
            self.assertIn("To jest test.", rendered)
            self.assertIn("Drugi napis.", rendered)

    def test_elevenlabs_requires_key_before_network(self):
        with self.assertRaisesRegex(RuntimeError, "ELEVENLABS_API_KEY"):
            ElevenLabsClient("").voices()


if __name__ == "__main__":
    unittest.main()
