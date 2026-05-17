from datetime import datetime, timedelta

from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.metrics import dp

import db.queries as queries
from components.category_button import CategoryButton
from utils.helpers import current_date, display_date, category_accent, advance_by_interval, RECUR_MAX

_RECUR_MAX = RECUR_MAX  # local alias


class RecurringToggle(Widget):
    """Decorative slider — pure visual; never grabs touches (plain Widget)."""
    active = BooleanProperty(False)


class ToggleRow(BoxLayout):
    """Whole-row clickable container. Press anywhere → flips active."""
    active = BooleanProperty(False)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        self.active = not self.active
        return True


class AddExpenseScreen(Screen):
    selected_date = StringProperty('')
    selected_date_display = StringProperty('')
    selected_category_id = NumericProperty(-1)
    is_recurring = BooleanProperty(False)
    recur_value = NumericProperty(1)
    recur_unit = StringProperty('month')
    recur_preview = StringProperty('')
    currency_symbol = StringProperty('₹')

    def on_enter(self, *args):
        self.currency_symbol = queries.get_setting('currency') or '₹'
        self._set_date(current_date())
        self.selected_category_id = -1
        self.is_recurring = False
        self.recur_value = 1
        self.recur_unit = 'month'
        self.recur_preview = ''
        self.ids.amount_input.text = ''
        self.ids.note_input.text = ''
        self.ids.error_label.text = ''
        self.ids.recur_value_input.text = '1'
        self._build_category_buttons()

    def _set_date(self, date_str):
        self.selected_date = date_str
        self.selected_date_display = display_date(date_str)
        if self.is_recurring:
            self._update_preview()

    def _build_category_buttons(self):
        grid = self.ids.category_grid
        grid.clear_widgets()
        # Alphabetical order from the query, but force "Other" to the end so
        # the catch-all sits after the real categories instead of mid-grid.
        cats = list(queries.get_all_categories())
        cats.sort(key=lambda c: (c['name'] == 'Other', c['name']))
        for cat in cats:
            btn = CategoryButton(
                category_name=cat['name'],
                group='category',
                cat_color=category_accent(cat['color']),
                category_id=cat['id'],
                size_hint_y=None,
                height=dp(40),
            )
            btn.bind(on_press=self._on_category_selected)
            grid.add_widget(btn)

    def _on_category_selected(self, btn):
        self.selected_category_id = btn.category_id if btn.state == 'down' else -1
        self.ids.error_label.text = ''
        if btn.state == 'down':
            self._maybe_auto_subscription(btn.category_name)

    def _maybe_auto_subscription(self, category_name):
        """Selecting the Subscriptions category auto-flips recurring on and
        defaults to monthly cadence (handled by the ToggleRow's on_active →
        on_toggle_changed chain, which resets cadence to 1/month). User can
        still override unit/interval afterwards."""
        if category_name == 'Subscriptions' and not self.is_recurring:
            self.is_recurring = True

    def prev_day(self):
        dt = datetime.strptime(self.selected_date, '%Y-%m-%d')
        self._set_date((dt - timedelta(days=1)).strftime('%Y-%m-%d'))

    def next_day(self):
        dt = datetime.strptime(self.selected_date, '%Y-%m-%d')
        next_dt = dt + timedelta(days=1)
        if next_dt.date() <= datetime.now().date():
            self._set_date(next_dt.strftime('%Y-%m-%d'))

    def on_toggle_changed(self, active):
        if self.is_recurring != active:
            self.is_recurring = active
        if active:
            self.recur_value = 1
            self.recur_unit = 'month'
            self.ids.recur_value_input.text = '1'
            self._update_preview()
        else:
            self.recur_preview = ''

    def set_recur_unit(self, unit):
        self.recur_unit = unit
        hi = RECUR_MAX.get(unit, 12)
        if int(self.recur_value) > hi:
            self.recur_value = hi
            self.ids.recur_value_input.text = str(hi)
        self._update_preview()

    def set_recur_value(self, val_str):
        try:
            v = int(val_str)
        except (ValueError, TypeError):
            return
        if v <= 0:
            return
        hi = RECUR_MAX.get(self.recur_unit, 12)
        clamped = min(v, hi)
        if clamped != self.recur_value:
            self.recur_value = clamped
        if self.is_recurring:
            self._update_preview()

    def _update_preview(self):
        v = int(self.recur_value)
        unit_label = {'day': 'day', 'month': 'month', 'year': 'year'}.get(self.recur_unit, 'month')
        plural = 's' if v > 1 else ''
        try:
            next_date = advance_by_interval(self.selected_date, v, self.recur_unit)
            next_display = display_date(next_date)
            self.recur_preview = f'Repeats every {v} {unit_label}{plural}  (next: {next_display})'
        except Exception:
            self.recur_preview = f'Repeats every {v} {unit_label}{plural}'

    def save_expense(self):
        amount_str = self.ids.amount_input.text.strip()

        if not amount_str:
            self.ids.error_label.text = 'Please enter an amount.'
            return
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            self.ids.error_label.text = 'Enter a valid amount greater than 0.'
            return
        if self.selected_category_id == -1:
            self.ids.error_label.text = 'Please select a category.'
            return

        if self.is_recurring:
            val_str = self.ids.recur_value_input.text.strip()
            try:
                val = max(1, int(val_str))
            except (ValueError, TypeError):
                val = 1
            hi = RECUR_MAX.get(self.recur_unit, 12)
            val = min(val, hi)
            queries.add_expense(
                amount, self.selected_category_id,
                self.ids.note_input.text.strip(),
                self.selected_date,
                is_recurring=1,
                recur_interval=val,
                recur_unit=self.recur_unit,
                recur_next_date=advance_by_interval(self.selected_date, val, self.recur_unit),
                recur_start_date=self.selected_date,
            )
        else:
            queries.add_expense(
                amount, self.selected_category_id,
                self.ids.note_input.text.strip(),
                self.selected_date,
            )
        App.get_running_app().go_to('home')
