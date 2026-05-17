from datetime import datetime

from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import (
    NumericProperty, StringProperty, BooleanProperty, ListProperty,
)


# ── Reusable detail-screen sub-widgets ────────────────────────────────────────
# These are defined as real Python classes (not KV `@` dynamic classes) so the
# ListProperty defaults are guaranteed non-empty before canvas.before evaluates.
# Dynamic KV classes infer ListProperty defaults as `[]`, which crashed
# `self.tint[0]` during widget construction.

class DetailActionButton(ButtonBehavior, BoxLayout):
    icon = StringProperty('')
    label = StringProperty('')
    tint = ListProperty([0.75, 0.77, 0.95, 1])
    fill_alpha = NumericProperty(0.10)


class DetailInfoRow(BoxLayout):
    info_label = StringProperty('')
    info_value = StringProperty('')
    info_color = ListProperty([0.92, 0.92, 0.97, 1])

import db.queries as queries
from utils.popups import AppModal, ConfirmPopup
from utils.helpers import (
    format_currency, display_date, category_accent,
    current_date, humanize_recur, advance_by_interval, RECUR_MAX,
)


def _humanize_timestamp(ts):
    """`ts` is either 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'. Returns a clean
    human-readable date (with time if available)."""
    if not ts:
        return ''
    try:
        if len(ts) > 10:
            dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
            return dt.strftime('%d %b %Y · %I:%M %p').lstrip('0')
        dt = datetime.strptime(ts, '%Y-%m-%d')
        return dt.strftime('%d %b %Y')
    except (ValueError, TypeError):
        return ts


class MakeRecurringPopup(AppModal):
    recur_value = NumericProperty(1)
    recur_unit_val = StringProperty('month')
    recur_preview = StringProperty('')

    def __init__(self, expense_id, on_done, **kwargs):
        super().__init__(**kwargs)
        self._expense_id = expense_id
        self._on_done = on_done

    def on_open(self):
        super().on_open()
        self.recur_value = 1
        self.recur_unit_val = 'month'
        self.ids.recur_value_input.text = '1'
        self._update_preview()

    def set_unit(self, unit):
        self.recur_unit_val = unit
        hi = RECUR_MAX.get(unit, 12)
        if int(self.recur_value) > hi:
            self.recur_value = hi
            self.ids.recur_value_input.text = str(hi)
        self._update_preview()

    def set_value(self, val_str):
        try:
            v = int(val_str)
            if v > 0:
                hi = RECUR_MAX.get(self.recur_unit_val, 12)
                self.recur_value = min(v, hi)
                self._update_preview()
        except (ValueError, TypeError):
            pass

    def _update_preview(self):
        v = int(self.recur_value)
        unit = self.recur_unit_val
        plural = 's' if v > 1 else ''
        try:
            next_dt = advance_by_interval(current_date(), v, unit)
            self.recur_preview = f'Every {v} {unit}{plural}  ·  next {display_date(next_dt)}'
        except Exception:
            self.recur_preview = f'Every {v} {unit}{plural}'

    def confirm(self):
        v = int(self.recur_value)
        unit = self.recur_unit_val
        next_dt = advance_by_interval(current_date(), v, unit)
        queries.enable_recurring_expense(self._expense_id, v, unit, next_dt)
        self._on_done()
        self.dismiss()


class ExpenseDetailScreen(Screen):
    """Full-screen drill-down for a single expense.

    Set `expense_id` then navigate here; `on_pre_enter` reloads from DB so
    the page always reflects current state (in case of external edits).
    """
    expense_id = NumericProperty(0)

    # Display properties (populated from DB on enter)
    amount_text = StringProperty('—')
    category_name = StringProperty('')
    title_text = StringProperty('')
    icon_letter = StringProperty('?')
    accent_color = ListProperty([0.75, 0.77, 0.95, 1])
    accent_soft = ListProperty([0.75, 0.77, 0.95, 0.14])
    date_text = StringProperty('')
    note_text = StringProperty('')
    has_note = BooleanProperty(False)

    is_recurring = BooleanProperty(False)
    recur_label = StringProperty('')
    recur_next_text = StringProperty('')
    recur_paused = BooleanProperty(False)
    kind_badge_text = StringProperty('Recurring')

    created_text = StringProperty('')

    # Internal — keep a snapshot for actions (in case the row is deleted mid-action)
    _expense = None
    _return_to = 'history'

    def on_pre_enter(self, *args):
        self._load()

    def set_expense(self, expense_id, return_to='history'):
        """Public entry point used by app.open_expense().

        Reloads immediately so the page refreshes even when navigating from
        detail to detail (e.g. right after a duplicate)."""
        self.expense_id = expense_id
        self._return_to = return_to or 'history'
        self._load()

    def _load(self):
        e = queries.get_expense_by_id(self.expense_id)
        self._expense = e
        if not e:
            self.amount_text = '—'
            self.category_name = 'Not found'
            return

        currency = queries.get_setting('currency') or '₹'
        self.amount_text = format_currency(e['amount'], currency)
        self.category_name = e['category']

        accent = category_accent(e['color'])
        self.accent_color = list(accent)
        self.accent_soft = [accent[0], accent[1], accent[2], 0.14]

        self.date_text = display_date(e['date'])
        self.note_text = e['note'] or ''
        self.has_note = bool(e['note'])
        self.title_text = (e['note'] or '').strip() or e['category']
        self.icon_letter = self.title_text[0].upper() if self.title_text else '?'

        is_subscription = (e['category'] == 'Subscriptions')
        self.is_recurring = e['is_recurring']
        self.recur_paused = e['recur_paused']
        if self.is_recurring:
            self.recur_label = humanize_recur(e['recur_interval'], e['recur_unit'])
            self.recur_next_text = (
                'Paused' if self.recur_paused else
                (display_date(e['recur_next_date']) if e['recur_next_date'] else '—')
            )
            # Items in the Subscriptions category get a distinct badge —
            # internally they are just normal recurring expenses. An active
            # subscription reads as 'Active' (not 'Subscription'), matching
            # the manager screen's ACTIVE / PAUSED grouping vocabulary.
            self.kind_badge_text = (
                'Paused' if self.recur_paused else
                ('Active' if is_subscription else 'Recurring')
            )
        else:
            self.recur_label = ''
            self.recur_next_text = ''
            self.kind_badge_text = 'Recurring'

        self.created_text = _humanize_timestamp(e.get('created_at') or e['date'])

    # ── Actions ───────────────────────────────────────────────────────────────

    def go_back(self):
        App.get_running_app().go_to(self._return_to)

    def open_edit(self):
        """Open the existing EditExpensePopup. After save, reload this view."""
        if not self._expense:
            return
        from screens.history import EditExpensePopup
        popup = EditExpensePopup(expense_data=self._expense, on_save=self._after_edit)
        popup.open()

    def _after_edit(self):
        # Refresh detail view from DB
        self._load()

    def confirm_delete(self):
        if not self._expense:
            return
        ConfirmPopup(
            title='Delete Expense',
            message='Delete this expense?\nThis cannot be undone.',
            on_confirm=self._do_delete,
            confirm_label='Delete',
        ).open()

    def _do_delete(self):
        queries.delete_expense(self.expense_id)
        self.go_back()

    def make_recurring(self):
        if not self._expense or self.is_recurring:
            return
        MakeRecurringPopup(
            expense_id=self.expense_id,
            on_done=self._load,
        ).open()

    def toggle_pause(self):
        if not self._expense or not self.is_recurring:
            return
        new_paused = not self.recur_paused
        queries.set_recurring_paused(self.expense_id, new_paused)
        self._load()
