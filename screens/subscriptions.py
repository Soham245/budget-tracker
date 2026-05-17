from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import (
    StringProperty, NumericProperty, ListProperty, BooleanProperty,
)
from kivy.metrics import dp

import db.queries as queries
from utils.helpers import (
    format_currency, category_accent, humanize_recur, next_due_label,
    days_until,
)


# ── Tappable subscription row ─────────────────────────────────────────────────

class SubscriptionRow(ButtonBehavior, BoxLayout):
    """Single recurring item. Tap opens the full expense detail page.

    Visual: category accent bar, name + frequency, due-pill, amount.
    Press state tints the row to match the rest of the app's row patterns.
    """
    expense_id = NumericProperty(0)
    title = StringProperty('')
    subtitle = StringProperty('')
    category_name = StringProperty('')  # drives the leading category icon
    amount_text = StringProperty('')
    due_text = StringProperty('')
    accent_color = ListProperty([0.75, 0.77, 0.95, 1])
    is_paused = BooleanProperty(False)
    is_overdue = BooleanProperty(False)

    def on_release(self):
        app = App.get_running_app()
        if app and self.expense_id:
            app.open_expense(self.expense_id, return_to='subscriptions')


# ── Screen ────────────────────────────────────────────────────────────────────

class SubscriptionsScreen(Screen):
    """Dedicated full-screen manager for recurring expenses ('subscriptions').

    Pure read+drill view: tapping any row hands off to ExpenseDetailScreen
    for edit/pause/delete actions, so the recurring engine stays in one place.
    """
    monthly_total_text = StringProperty('—')
    summary_text = StringProperty('')
    has_upcoming = BooleanProperty(False)
    has_active = BooleanProperty(False)
    has_paused = BooleanProperty(False)
    is_empty = BooleanProperty(True)

    def on_pre_enter(self, *args):
        self._refresh()

    # Single source of truth for what counts as a "subscription" — items in
    # this category that are recurring. General recurring (rent, EMI, etc.)
    # lives in History and is reachable via expense detail.
    SUBSCRIPTION_CATEGORY = 'Subscriptions'

    def _refresh(self):
        currency = queries.get_setting('currency') or '₹'
        items = queries.get_all_recurring_expenses(
            category_name=self.SUBSCRIPTION_CATEGORY,
        )

        self.monthly_total_text = format_currency(
            queries.get_monthly_recurring_total_for_category(
                self.SUBSCRIPTION_CATEGORY,
            ),
            currency,
        )

        active = [i for i in items if not i['recur_paused']]
        paused = [i for i in items if i['recur_paused']]
        self.summary_text = (
            f'{len(active)} active · {len(paused)} paused' if items else
            'No subscriptions yet'
        )

        self.has_active = bool(active)
        self.has_paused = bool(paused)
        self.is_empty = not items

        # Upcoming = active items due within 7 days (including overdue)
        upcoming = []
        for i in active:
            d = days_until(i['recur_next_date'])
            if d is not None and d <= 7:
                upcoming.append((d, i))
        upcoming.sort(key=lambda t: t[0])
        self.has_upcoming = bool(upcoming)

        self._build_upcoming([t[1] for t in upcoming], currency)
        self._build_active_by_category(active, currency)
        self._build_paused(paused, currency)

    # ── Section builders ──────────────────────────────────────────────────────

    def _build_upcoming(self, upcoming_items, currency):
        container = self.ids.upcoming_container
        container.clear_widgets()
        if not upcoming_items:
            container.height = 0
            return
        for item in upcoming_items[:6]:  # cap to keep section breathable
            container.add_widget(self._make_row(item, currency))
        container.height = self._stack_height(len(upcoming_items[:6]))

    def _build_active_by_category(self, active, currency):
        """Active subscriptions stack flat under the ACTIVE section header.
        We dropped the per-category subheader strip ("• SUBSCRIPTIONS · N") —
        every row in this screen is already a subscription, so that metadata
        was redundant clutter. Name kept for caller compatibility."""
        container = self.ids.active_container
        container.clear_widgets()
        if not active:
            container.height = 0
            return
        for item in active:
            container.add_widget(self._make_row(item, currency))
        container.height = self._stack_height(len(active))

    def _build_paused(self, paused, currency):
        container = self.ids.paused_container
        container.clear_widgets()
        if not paused:
            container.height = 0
            return
        for item in paused:
            container.add_widget(self._make_row(item, currency))
        container.height = self._stack_height(len(paused))

    # ── Row factory ───────────────────────────────────────────────────────────

    def _make_row(self, item, currency):
        accent = category_accent(item['color'])
        freq = humanize_recur(item['recur_interval'], item['recur_unit'])
        note = item['note'].strip() if item['note'] else ''
        # Title prefers the user's note (e.g. "Netflix") and falls back to
        # the category name. Subtitle shows category + cadence.
        if note:
            title = note
            subtitle = f'{item["category"]}  ·  {freq}'
        else:
            title = item['category']
            subtitle = freq
        due = next_due_label(item['recur_next_date'], paused=item['recur_paused'])
        d = days_until(item['recur_next_date']) if not item['recur_paused'] else None
        return SubscriptionRow(
            expense_id=item['id'],
            title=title,
            subtitle=subtitle,
            category_name=item['category'],
            amount_text=format_currency(item['amount'], currency),
            due_text=due,
            accent_color=list(accent),
            is_paused=item['recur_paused'],
            is_overdue=(d is not None and d < 0),
            size_hint_y=None,
            height=dp(64),
        )

    @staticmethod
    def _stack_height(n_rows):
        if n_rows <= 0:
            return 0
        return dp(64) * n_rows + dp(10) * (n_rows - 1)

    # ── Actions ───────────────────────────────────────────────────────────────

    def go_back(self):
        App.get_running_app().go_to('home')
