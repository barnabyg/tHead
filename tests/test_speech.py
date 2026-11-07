"""Public text segmentation contract; native voice is exercised on Windows separately."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from speech import segments  # noqa: E402


class SpeechTests(unittest.TestCase):
    def test_bounded_phrases_preserve_every_word_and_final_partial(self) -> None:
        text = "Hello, world! This is a second sentence. Last words without punctuation"
        parts = segments(text)
        self.assertEqual(
            parts, ["Hello, world!", "This is a second sentence.", "Last words without punctuation"]
        )
        long = " ".join(["boundary"] * 120)
        chunks = segments(long)
        self.assertEqual(" ".join(chunks), long)
        self.assertTrue(all(len(part) <= 180 for part in chunks))
        self.assertEqual(segments("Hi"), ["Hi"])
        for invalid in ("", " \n ", "a" * 1201):
            with self.assertRaises(ValueError):
                segments(invalid)


if __name__ == "__main__":
    unittest.main()
