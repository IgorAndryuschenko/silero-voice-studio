import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bootstrap


class DownloadTests(unittest.TestCase):
    def test_existing_model_needs_no_network(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / 'model.pt'
            model.write_bytes(b'known model')
            expected = hashlib.sha256(model.read_bytes()).hexdigest()
            with patch.object(bootstrap, 'MODEL_SHA256', expected), patch.object(bootstrap.urllib.request, 'urlopen') as network:
                bootstrap.ensure_model(model)
                network.assert_not_called()

    def test_legacy_copy_keeps_original(self):
        with tempfile.TemporaryDirectory() as temp:
            legacy, target = Path(temp) / 'old.pt', Path(temp) / 'new.pt'
            legacy.write_bytes(b'known model')
            with patch.object(bootstrap, 'MODEL_SHA256', hashlib.sha256(b'known model').hexdigest()):
                bootstrap.ensure_model(target, legacy)
            self.assertEqual(target.read_bytes(), b'known model')
            self.assertEqual(legacy.read_bytes(), b'known model')

    def test_incomplete_download_does_not_replace_existing_model(self):
        import io
        class Response(io.BytesIO):
            headers = {'Content-Length': '100'}
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'model.pt'
            target.write_bytes(b'old file')
            with patch.object(bootstrap.urllib.request, 'urlopen', return_value=Response(b'partial')):
                with self.assertRaisesRegex(RuntimeError, 'SHA-256 mismatch'):
                    bootstrap.ensure_model(target, Path(temp) / 'absent.pt')
            self.assertEqual(target.read_bytes(), b'old file')
            self.assertFalse(target.with_suffix('.pt.part').exists())

    def test_verified_download_replaces_bad_file(self):
        import io
        class Response(io.BytesIO):
            headers = {'Content-Length': '10'}
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'model.pt'
            target.write_bytes(b'bad')
            payload = b'known file'
            with patch.object(bootstrap, 'MODEL_SHA256', hashlib.sha256(payload).hexdigest()), patch.object(bootstrap.urllib.request, 'urlopen', return_value=Response(payload)):
                bootstrap.ensure_model(target, Path(temp) / 'absent.pt')
            self.assertEqual(target.read_bytes(), payload)


if __name__ == '__main__':
    unittest.main()
