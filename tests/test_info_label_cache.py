"""Regression tests for the menu label relayout guard.

Pyglet 2.x reruns DirectWrite layout whenever ``Label.text`` is assigned,
even when the value is unchanged.  The first menu frame used to spend
several seconds relaying out constant labels; these tests pin down the
"only write changed properties" contract.
"""

import unittest

from functions import _sync_info_label


class _FakeLabel:
    _FIELDS = ("text", "font_size", "x", "y", "anchor_x", "anchor_y")

    def __init__(self):
        object.__setattr__(self, "_values", {
            "text": "",
            "font_size": 15,
            "x": 0,
            "y": 0,
            "anchor_x": "left",
            "anchor_y": "baseline",
        })
        object.__setattr__(self, "writes", [])

    def __getattr__(self, name):
        values = object.__getattribute__(self, "_values")
        if name in values:
            return values[name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        values = object.__getattribute__(self, "_values")
        if name in values:
            if values[name] != value:
                object.__getattribute__(self, "writes").append(name)
            values[name] = value
        else:
            object.__setattr__(self, name, value)


class InfoLabelCacheTests(unittest.TestCase):
    def test_first_sync_writes_only_changed_properties(self):
        label = _FakeLabel()
        _sync_info_label(
            label, "hello", 12, 10, 20, "center", "baseline"
        )
        self.assertEqual(
            label.writes, ["text", "font_size", "x", "y", "anchor_x"]
        )

    def test_unchanged_label_is_not_rewritten(self):
        label = _FakeLabel()
        _sync_info_label(
            label, "hello", 12, 10, 20, "center", "baseline"
        )
        label.writes.clear()

        _sync_info_label(
            label, "hello", 12, 10, 20, "center", "baseline"
        )
        self.assertEqual(label.writes, [])

    def test_changed_text_triggers_relayout(self):
        label = _FakeLabel()
        _sync_info_label(
            label, "before", 12, 10, 20, "center", "baseline"
        )
        label.writes.clear()

        _sync_info_label(
            label, "after", 12, 10, 20, "center", "baseline"
        )
        self.assertEqual(label.writes, ["text"])


if __name__ == "__main__":
    unittest.main()
