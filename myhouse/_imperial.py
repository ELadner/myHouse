# SPDX-License-Identifier: GPL-3.0-or-later
"""Lengths for the MyHouse dialogs, imperial or metric (shared code, not a
feature; the name is from when it was imperial only).

IngeTrazo stores every length in metres, and so does MyHouse. What changes is
what the user reads and types:

  - imperial: feet and inches, in fractions down to 1/16" (96, 8', 8'6 1/2",
    7 4 for 7'4"; a bare number is inches)
  - metric: the document's metric unit, or metres (2.4, 240cm, 2400mm)

Which one is the MyHouse units setting (Extensions > MyHouse > Units…):
"auto" follows the document's units, "imperial" and "metric" force one.

    from ._imperial import IN, FT, spin, fmt, parse, ask_length, dflt

spin(value, lo, hi) is a spin box whose value(), setValue() and range are all
METRES, like the plain QDoubleSpinBox it replaces; only its text follows the
units. fmt(metres) is the same text for a read-out. dflt(imperial, metric)
picks a default size (both in metres) for the units in use.
"""
from __future__ import annotations

import os
import re

from PySide6.QtCore import QSettings
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QVBoxLayout,
)

from core import units

IN = 0.0254          # one inch, in metres
FT = 0.3048          # one foot, in metres
FEET_FROM = 24 * IN  # shorter than this reads in inches, longer in feet-inches
_FRACTION = 2        # core.units precision: 2 = sixteenths of an inch
_FEET_INCHES = re.compile(r"^(\d+)\s+(\d+(?:\.\d+)?(?:\s+\d+/\d+)?)$")

SETTING = "myhouse/units"
MODES = ("auto", "imperial", "metric")
_METRIC = ("m", "cm", "mm")
_DECIMALS = {"m": 3, "cm": 1, "mm": 0}     # a millimetre, in each unit
_setting: str | None = None


def setting() -> str:
    """The saved choice: "auto", "imperial" or "metric"."""
    global _setting
    if _setting is None:        # MYHOUSE_UNITS overrides it (tests, scripts)
        value = str(os.environ.get("MYHOUSE_UNITS")
                    or QSettings().value(SETTING) or "auto")
        _setting = value if value in MODES else "auto"
    return _setting


def set_setting(value: str) -> None:
    global _setting
    _setting = value if value in MODES else "auto"
    QSettings().setValue(SETTING, _setting)


def imperial() -> bool:
    """Whether lengths are read and typed in feet and inches right now."""
    choice = setting()
    if choice == "auto":
        return units.model_unit() not in _METRIC
    return choice == "imperial"


def _metric_unit() -> str:
    unit = units.model_unit()
    return unit if unit in _METRIC else "m"


def dflt(imperial_value, metric_value):
    """A default for the units in use: both given in metres (or both any
    other kind of value, such as a size code)."""
    return imperial_value if imperial() else metric_value


def fmt(metres: float, feet: bool | None = None) -> str:
    """A length as text. Imperial: 2 1/2" or 8'6" (feet=True/False forces
    the form; None picks inches below two feet and feet-inches from there
    up). Metric: 2.400 m, in the document's metric unit."""
    if not imperial():
        unit = _metric_unit()
        return units.localized(
            units.format_length(float(metres), unit, _DECIMALS[unit]))
    if feet is None:
        feet = abs(metres) >= FEET_FROM - 1e-9
    return units.format_length(metres, "ft-in-frac" if feet else "in-frac",
                               _FRACTION)


def parse(text: str):
    """Metres from typed text; None if unreadable. A bare number is inches
    (imperial) or the document's metric unit; a unit can always be typed."""
    text = str(text).strip()
    if not imperial():
        value = units.parse(text, "length", unit=_metric_unit()).value
        if value is None and "," in text:          # 2,40 as well as 2.40
            value = units.parse(text.replace(",", "."), "length",
                                unit=_metric_unit()).value
        return value
    m = _FEET_INCHES.match(text)
    if m:                                # 7 2 or 7 2 1/2: feet, then inches
        text = f"{m.group(1)}'{m.group(2)}\""
    return units.parse(text, "length", unit="in").value


class ImperialSpin(QDoubleSpinBox):
    """A length in metres, shown and typed in the MyHouse units."""

    def __init__(self, metres=0.0, lo=0.0, hi=100.0, feet=None) -> None:
        super().__init__()
        self._feet = feet
        self.setDecimals(8)                # metres: exact to 1/64"
        self.setRange(lo, hi)
        self.setValue(metres)

    def textFromValue(self, value: float) -> str:
        return fmt(value, self._feet)

    def valueFromText(self, text: str) -> float:
        metres = parse(text)
        return self.value() if metres is None else metres

    def validate(self, text: str, pos: int):
        ok = parse(text) is not None
        return (QValidator.Acceptable if ok else QValidator.Intermediate,
                text, pos)

    def stepBy(self, steps: int) -> None:
        if imperial():                     # 1/8" on small sizes, 1" on big
            step = IN if abs(self.value()) >= FEET_FROM - 1e-9 else IN / 8
        else:                              # 1 mm on small sizes, 1 cm on big
            step = 0.01 if abs(self.value()) >= 0.5 - 1e-9 else 0.001
        self.setValue(self.value() + steps * step)

    def metres(self) -> float:
        return self.value()


def spin(value, lo, hi, feet=None):
    """Drop-in for a QDoubleSpinBox of metres: value, lo and hi in metres."""
    return ImperialSpin(value, lo, hi, feet)


def ask_length(parent, title: str, label: str, metres: float,
               lo: float = -1000.0, hi: float = 1000.0):
    """Like QInputDialog.getDouble for a length: (metres, ok)."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    form = QFormLayout()
    box = spin(metres, lo, hi)
    form.addRow(label, box)
    lay.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    box.selectAll()
    box.setFocus()
    ok = dlg.exec() == QDialog.Accepted
    return box.value(), ok
