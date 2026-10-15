def classFactory(iface):
    from .plugin import DfccPlugin
    return DfccPlugin(iface)
