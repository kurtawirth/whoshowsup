"""Keep the PC from sleeping for a while, then let it sleep on its own schedule again.

    pythonw scripts/stay_awake.py 75      # minutes

Used by the Windows task "Politics - newsletter wake", which wakes the PC Sunday mornings so the Claude app's
newsletter-draft task (9 a.m.) can run. Asks Windows to stay awake (the same request a video player makes) and
exits after the given minutes; the normal sleep timer takes over from there.
"""
import ctypes
import sys
import time

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001

minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 60
ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
try:
    time.sleep(minutes * 60)
finally:
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
