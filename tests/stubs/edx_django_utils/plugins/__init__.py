"""
Minimal stand-ins for the platform's plugin constants.

These exist only so the real ``nelc/certification/apps.py`` imports cleanly
outside edx-platform. They carry the same attribute names the AppConfig reads,
so the real ``plugin_app`` dict is constructed verbatim during these checks; it
is simply never acted on, because nothing here is edx-platform.
"""


class PluginURLs:
    CONFIG = "url_config"
    NAMESPACE = "namespace"
    APP_NAME = "app_name"
    REGEX = "regex"
    RELATIVE_PATH = "relative_path"


class PluginSettings:
    CONFIG = "settings_config"
    RELATIVE_PATH = "relative_path"


class PluginSignals:
    CONFIG = "signals_config"
    RELATIVE_PATH = "relative_path"
    RECEIVERS = "receivers"
    RECEIVER_FUNC_NAME = "receiver_func_name"
    SIGNAL_PATH = "signal_path"
    SENDER_PATH = "sender_path"
