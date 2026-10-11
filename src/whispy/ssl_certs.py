"""Point SSL at certifi's CA bundle when the inherited one is missing.

Inside the .app bundle the interpreter has no system CA file, and py2app's
``__boot__`` sets ``SSL_CERT_FILE``/``SSL_CERT_DIR`` to a path that does not
exist (``openssl.ca/no-such-file``). httpx honors those variables, so every
HTTPS request — e.g. the first-run HuggingFace model download — raised a bare
``FileNotFoundError: [Errno 2]`` and the model never loaded. A plain
``setdefault`` is not enough: the variables are already set, just wrong.
"""

import os
from collections.abc import MutableMapping


def use_certifi_if_missing(environ: MutableMapping[str, str] = os.environ) -> None:
    """Replace unset or dangling SSL_CERT_FILE/SSL_CERT_DIR with certifi's bundle.

    A value that points at an existing path is a deliberate user choice (a
    corporate proxy CA, say) and is left alone.
    """
    try:
        import certifi
    except ImportError:  # pragma: no cover - certifi absent on a minimal host
        return

    cafile = certifi.where()
    targets = {"SSL_CERT_FILE": cafile, "SSL_CERT_DIR": os.path.dirname(cafile)}
    for key, value in targets.items():
        current = environ.get(key)
        if not current or not os.path.exists(current):
            environ[key] = value
