"""Companion engine log (Bugs S.No 146, second pass).

Until this existed the companion wrote **no log file at all**. The only record of an engine
failure was whatever was still on screen in the operator's terminal — which is why, of nine
"AI engine exited with an error" builds across two tenants, eight were unrecoverable by the time
anyone asked. The one that could be diagnosed was diagnosed because the QA member happened to
still have the window open.

What lands here that nowhere else keeps:

* The Claude Code CLI's **stdout diagnostics**. They arrive as non-JSON lines and the SDK drops
  them at ``logger.debug`` ("Skipping non-JSON line from CLI stdout"). Nothing in the companion
  configured logging, so the root logger had no handlers and ``logging.lastResort`` is
  WARNING-level — those records went nowhere. The usage-limit notice is one of them.
* ``query.py``'s ``logger.error("Fatal error in message reader: …")`` — visible in the terminal
  via ``lastResort``, but never written down.

Attached to the ``claude_agent_sdk`` logger rather than the root logger so the file stays
readable: root-at-DEBUG would bury the engine's own words under asyncio/urllib3 chatter. The
driver's per-run capture (``ClaudeDriver._capturing_sdk_log``) adds its own handler to the same
logger and sets ``propagate = False`` while it holds it — that only stops records reaching
*ancestor* loggers, so a handler attached here still receives everything.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_SDK_LOGGER_NAME = "claude_agent_sdk"
LOG_FILENAME = "companion-engine.log"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUPS = 3
_HANDLER_TAG = "sdlc-companion-engine-log"


def default_log_path(worktrees_root=None) -> Path:
    """Beside the worktrees when the operator named one (that directory is already theirs and
    already excluded from any repo), else a dot-directory under the current working directory."""
    base = Path(worktrees_root) if worktrees_root else Path.cwd() / ".sdlc-companion"
    return base / LOG_FILENAME


def setup_engine_log(worktrees_root=None, *, path=None) -> Path | None:
    """Start writing the engine's own output to a rotating file. Returns the path, or None if the
    log could not be opened.

    Idempotent — serving twice in one process does not double-write. **Never fatal**: a companion
    that cannot open its log must still run builds, so an unwritable directory degrades to no
    logging rather than a dead runner.
    """
    target = Path(path) if path else default_log_path(worktrees_root)
    logger = logging.getLogger(_SDK_LOGGER_NAME)
    for existing in logger.handlers:
        if getattr(existing, "_sdlc_tag", "") == _HANDLER_TAG:
            return Path(getattr(existing, "baseFilename", target))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            target, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8")
    except OSError:
        return None
    handler._sdlc_tag = _HANDLER_TAG            # type: ignore[attr-defined]
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    # Only lower the level, never raise it — an operator who set SDLC_ENGINE_LOG_LEVEL or
    # configured logging themselves keeps what they chose.
    if logger.level == logging.NOTSET or logger.level > logging.DEBUG:
        logger.setLevel(logging.DEBUG)
    return target
