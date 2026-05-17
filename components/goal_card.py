from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.properties import (
    StringProperty, NumericProperty, BooleanProperty, ListProperty,
)
from kivy.metrics import dp


class GoalCard(BoxLayout):
    """Compact savings-goal card with milestone progress track."""
    goal_id       = NumericProperty(0)
    goal_name     = StringProperty('')
    saved_text    = StringProperty('')        # "$6,450 of $10,000"
    pct           = NumericProperty(0)        # 0–100
    pct_text      = StringProperty('')        # "65%"
    ratio         = NumericProperty(0.0)      # 0.0–1.0
    due_text      = StringProperty('')
    forecast_text = StringProperty('')
    accent_color  = ListProperty([0.62, 0.50, 0.96, 1])
    is_complete   = BooleanProperty(False)


class MilestoneProgress(Widget):
    """Thin line + 4 milestone dots at 25/50/75/100, filled by ratio."""
    ratio        = NumericProperty(0.0)
    accent_color = ListProperty([0.62, 0.50, 0.96, 1])

    def on_ratio(self, *a):        self._safe_redraw()
    def on_accent_color(self, *a): self._safe_redraw()
    def on_size(self, *a):         self._safe_redraw()
    def on_pos(self, *a):          self._safe_redraw()

    def _safe_redraw(self):
        if self.canvas is None:
            return
        from kivy.graphics import Color, RoundedRectangle, Ellipse
        self.canvas.before.clear()
        with self.canvas.before:
            # Track
            cy = self.y + self.height / 2
            track_h = dp(3)
            Color(0.14, 0.16, 0.26, 1)
            RoundedRectangle(
                pos=(self.x, cy - track_h / 2),
                size=(self.width, track_h),
                radius=[track_h / 2],
            )
            # Filled portion
            r = max(0.0, min(self.ratio, 1.0))
            fill_w = self.width * r
            if fill_w > 0:
                ac = self.accent_color
                Color(ac[0], ac[1], ac[2], 1)
                RoundedRectangle(
                    pos=(self.x, cy - track_h / 2),
                    size=(fill_w, track_h),
                    radius=[track_h / 2],
                )

            # Milestone dots at 25/50/75/100
            dot = dp(12)
            ring = dp(10)
            for pct in (0.25, 0.50, 0.75, 1.0):
                cx = self.x + self.width * pct
                filled = (pct <= r + 0.001)
                # Outer ring
                if filled:
                    ac = self.accent_color
                    Color(ac[0], ac[1], ac[2], 1)
                else:
                    Color(0.18, 0.20, 0.30, 1)
                Ellipse(pos=(cx - dot / 2, cy - dot / 2), size=(dot, dot))
                # Inner hole for unfilled (creates a "ring" look)
                if not filled:
                    Color(0.094, 0.108, 0.180, 1)  # card surface
                    Ellipse(pos=(cx - ring / 2, cy - ring / 2), size=(ring, ring))
