from datetime import datetime, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.modalview import ModalView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.metrics import dp

import db.queries as queries
from components.expense_item import ExpenseItem  # noqa: F401
from components.category_chip import (
    CategoryChip, icon_for_category,
    CATEGORY_ICON_ALL, CATEGORY_ICON_RECURRING,
)
from utils.popups import ConfirmPopup, TRANSPARENT_BG
from utils.helpers import (
    current_month, display_month, display_date, format_currency,
    hex_to_kivy_color, category_accent, days_until, advance_by_interval, current_date, RECUR_MAX,
    relative_date_label,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp, sp


class DateGroupHeader(RecycleDataViewBehavior, BoxLayout):
    """Section header above a date-grouped run of expenses.

    Mixes in RecycleDataViewBehavior so it can be rendered as a viewclass
    inside the expense RecycleView alongside ExpenseItem rows.
    """
    label_text = StringProperty('')
    total_text = StringProperty('')

_RECUR_MAX = RECUR_MAX  # local alias


# Neutral accent for the "All" chip — primary lavender (matches design tokens).
_ALL_ACCENT = (0.75, 0.77, 0.95, 1)
# Recurring chip — Subscriptions violet, softened through category_accent so it
# matches the rest of the app's category-tinted surfaces.
_RECURRING_ACCENT_HEX = '#7E57C2'


class EditExpensePopup(ModalView):
    expense_id = NumericProperty(0)
    selected_category_id = NumericProperty(-1)
    selected_date = StringProperty('')
    selected_date_display = StringProperty('')
    is_recurring = BooleanProperty(False)
    was_recurring = BooleanProperty(False)
    recur_paused = BooleanProperty(False)
    recur_value = NumericProperty(1)
    recur_unit_val = StringProperty('month')
    recur_preview = StringProperty('')
    currency_symbol = StringProperty('₹')

    def __init__(self, expense_data, on_save, **kwargs):
        # Same trick as AppModal: point at a fully-transparent PNG and a
        # neutral white tint so Kivy doesn't multiply `background_color` with
        # its default gray BorderImage chrome (which was darkening the popup
        # surface to roughly half of the intended navy and making the bg
        # read as near-black). The KV `BoxLayout` paints the real navy fill.
        kwargs.setdefault('background', TRANSPARENT_BG)
        kwargs.setdefault('background_color', [1, 1, 1, 1])
        kwargs.setdefault('overlay_color', [0, 0, 0, 0])
        super().__init__(**kwargs)
        self._on_save = on_save
        self._expense = expense_data
        self.expense_id = expense_data['id']

    def on_open(self):
        e = self._expense
        amt = e['amount']
        self.currency_symbol = queries.get_setting('currency') or '₹'
        self.ids.amount_input.text = str(int(amt)) if amt == int(amt) else str(amt)
        self.ids.note_input.text = e['note'] or ''
        self.selected_date = e['date']
        self.selected_date_display = display_date(e['date'])
        self.is_recurring = e.get('is_recurring', False)
        self.was_recurring = self.is_recurring
        self.recur_paused = e.get('recur_paused', False)
        self.recur_value = e.get('recur_interval', 1)
        self.recur_unit_val = e.get('recur_unit', 'month')
        self._build_category_buttons(e['category_id'])
        if self.is_recurring:
            self.ids.edit_recur_value_input.text = str(int(self.recur_value))
            self._update_preview()

    def _build_category_buttons(self, selected_id):
        from components.category_button import CategoryButton
        grid = self.ids.category_grid
        grid.clear_widgets()
        # Mirror Add Expense: 3-column GridLayout with dp(40) tall buttons that
        # flex to the grid column width. Query already places "Other" last.
        for cat in queries.get_all_categories():
            btn = CategoryButton(
                category_name=cat['name'],
                group='edit_cat',
                cat_color=category_accent(cat['color']),
                category_id=cat['id'],
                size_hint_y=None,
                height=dp(40),
                state='down' if cat['id'] == selected_id else 'normal',
            )
            btn.bind(texture_size=lambda inst, val: setattr(inst, 'width', val[0] + dp(32)))
            btn.bind(on_press=self._on_category_selected)
            grid.add_widget(btn)
        self.selected_category_id = selected_id

    def _on_category_selected(self, btn):
        self.selected_category_id = btn.category_id if btn.state == 'down' else -1

    def prev_day(self):
        dt = datetime.strptime(self.selected_date, '%Y-%m-%d')
        d = (dt - timedelta(days=1)).strftime('%Y-%m-%d')
        self.selected_date = d
        self.selected_date_display = display_date(d)

    def next_day(self):
        dt = datetime.strptime(self.selected_date, '%Y-%m-%d')
        nxt = dt + timedelta(days=1)
        if nxt.date() <= datetime.now().date():
            d = nxt.strftime('%Y-%m-%d')
            self.selected_date = d
            self.selected_date_display = display_date(d)

    def on_edit_toggle_changed(self, active):
        if self.is_recurring != active:
            self.is_recurring = active
        if active:
            if not self.was_recurring:
                self.recur_value = 1
                self.recur_unit_val = 'month'
                self.ids.edit_recur_value_input.text = '1'
            self._update_preview()
        else:
            self.recur_preview = ''

    def _update_preview(self):
        v = int(self.recur_value)
        unit_label = {'day': 'day', 'month': 'month', 'year': 'year'}.get(self.recur_unit_val, 'month')
        plural = 's' if v > 1 else ''
        try:
            next_dt = advance_by_interval(current_date(), v, self.recur_unit_val)
            self.recur_preview = f'Repeats every {v} {unit_label}{plural}  (next: {display_date(next_dt)})'
        except Exception:
            self.recur_preview = f'Repeats every {v} {unit_label}{plural}'

    def set_edit_recur_value(self, val_str):
        try:
            v = int(val_str)
            if v > 0:
                hi = RECUR_MAX.get(self.recur_unit_val, 12)
                self.recur_value = min(v, hi)
                if self.is_recurring:
                    self._update_preview()
        except (ValueError, TypeError):
            pass

    def set_edit_recur_unit(self, unit):
        self.recur_unit_val = unit
        hi = RECUR_MAX.get(unit, 12)
        if int(self.recur_value) > hi:
            self.recur_value = hi
            self.ids.edit_recur_value_input.text = str(hi)
        if self.is_recurring:
            self._update_preview()

    def toggle_pause(self):
        self.recur_paused = not self.recur_paused
        queries.set_recurring_paused(self.expense_id, self.recur_paused)
        self._on_save()

    def stop_recurring(self):
        popup = ConfirmPopup(
            title='Stop Recurring',
            message='This expense will no longer repeat.\nThe expense itself is kept.',
            on_confirm=self._do_stop_recurring,
            confirm_label='Stop',
        )
        popup.open()

    def _do_stop_recurring(self):
        queries.stop_recurring_expense(self.expense_id)
        self.is_recurring = False
        self._on_save()
        self.dismiss()

    def save(self):
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

        queries.update_expense(
            self.expense_id, amount,
            self.selected_category_id,
            self.ids.note_input.text.strip(),
            self.selected_date,
        )

        if self.is_recurring:
            val_str = self.ids.edit_recur_value_input.text.strip()
            try:
                iv = max(1, int(val_str))
            except (ValueError, TypeError):
                iv = 1
            hi = RECUR_MAX.get(self.recur_unit_val, 12)
            iv = min(iv, hi)
            if self.was_recurring:
                queries.update_recurring_schedule(self.expense_id, iv, self.recur_unit_val)
            else:
                queries.enable_recurring_expense(
                    self.expense_id, iv, self.recur_unit_val,
                    advance_by_interval(current_date(), iv, self.recur_unit_val),
                )
        elif self.was_recurring:
            queries.stop_recurring_expense(self.expense_id)

        self._on_save()
        self.dismiss()


_SEARCH_DEBOUNCE_S = 0.2  # 200ms — pause-detect, not throttle
_HEADER_H = dp(34)
_ROW_H    = dp(64)


class HistoryScreen(Screen):
    """History screen with a RecycleView-backed expense list.

    Performance contract:
      - Only the visible rows are real widgets. RV recycles instances.
      - DateGroupHeader and ExpenseItem rows interleave via per-item viewclass
        in the data dict — RV pools each class separately.
      - Filter chips are mounted once per dataset and only flip `active` on
        selection; no clear_widgets / no chip texture rebuild.
      - Search keystrokes only schedule a single delayed _apply_filter; rapid
        typing cancels prior pending calls so we filter once when the user
        pauses.
      - Currency is read from SQLite once per _refresh and cached on the
        screen, not re-read inside _apply_filter (which can run on every
        keystroke / filter tap).
    """
    month = StringProperty('')
    month_display = StringProperty('')
    active_filter = StringProperty('')
    search_query = StringProperty('')
    is_current_month = BooleanProperty(False)
    # Drives the empty-state overlay in KV. The RV is hidden whenever this is
    # True so an empty data list doesn't render a blank scroll area.
    is_empty_state = BooleanProperty(True)
    empty_title = StringProperty('')
    empty_subtitle = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._raw_expenses = []
        self._search_event = None         # Clock event for debounced filter
        self._chips_by_key = {}           # filter_key -> CategoryChip
        self._cached_currency = '₹'
        # Deep-link pre-seeds. Callers (Analytics category tap, Calendar day
        # tap, future hosts) set these BEFORE calling app.go_to('history').
        # on_enter consumes them once, so a second visit to History without
        # a fresh pre-seed reverts to the default "all categories, current
        # month, no search" state.
        self._pending_filter = None       # category name or '' for All
        self._pending_month = None        # 'YYYY-MM' or None
        self._pending_search = None       # query string or None

    # ── Deep-link API ─────────────────────────────────────────────────────────

    def deep_link(self, category=None, month=None, search=None):
        """Pre-seed the next entry to History.

        Any arg left as None keeps the existing default behavior for that
        dimension on the next on_enter. Pass `category=''` to explicitly
        select the All chip; pass a category name (e.g. 'Food') to filter
        to that category."""
        if category is not None:
            self._pending_filter = category
        if month is not None:
            self._pending_month = month
        if search is not None:
            self._pending_search = search

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_enter(self, *args):
        # Consume any pre-seed from a deep-link (Analytics, Calendar, etc.)
        # exactly once. Without an explicit pre-seed, defaults take over:
        # current month, no category filter, no search.
        if self._pending_month is not None:
            self.month = self._pending_month
            self._pending_month = None
        elif not self.month:
            self.month = current_month()

        self._raw_expenses = []
        self.active_filter = self._pending_filter or ''
        self._pending_filter = None
        self.search_query = self._pending_search or ''
        self._pending_search = None
        self._refresh()

    def _refresh(self):
        # Cancel any in-flight search before clobbering inputs.
        self._cancel_pending_search()

        self.month_display = display_month(self.month)
        now = datetime.now()
        dt = datetime.strptime(self.month, '%Y-%m')
        self.is_current_month = (dt.year == now.year and dt.month == now.month)

        # One SQLite hit per refresh; cached for the rest of the cycle.
        self._cached_currency = queries.get_setting('currency') or '₹'
        self._raw_expenses = queries.get_expenses_for_month(self.month)

        total = sum(e['amount'] for e in self._raw_expenses)
        n = len(self._raw_expenses)
        self.ids.total_label.text = (
            f'{format_currency(total, self._cached_currency)}  ·  '
            f'{n} expense{"s" if n != 1 else ""}'
        )
        self.ids.count_label.text = ''

        # Clear search input on month change (cancel above already nuked the
        # pending event so setting .text won't trigger another scheduled run).
        if hasattr(self.ids, 'search_input'):
            self.ids.search_input.text = ''
        self.search_query = ''

        self._build_filter_chips()
        self._apply_filter()

    # ── Filter chips (build once, toggle thereafter) ──────────────────────────

    def _build_filter_chips(self):
        """Rebuild chip widgets only when the *set of categories* changes;
        otherwise just flip each chip's `active` flag. Toggling is O(N) on
        properties; rebuilding is O(N) on widget construction + texture
        regeneration. The fast path matters because every filter tap calls
        this through set_filter."""
        seen = set()
        cats = []  # list[(name, color_hex)]
        for e in self._raw_expenses:
            name = e['category']
            if name not in seen:
                seen.add(name)
                cats.append((name, e['color']))
        # "Other" is the catch-all — always last in the filter row, regardless
        # of when it first appeared in the expense list. Stable sort preserves
        # the existing relative order of every other category.
        cats.sort(key=lambda c: c[0] == 'Other')

        has_recurring = any(e.get('is_recurring') for e in self._raw_expenses)

        # Desired ordered list of (key, label, icon, accent_rgba)
        desired = []
        if cats:
            desired.append(('', 'All', CATEGORY_ICON_ALL, list(_ALL_ACCENT)))
            if has_recurring:
                desired.append((
                    '__recurring__', 'Recurring', CATEGORY_ICON_RECURRING,
                    list(category_accent(_RECURRING_ACCENT_HEX)),
                ))
            for name, color_hex in cats:
                desired.append((
                    name, name, icon_for_category(name),
                    list(category_accent(color_hex)),
                ))

        desired_keys = [d[0] for d in desired]
        existing_keys = list(self._chips_by_key.keys())

        # Fast path: same chip set as last time — just retarget the active flag.
        if desired_keys == existing_keys:
            for key, chip in self._chips_by_key.items():
                chip.active = (key == self.active_filter)
            return

        # Slow path: dataset's category set changed (month switch / first paint
        # / delete-last-of-a-category). Tear down and rebuild.
        container = self.ids.filter_chips
        container.clear_widgets()
        self._chips_by_key.clear()

        for key, label, icon, accent in desired:
            chip = CategoryChip(
                text=label, icon=icon, accent=accent,
                active=(key == self.active_filter),
            )
            # Default-arg trick captures `key` per-chip (lambdas otherwise share).
            chip.bind(on_release=lambda _, k=key: self.set_filter(k))
            container.add_widget(chip)
            self._chips_by_key[key] = chip

    def set_filter(self, key):
        if key == self.active_filter:
            return
        self.active_filter = key
        # Pure property flip — no widget churn.
        for k, chip in self._chips_by_key.items():
            chip.active = (k == key)
        # A pending debounced search would re-apply the filter ~200 ms later
        # anyway, so canceling here avoids one redundant pass on the new key.
        self._cancel_pending_search()
        self._apply_filter()

    # ── Search (debounced) ────────────────────────────────────────────────────

    def on_search_text(self, text):
        new_q = text.strip().lower()
        if new_q == self.search_query:
            return
        self.search_query = new_q
        self._cancel_pending_search()
        self._search_event = Clock.schedule_once(
            self._apply_filter_event, _SEARCH_DEBOUNCE_S,
        )

    def _apply_filter_event(self, _dt):
        self._search_event = None
        self._apply_filter()

    def _cancel_pending_search(self):
        if self._search_event is not None:
            self._search_event.cancel()
            self._search_event = None

    # ── Filtering + RV data assembly ──────────────────────────────────────────

    def _apply_filter(self, *_):
        currency = self._cached_currency

        # Category / recurring filter
        if self.active_filter == '__recurring__':
            filtered = [e for e in self._raw_expenses if e.get('is_recurring')]
        elif self.active_filter:
            filtered = [
                e for e in self._raw_expenses
                if e['category'] == self.active_filter
            ]
        else:
            filtered = self._raw_expenses

        # Search filter (note / category / amount)
        q = self.search_query
        if q:
            def matches(e):
                return (
                    q in (e.get('note') or '').lower()
                    or q in e['category'].lower()
                    or q in str(e['amount'])
                )
            filtered = [e for e in filtered if matches(e)]

        if not filtered:
            self.is_empty_state = True
            self.empty_title = (
                'No expenses yet' if not self._raw_expenses else 'No matches'
            )
            self.empty_subtitle = (
                'Add an expense to get started' if not self._raw_expenses
                else 'Try a different search or filter'
            )
            # Drop RV data so the recycled rows release their references.
            self.ids.expense_rv.data = []
            return

        self.is_empty_state = False

        # Build the RV data list. One pass for grouping + totals + row dicts.
        # Preserves the original DESC ordering from queries.get_expenses_for_month.
        date_order = []
        date_items = {}
        date_totals = {}
        for e in filtered:
            d = e['date']
            if d not in date_items:
                date_items[d] = []
                date_totals[d] = 0.0
                date_order.append(d)
            date_items[d].append(e)
            date_totals[d] += e['amount']

        data = []
        for d in date_order:
            data.append({
                'viewclass': 'DateGroupHeader',
                'label_text': relative_date_label(d),
                'total_text': format_currency(date_totals[d], currency),
                'height': _HEADER_H,
            })
            for e in date_items[d]:
                data.append(_expense_row_data(e, currency))

        rv = self.ids.expense_rv
        rv.data = data
        # Snap to top once layout settles. Doing it next frame avoids a race
        # where RV is still mid-relayout when we set scroll_y.
        Clock.schedule_once(lambda _dt: setattr(rv, 'scroll_y', 1), 0)

    # ── Month navigation ──────────────────────────────────────────────────────

    def prev_month(self):
        self._cancel_pending_search()
        dt = datetime.strptime(self.month, '%Y-%m')
        if dt.month == 1:
            self.month = f'{dt.year - 1}-12'
        else:
            self.month = f'{dt.year}-{dt.month - 1:02d}'
        self.active_filter = ''
        self._refresh()

    def next_month(self):
        self._cancel_pending_search()
        dt = datetime.strptime(self.month, '%Y-%m')
        now = datetime.now()
        if dt.year == now.year and dt.month == now.month:
            return
        if dt.month == 12:
            self.month = f'{dt.year + 1}-01'
        else:
            self.month = f'{dt.year}-{dt.month + 1:02d}'
        self.active_filter = ''
        self._refresh()

    # ── Row actions ───────────────────────────────────────────────────────────

    def confirm_delete_expense(self, expense_id):
        popup = ConfirmPopup(
            title='Delete Expense',
            message='Delete this expense?\nThis cannot be undone.',
            on_confirm=lambda: self._do_delete(expense_id),
            confirm_label='Delete',
        )
        popup.open()

    def _do_delete(self, expense_id):
        queries.delete_expense(expense_id)
        self._refresh()

    def open_edit_expense(self, expense_id):
        expense = queries.get_expense_by_id(expense_id)
        if not expense:
            return
        popup = EditExpensePopup(expense_data=expense, on_save=self._refresh)
        popup.open()


def _expense_row_data(e, currency):
    """Build a single ExpenseItem RV data dict. Pulled out of HistoryScreen
    so the data-shape contract is colocated with the row-class definition
    and easy to find when ExpenseItem props change."""
    recurring = bool(e.get('is_recurring', False))
    paused = bool(e.get('recur_paused', False))
    ndd = e.get('recur_next_date', '') or ''
    note = e['note'] or ''

    if recurring and paused:
        sub_text = '⏸  Paused' + (f'  ·  {note}' if note else '')
    elif recurring and ndd:
        d = days_until(ndd)
        if d is None:
            nxt = 'Next: ' + display_date(ndd)
        elif d < 0:
            nxt = f'Overdue {abs(d)}d'
        elif d == 0:
            nxt = 'Next: Today'
        elif d <= 7:
            nxt = f'Next in {d}d'
        else:
            nxt = 'Next: ' + display_date(ndd)
        sub_text = (note + '  ·  ' + nxt) if note else nxt
    else:
        sub_text = note

    return {
        'viewclass': 'ExpenseItem',
        'expense_id': e['id'],
        'amount': format_currency(e['amount'], currency),
        'category': e['category'],
        'note': sub_text,
        'date_display': '',
        'cat_color': list(category_accent(e['color'])),
        'is_recurring': recurring,
        'height': _ROW_H,
    }
