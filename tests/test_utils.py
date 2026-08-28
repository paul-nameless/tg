import os
import tempfile
import unittest
from unittest.mock import patch

from tg import config, utils


class MailcapTest(unittest.TestCase):
    def test_custom_mailcap_file_selects_configured_handler(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as mailcap_file:
            mailcap_file.write('video/*; vlc "%s"\n')
            path = mailcap_file.name

        try:
            with patch.object(config, "MAILCAP_FILE", path):
                self.assertEqual(
                    utils.get_file_handler("/tmp/video.mp4"),
                    'vlc "/tmp/video.mp4"',
                )
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
