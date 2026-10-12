import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows byte locks")
class InstanceLockTests(unittest.TestCase):
    def test_second_instance_detects_lock_without_reading_locked_byte(self):
        import msvcrt

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "instance.lock"
            code = "import msvcrt,sys; f=open(sys.argv[1],'a+b'); f.write(b'0'); f.flush(); f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1); print('READY',flush=True); sys.stdin.readline()"
            child = subprocess.Popen(
                [sys.executable, "-c", code, str(path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "READY")
                with path.open("a+b") as instance:
                    instance.seek(0, 2)
                    self.assertGreater(instance.tell(), 0)
                    instance.seek(0)
                    with self.assertRaises(OSError):
                        msvcrt.locking(instance.fileno(), msvcrt.LK_NBLCK, 1)
            finally:
                child.stdin.write("exit\n")
                child.stdin.flush()
                child.wait(timeout=5)
                child.stdin.close()
                child.stdout.close()
