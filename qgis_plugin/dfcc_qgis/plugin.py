import os
import sys
from qgis.core import QgsApplication
from .provider import DfccProvider


def _ensure_path():
    """Allow running from a source checkout:  <repo>/src is added when the package is not installed."""
    try:
        import dfcc  # noqa: F401
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        for up in (os.path.join(here, "..", "..", "src"), os.path.join(here, "src")):
            if os.path.isdir(os.path.join(up, "dfcc")):
                sys.path.insert(0, os.path.abspath(up))
                break


class DfccPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initGui(self):
        _ensure_path()
        self.provider = DfccProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
