"""Stand-ins for the platform's project and settings type constants."""


class ProjectType:
    LMS = "lms.djangoapp"
    CMS = "cms.djangoapp"


class SettingsType:
    COMMON = "common"
    PRODUCTION = "production"
    DEVSTACK = "devstack"
