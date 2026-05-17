"""Calendar screen — spending heatmap + day detail card.

Design rules followed:
  • All container heights are explicit (no minimum_height / texture_size chains).
  • Day cells, grid, and detail card are sized deterministically per refresh.
"""

from calendar import monthrange
from datetime import datetime

from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import (
    NumericProperty, StringProperty, BooleanProperty, ListProperty,
)
from kivy.metrics import dp, sp

import db.queries as queries
from utils.helpers import (
    current_month, current_date, display_month, format_currency,
    category_accent, relative_date_label,
)


# ── Heatmap palette (5 levels + base + selected) ──────────────────────────────

_LEVELS = [
    (0.114, 0.130, 0.215, 1),  # 0 — no spend / dim
    (0.180, 0.180, 0.330, 1),  # 1
    (0.275, 0.250, 0.460, 1),  # 2
    (0.410, 0.360, 0.640, 1),  # 3
    (0.560, 0.470, 0.870, 1),  # 4 — heaviest spend
]
_SELECTED   = (0.620, 0.500, 0.960, 1)
_TODAY_RING = (0.78,  0.80,  0.95, 0.55)
_FUTURE     = (0.085, 0.100, 0.180, 1)


# ── Day cell ──────────────────────────────────────────────────────────────────

class CalendarDayCell(ButtonBehavior, Widget):
    """Rounded heatmap square with a day number on top."""
    day        = NumericProperty(0)          # 0 → blank padding cell
    iso_date   = StringProperty('')
    level      = NumericProperty(0)          # 0–4
    is_selected = BooleanProperty(False)
    is_today   = BooleanProperty(False)
    is_future  = BooleanProperty(False)

    def on_day(self, *a):         self._safe_redraw()
    def on_level(self, *a):       self._safe_redraw()
    def on_is_selected(self, *a): self._safe_redraw()
    def on_is_today(self, *a):    self._safe_redraw()
    def on_is_future(self, *a):   self._safe_redraw()
    def on_size(self, *a):        self._safe_redraw()
    def on_pos(self, *a):         self._safe_redraw()

    def _safe_redraw(self):
        if self.canvas is None:
            return
        from kivy.graphics import Color, RoundedRectangle, Line
        self.canvas.before.clear()
        self.canvas.after.clear()
        if self.day == 0:
            return
        with self.canvas.before:
            if self.is_selected:
                fill = _SELECTED
            elif self.is_future:
                fill = _FUTURE
            else:
                fill = _LEVELS[max(0, min(4, int(self.level)))]
            Color(*fill)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
            if self.is_today and not self.is_selected:
                Color(*_TODAY_RING)
                Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(10)),
                     width=1.2)

    def on_release(self):
        if self.day == 0 or not self.iso_date:
            return
        app = App.get_running_app()
        if app and app.root:
            try:
                screen = app.root.get_screen('calendar')
            except Exception:
                return
            screen.select_day(self.iso_date)


# ── Legend block ──────────────────────────────────────────────────────────────

class LegendBlock(Widget):
    level = NumericProperty(0)

    def on_level(self, *a): self._safe_redraw()
    def on_size(self, *a):  self._safe_redraw()
    def on_pos(self, *a):   self._safe_redraw()

    def _safe_redraw(self):
        if self.canvas is None:
            return
        from kivy.graphics import Color, RoundedRectangle
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*_LEVELS[max(0, min(4, int(self.level)))])
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(4)])


# ── Transaction mini-row (re-use ExpenseItem-like visuals, simplified) ────────

class CalendarTxRow(ButtonBehavior, BoxLayout):
    expense_id = NumericProperty(0)
    title      = StringProperty('')
    subtitle   = StringProperty('')
    amount     = StringProperty('')
    cat_color  = ListProperty([0.5, 0.5, 0.5, 1])

    def on_release(self):
        app = App.get_running_app()
        if app and self.expense_id:
            app.open_expense(self.expense_id, return_to='calendar')


# ── Screen ────────────────────────────────────────────────────────────────────

class CalendarScreen(Screen):
    month            = StringProperty('')      # 'YYYY-MM'
    month_display    = StringProperty('')      # 'May 2026'
    selected_date    = StringProperty('')      # 'YYYY-MM-DD'
    is_current_month = BooleanProperty(False)
    month_total_text = StringProperty('')
    active_days_text = StringProperty('')

    def on_pre_enter(self, *args):
        if not self.month:
            self.month = current_month()
        if not self.selected_date or not self.selected_date.startswith(self.month):
            self._set_default_selected()
        self._refresh()

    def _set_default_selected(self):
        # Today if in current month, else first of the month
        today = current_date()
        if today.startswith(self.month):
            self.selected_date = today
        else:
            self.selected_date = f'{self.month}-01'

    # ── Navigation ────────────────────────────────────────────────────────────
    def prev_month(self):
        y, m = int(self.month[:4]), int(self.month[5:7])
        if m == 1:
            self.month = f'{y - 1}-12'
        else:
            self.month = f'{y}-{m - 1:02d}'
        self._set_default_selected()
        self._refresh()

    def next_month(self):
        now = datetime.now()
        y, m = int(self.month[:4]), int(self.month[5:7])
        if y == now.year and m == now.month:
            return
        if m == 12:
            self.month = f'{y + 1}-01'
        else:
            self.month = f'{y}-{m + 1:02d}'
        self._set_default_selected()
        self._refresh()

    def select_day(self, iso_date):
        self.selected_date = iso_date
        self._refresh_grid_selection()
        self._refresh_detail()

    # ── Refresh ───────────────────────────────────────────────────────────────
    def _refresh(self):
        self.month_display = display_month(self.month)
        now = datetime.now()
        y, m = int(self.month[:4]), int(self.month[5:7])
        self.is_current_month = (y == now.year and m == now.month)

        self._daily = {
            d['date']: d['total']
            for d in queries.get_daily_totals_for_month(self.month)
        }
        currency = queries.get_setting('currency') or '₹'
        total = sum(self._daily.values())
        n_active = sum(1 for v in self._daily.values() if v > 0)
        self.month_total_text = format_currency(total, currency)
        self.active_days_text = f'{n_active} day{"s" if n_active != 1 else ""} active'

        max_total = max(self._daily.values()) if self._daily else 0
        self._max_daily = max_total

        self._build_grid()
        self._refresh_detail()

    def _level_for(self, amount):
        if amount <= 0 or self._max_daily <= 0:
            return 0
        ratio = amount / self._max_daily
        if ratio < 0.20: return 1
        if ratio < 0.45: return 2
        if ratio < 0.75: return 3
        return 4

    def _build_grid(self):
        grid = self.ids.day_grid
        grid.clear_widgets()
        y, m = int(self.month[:4]), int(self.month[5:7])
        first_wd, last_day = monthrange(y, m)  # first_wd: 0=Mon
        # Convert to Sunday-first (US): weekdays start with Sun (0)
        leading_blanks = (first_wd + 1) % 7

        today = current_date()
        self._cells_by_iso = {}

        for _ in range(leading_blanks):
            grid.add_widget(CalendarDayCell(day=0))

        for d in range(1, last_day + 1):
            iso = f'{y}-{m:02d}-{d:02d}'
            amount = self._daily.get(iso, 0)
            is_future = iso > today
            cell = CalendarDayCell(
                day=d,
                iso_date=iso,
                level=self._level_for(amount),
                is_selected=(iso == self.selected_date),
                is_today=(iso == today),
                is_future=is_future,
            )
            self._cells_by_iso[iso] = cell
            grid.add_widget(cell)

        # Pad trailing cells so grid is always 6 rows
        total_cells = leading_blanks + last_day
        rows = (total_cells + 6) // 7
        rows = max(rows, 6)
        trailing = rows * 7 - total_cells
        for _ in range(trailing):
            grid.add_widget(CalendarDayCell(day=0))

        # Day numbers — set on a labels overlay (one big GridLayout of labels
        # is overkill; instead we paint the digits via a Label child added
        # inside each cell via _attach_day_label).
        for iso, cell in self._cells_by_iso.items():
            self._attach_day_label(cell)

        grid.rows = rows

    def _attach_day_label(self, cell):
        if cell.children:
            return  # already attached
        lbl = Label(
            text=str(cell.day),
            font_size=sp(13),
            bold=True,
            color=(0.95, 0.95, 1.0, 1) if (cell.level >= 3 or cell.is_selected)
                  else (0.45, 0.47, 0.58, 1) if cell.is_future
                  else (0.82, 0.83, 0.92, 1),
            halign='center',
            valign='middle',
        )
        # Bind text_size to cell size so the label always fills cell.
        lbl.size = cell.size
        lbl.pos = cell.pos
        cell.bind(size=lambda w, v: setattr(lbl, 'size', v))
        cell.bind(pos=lambda w, v: setattr(lbl, 'pos', v))
        lbl.text_size = lbl.size
        lbl.bind(size=lambda w, v: setattr(w, 'text_size', v))
        cell.add_widget(lbl)

    def _refresh_grid_selection(self):
        today = current_date()
        for iso, cell in self._cells_by_iso.items():
            cell.is_selected = (iso == self.selected_date)
            # Refresh label color (selected → high contrast)
            if cell.children:
                lbl = cell.children[0]
                lbl.color = (
                    (0.95, 0.95, 1.0, 1) if (cell.level >= 3 or cell.is_selected)
                    else (0.45, 0.47, 0.58, 1) if cell.is_future
                    else (0.82, 0.83, 0.92, 1)
                )

    def _refresh_detail(self):
        currency = queries.get_setting('currency') or '₹'
        date_lbl = self.ids.detail_date
        total_lbl = self.ids.detail_total
        count_lbl = self.ids.detail_count
        tx_list = self.ids.detail_tx_list

        tx_list.clear_widgets()

        if not self.selected_date:
            date_lbl.text = ''
            total_lbl.text = ''
            count_lbl.text = '0'
            self._set_detail_height(0)
            return

        date_lbl.text = relative_date_label(self.selected_date) \
            if (current_date() == self.selected_date
                or relative_date_label(self.selected_date) in ('Today', 'Yesterday'))\
            else datetime.strptime(self.selected_date, '%Y-%m-%d').strftime('%A, %b %d')\
                 .replace(' 0', ' ')

        # Pull all month expenses, filter for selected date
        expenses = [e for e in queries.get_expenses_for_month(self.month)
                    if e['date'] == self.selected_date]
        total = sum(e['amount'] for e in expenses)
        total_lbl.text = f'{format_currency(total, currency)} spent' if expenses \
            else 'No spending'
        count_lbl.text = str(len(expenses))

        TX_H = dp(54)
        TX_SPACING = dp(6)
        for e in expenses:
            row = CalendarTxRow(
                expense_id=e['id'],
                title=e['category'],
                subtitle=e['note'] or '',
                amount=format_currency(e['amount'], currency),
                cat_color=category_accent(e['color']),
            )
            tx_list.add_widget(row)

        n = len(expenses)
        list_h = n * TX_H + max(0, n - 1) * TX_SPACING
        tx_list.height = list_h
        self._set_detail_height(list_h)

    def _set_detail_height(self, list_h):
        # Header (date row dp(28) + total row dp(20) + spacing dp(6)) + padding
        header_h = dp(28) + dp(20) + dp(6)
        padding_v = dp(16) + dp(16)
        spacing_after_header = dp(12) if list_h > 0 else 0
        self.ids.detail_card.height = header_h + padding_v + spacing_after_header + list_h
        # Recompute scroll content height — every section is now fixed/known.
        fixed = dp(46) + dp(22) + dp(282) + dp(26)
        spacing = dp(14) * 5
        padding = dp(4) + dp(100)
        self.ids.scroll_content.height = fixed + spacing + padding + self.ids.detail_card.height
