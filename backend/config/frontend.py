from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@never_cache
@require_safe
def console(request, device_id=None):
    """Serve the public login shell; data access stays behind the session APIs."""
    try:
        index = (settings.FRONTEND_DIST / "index.html").open("rb")
    except FileNotFoundError:
        raise Http404("Console assets are not built.") from None
    return FileResponse(index, content_type="text/html; charset=utf-8")
