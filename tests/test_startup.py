import unittest
from unittest.mock import patch, MagicMock
from room_brightness import startup


class StartupTests(unittest.TestCase):
    @patch("winreg.SetValueEx")
    @patch("winreg.CreateKey")
    def test_enable_writes_only_our_current_user_value(self, create, write):
        create.return_value = MagicMock()
        startup.set_enabled(True)
        self.assertEqual(create.call_args.args[1], startup.KEY)
        self.assertEqual(write.call_args.args[1], startup.NAME)
        self.assertIn("--autostart", write.call_args.args[4])

    @patch("winreg.DeleteValue")
    @patch("winreg.CreateKey")
    def test_disable_removes_only_our_value(self, create, delete):
        create.return_value = MagicMock()
        startup.set_enabled(False)
        self.assertEqual(delete.call_args.args[1], startup.NAME)
