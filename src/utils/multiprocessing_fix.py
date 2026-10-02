"""
Fix for Python multiprocessing with Textual / custom TUI applications.

Textual redirects sys.stderr to a print-capture object whose .fileno() returns -1.
In Python multiprocessing on POSIX systems, resource_tracker and spawn implementations
attempt to pass sys.stderr.fileno() to child processes via multiprocessing.util.spawnv_passfds.
Because -1 is an invalid file descriptor, _posixsubprocess.fork_exec raises:
    ValueError: bad value(s) in fds_to_keep

This module patches multiprocessing.util.spawnv_passfds to sanitize the file descriptors,
filtering out any negative or invalid values so child processes spawn cleanly.
"""

import multiprocessing.util as mp_util
from utils.logger import get_logger

logger = get_logger(__name__)


def apply_multiprocessing_fix() -> None:
    """Sanitize passfds in multiprocessing.util.spawnv_passfds to ignore invalid FDs."""
    if hasattr(mp_util, "spawnv_passfds") and not getattr(mp_util.spawnv_passfds, "_is_rezen_patched", False):
        orig_spawnv_passfds = mp_util.spawnv_passfds

        def _safe_spawnv_passfds(path, args, passfds):
            clean_fds = [fd for fd in passfds if fd is not None and fd >= 0]
            return orig_spawnv_passfds(path, args, clean_fds)

        _safe_spawnv_passfds._is_rezen_patched = True
        mp_util.spawnv_passfds = _safe_spawnv_passfds
        logger.debug("Applied multiprocessing spawnv_passfds fix.")
