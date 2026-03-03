"""Compatibility facade for API views.

This module keeps the historic `api.views` import path stable while the
implementation is split into domain-focused modules.
"""

from __future__ import annotations

import sys
import types

from . import view_applications as _view_applications
from . import view_auth_catalog as _view_auth_catalog
from . import view_billing as _view_billing
from . import view_notifications as _view_notifications
from . import views_shared as _views_shared
from .view_applications import *  # noqa: F401,F403
from .view_auth_catalog import *  # noqa: F401,F403
from .view_billing import *  # noqa: F401,F403
from .view_notifications import *  # noqa: F401,F403
from .views_shared import *  # noqa: F401,F403
from .views_shared import _get_enqueue_guard_token, _latest_inflight_job, _observe_async_guard_event  # noqa: F401

_PATCH_TARGET_MODULES = (
    _views_shared,
    _view_auth_catalog,
    _view_billing,
    _view_applications,
    _view_notifications,
)


class _ViewsCompatModule(types.ModuleType):
    """Propagate monkeypatches on `api.views` to split modules."""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for module in _PATCH_TARGET_MODULES:
            if hasattr(module, name):
                setattr(module, name, value)


sys.modules[__name__].__class__ = _ViewsCompatModule
