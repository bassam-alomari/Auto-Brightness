import unittest
from unittest.mock import Mock

from room_brightness.brightness import verify_control, set_checked


class VerificationTests(unittest.TestCase):
    def test_success_restores_original(self):
        hardware = Mock(side_effect=[40, 45, 40])
        self.assertEqual(verify_control(hardware), 40)
        self.assertEqual([call.args for call in hardware.call_args_list], [(), (45,), (40,)])

    def test_failed_readback_still_restores(self):
        hardware = Mock(side_effect=[40, 40, 40])
        with self.assertRaisesRegex(RuntimeError, "readback"):
            verify_control(hardware)
        self.assertEqual(hardware.call_args_list[-1].args, (40,))

    def test_write_exception_still_restores(self):
        hardware = Mock(side_effect=[40, RuntimeError("driver failed"), 40])
        with self.assertRaisesRegex(RuntimeError, "driver failed"):
            verify_control(hardware)
        self.assertEqual(hardware.call_args_list[-1].args, (40,))

    def test_restoration_failure_is_reported(self):
        hardware = Mock(side_effect=[40, 45, 70])
        with self.assertRaisesRegex(RuntimeError, "Restore brightness manually"):
            verify_control(hardware)

    def test_full_brightness_tests_downward(self):
        hardware = Mock(side_effect=[100, 95, 100])
        self.assertEqual(verify_control(hardware), 100)
        self.assertEqual(hardware.call_args_list[1].args, (95,))

    def test_zero_original_brightness_can_be_verified_and_restored(self):
        hardware = Mock(side_effect=[0, 5, 0])
        self.assertEqual(verify_control(hardware), 0)
        self.assertEqual(hardware.call_args_list[-1].args, (0,))

    def test_setter_rejects_unconfirmed_change(self):
        with self.assertRaises(RuntimeError):
            set_checked(60, Mock(return_value=40))

    def test_one_percent_old_value_is_not_success(self):
        with self.assertRaises(RuntimeError):
            set_checked(41, Mock(return_value=40))
