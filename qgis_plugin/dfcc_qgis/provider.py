from qgis.core import QgsProcessingProvider
from .algorithm import DfccAlgorithm


class DfccProvider(QgsProcessingProvider):
    def id(self):
        return "dfcc"

    def name(self):
        return "DFCC - Debris Flow"

    def longName(self):
        return "DFCC - Debris-Flow Channel Classification"

    def loadAlgorithms(self):
        self.addAlgorithm(DfccAlgorithm())
