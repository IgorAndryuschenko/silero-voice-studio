import unittest
import numpy as np
from speech_engine import Options, process_audio, render_ssml, split_text


class AudioTests(unittest.TestCase):
    def test_trim_preserves_internal_pause_and_padding(self):
        audio = np.r_[np.zeros(500), np.full(100, .1), np.zeros(200), np.full(100, .1), np.zeros(500)]
        result = process_audio(audio, 1000, Options(padding_ms=100, fade_ms=0))
        self.assertEqual(len(result), 600)
        np.testing.assert_array_equal(result[200:400], np.zeros(200))
        self.assertEqual(np.count_nonzero(result), 200)

    def test_silence_is_not_amplified_or_deleted(self):
        result = process_audio(np.zeros(100), 1000, Options(normalize=True))
        np.testing.assert_array_equal(result, np.zeros(100))

    def test_fades_and_peak_normalization(self):
        result = process_audio(np.full(1000, .1), 1000, Options(trim=False, normalize=True, fade_ms=5))
        self.assertEqual(result[0], 0)
        self.assertEqual(result[-1], 0)
        self.assertAlmostEqual(float(np.max(result)), 10 ** (-1 / 20), places=5)

    def test_disabled_processing_preserves_signal(self):
        audio = np.linspace(-.5, .5, 100, dtype=np.float32)
        np.testing.assert_array_equal(process_audio(audio, 48000, Options(trim=False, fade_ms=0)), audio)

    def test_ssml_escapes_input(self):
        text = 'А <break/> & Б'
        self.assertIn('А &lt;break/&gt; &amp; Б', render_ssml(text, Options()))
        self.assertEqual(text, 'А <break/> & Б')

    def test_chunking_preserves_words(self):
        text = ('Первое предложение. Второе предложение! ' * 100).strip()
        chunks = split_text(text)
        self.assertTrue(all(len(c) <= 500 for c in chunks))
        self.assertEqual(' '.join(chunks).split(), text.split())


if __name__ == '__main__':
    unittest.main()
