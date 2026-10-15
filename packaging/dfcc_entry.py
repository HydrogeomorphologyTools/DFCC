"""PyInstaller entry point: `dfcc.exe` = GUI when run without arguments, CLI otherwise
(dfcc.exe run dtm.tif -o out --runout | dfcc.exe fill ... | dfcc.exe --version)."""
import os
import sys
import multiprocessing

if getattr(sys, "frozen", False):
    # numba cache must live outside the read-only/temporary bundle
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(base, "DFCC", "numba_cache"))
    os.makedirs(os.environ["NUMBA_CACHE_DIR"], exist_ok=True)
    import faulthandler
    _crash = open(os.path.join(os.environ["NUMBA_CACHE_DIR"], "..", "crash.log"), "a")   # native crashes -> %LOCALAPPDATA%\DFCC\crash.log
    faulthandler.enable(file=_crash, all_threads=True)
    if sys.stdout is None:                      # windowed build: no console attached
        sys.stdout = sys.stderr = open(os.devnull, "w")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from dfcc.cli import main
    sys.exit(main())
