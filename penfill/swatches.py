"""Colour swatches for vsketch choice dropdowns.

vsketch's GUI hardcodes its parameter widgets with no extension hook, so this
monkey-patches ``vsketch_cli.param_widget.ChoiceParamWidget`` to prefix each
combo-box item with a colour swatch whenever the choice resolves to a colour — a
known pen name (via the registry passed to :func:`install`) or a literal
``#rgb`` / ``#rrggbb`` string. Other dropdowns are left untouched.

Call :func:`install` once before the GUI is built; importing it from a sketch
module does that, since the sketch is imported before ``vsk run`` constructs the
widgets. It is GUI-only and best-effort: if PySide6 / vsketch_cli are missing
(e.g. headless export) it silently no-ops. This is the one place that reaches
into vsketch internals — the patched surface is deliberately tiny.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, Optional

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

_COLORS: Dict[str, str] = {}                  # choice value -> colour
_RESOLVER: Optional[Callable[[object], Optional[str]]] = None
_installed = False


def _resolve(value) -> Optional[str]:
    if _RESOLVER is not None:
        c = _RESOLVER(value)
        if c:
            return c
    if value in _COLORS:
        return _COLORS[value]
    if isinstance(value, str) and _HEX_RE.match(value):
        return value
    return None


def install(colors: Optional[Dict[str, str]] = None,
            resolver: Optional[Callable[[object], Optional[str]]] = None,
            size: int = 16) -> bool:
    """Show colour swatches on choice dropdowns. Returns True if the patch is active.

    ``colors`` maps a choice value to a colour; ``resolver`` is an optional
    fallback mapping a choice value to a colour string. Both ``#rrggbb`` and CSS
    colour names are accepted. The registry is additive across calls and the
    patch itself is applied only once.
    """
    global _installed, _RESOLVER
    if colors:
        _COLORS.update(colors)
    if resolver is not None:
        _RESOLVER = resolver
    if _installed:
        return True

    try:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
        from vsketch_cli import param_widget
    except Exception:
        return False

    icon_cache: Dict[str, "QIcon"] = {}

    def swatch(color: str):
        ic = icon_cache.get(color)
        if ic is None:
            qc = QColor(color)
            if not qc.isValid():
                return None
            pm = QPixmap(size, size)
            pm.fill(qc)
            p = QPainter(pm)
            p.setPen(QColor("#808080"))           # border so light colours show
            p.drawRect(0, 0, size - 1, size - 1)
            p.end()
            ic = QIcon(pm)
            icon_cache[color] = ic
        return ic

    widget_cls = param_widget.ChoiceParamWidget
    orig_init = widget_cls.__init__

    def patched_init(self, param, *args, **kwargs):
        orig_init(self, param, *args, **kwargs)
        self.setIconSize(QSize(size, size))
        for i in range(self.count()):
            val = self.itemData(i)
            if val is None:
                val = self.itemText(i)
            color = _resolve(val)
            if color:
                ic = swatch(color)
                if ic is not None:
                    self.setItemIcon(i, ic)

    widget_cls.__init__ = patched_init
    _installed = True
    return True
