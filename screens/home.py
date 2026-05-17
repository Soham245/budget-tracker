from kivy.uix.screenmanager import Screen
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.factory import Factory
from kivy.metrics import dp, sp
from kivy.clock import Clock

import db.queries as queries
from components.category_bar import CategoryBar          # noqa: F401
from components.recent_expense_row import RecentExpenseRow  # noqa: F401
from utils.helpers import (
    current_month, display_month, display_date,
    format_currency, hex_to_kivy_color, category_accent, days_remaining_in_month,
    days_elapsed_in_month, days_until, predict_overspend_days,
)


class HomeScreen(Screen):
    """Dashboard screen.

    Layout shape (top → bottom):
        app_bar  ·  FloatLayout(ScrollView + FAB)  ·  NavBar

    Sizing is driven by ``BoxLayout.minimum_height`` everywhere — no manual
    height arithmetic. Conditional sections (alerts, subscriptions card,
    goal alert) are *detached* from their parent when empty rather than
    collapsed to height 0, because a height-0 child still consumes the
    BoxLayout's spacing on both sides — that was the source of the
    invisible gaps. The FAB lives in the FloatLayout alongside (not
    inside) the ScrollView, so it cannot affect scroll-content size and
    cannot move with scroll.

    **Strong references vs. ``self.ids``** — ``self.ids`` stores
    ``kivy.weakproxy.WeakProxy`` values, NOT widget objects. Assigning
    ``x = self.ids.foo`` stores the proxy; once the underlying widget is
    detached from its parent and loses every other strong reference,
    Python collects it and the proxy turns stale (``ReferenceError`` on
    next attribute access).

    For widgets this screen detaches (``intel_strip``, ``subs_card``,
    ``goal_alert_label``, plus ``hero_card`` / ``categories_card`` /
    ``recent_card`` during the scroll_content rebuild) we therefore walk
    the tree once in ``on_kv_post`` and store the *actual* widget object.
    ``Widget.walk()`` yields real widgets (held strongly by their
    parent's children list at that moment), and ``WeakProxy.__eq__``
    delegates to the underlying widget so we can find the match by
    comparing each walked widget against the proxy out of ``self.ids``.

    ``self.ids`` is still used for widgets that never leave the tree
    (the labels and progress bar deep inside the hero card; the inner
    list containers inside categories/recent cards) — those stay alive
    via their parent's children list and their weakref stays valid.
    """

    def on_kv_post(self, base_widget):
        # Walk the tree once to convert the WeakProxy entries in self.ids
        # into strong widget references. WeakProxy.__eq__ delegates to the
        # widget, so a walked widget compares equal to the proxy that
        # wraps it. The returned value is the widget itself — assigning
        # it to an instance attribute creates a strong reference that
        # keeps the widget alive across detach/reattach cycles.
        def strong(proxy):
            for w in self.walk():
                if w == proxy:
                    return w
            raise RuntimeError(f'widget for {proxy!r} not found in tree')

        self._scroll = strong(self.ids.home_scroll)
        self._scroll_content = strong(self.ids.scroll_content)
        self._hero = strong(self.ids.hero_card)
        self._intel = strong(self.ids.intel_strip)
        self._subs = strong(self.ids.subs_card)
        self._cats = strong(self.ids.categories_card)
        self._recent = strong(self.ids.recent_card)
        self._goal_alert = strong(self.ids.goal_alert_label)

    def on_pre_enter(self, *args):
        # Pin scroll to the top before the screen is shown so the hero
        # card is at viewport top regardless of any drift from the
        # previous visit's layout passes.
        if hasattr(self, '_scroll'):
            self._scroll.scroll_y = 1

    def on_enter(self, *args):
        self._refresh()

    def _refresh(self):
        month = current_month()
        currency = queries.get_setting('currency') or '₹'
        income = float(queries.get_setting('monthly_income') or 0)
        total_spent = queries.get_monthly_total(month)
        remaining = income - total_spent

        self.ids.month_label.text = display_month(month).upper()
        self.ids.spent_label.text = format_currency(total_spent, currency)
        self.ids.income_label.text = f'spent  ·  of {format_currency(income, currency)}'

        if income <= 0:
            self.ids.remaining_amount.text = '—'
            self.ids.remaining_title.text = 'Budget'
            self.ids.remaining_amount.color = (0.5, 0.5, 0.62, 1)
        elif remaining >= 0:
            self.ids.remaining_amount.text = format_currency(remaining, currency)
            self.ids.remaining_title.text = 'Left'
            self.ids.remaining_amount.color = (0.42, 0.82, 0.52, 1)
        else:
            self.ids.remaining_amount.text = '-' + format_currency(abs(remaining), currency)
            self.ids.remaining_title.text = 'Over'
            self.ids.remaining_amount.color = (0.92, 0.38, 0.38, 1)

        ratio = (total_spent / income) if income > 0 else 0
        self.ids.budget_progress.ratio = min(ratio, 1.0)
        self.ids.budget_progress.over = ratio > 1.0

        days_left = days_remaining_in_month()
        if income <= 0:
            insight = 'Set your monthly income in Settings →'
            insight_color = (0.55, 0.55, 0.65, 1)
        elif remaining < 0:
            insight = f'Over budget by {format_currency(abs(remaining), currency)}'
            insight_color = (0.92, 0.38, 0.38, 1)
        elif days_left > 0:
            daily = remaining / days_left
            insight = f'On track  ·  {format_currency(daily, currency)}/day left to spend'
            insight_color = (0.42, 0.82, 0.52, 1)
        else:
            insight = 'Last day of the month — stay within budget!'
            insight_color = (1.0, 0.72, 0.2, 1)
        self.ids.insight_label.text = insight
        self.ids.insight_label.color = insight_color

        # Build dynamic sections; each tells us whether it has content.
        has_intel = self._build_budget_intelligence(month, currency, income, days_left)
        has_subs = self._refresh_subscriptions_card(currency)

        # Always-present sections.
        self._build_category_bars(month, currency)
        self._build_recent_expenses(month, currency)
        self._refresh_goal_alert(currency)

        # Re-attach only the sections that actually have something to show.
        self._rebuild_scroll_layout(has_intel, has_subs)

        # Pin scroll to the top. Set it immediately, then again after the
        # next frame — minimum_height propagates through the nested cards
        # over a layout pass, and a single immediate set can be undone by
        # the ScrollView's clamp logic when content height grows.
        self._scroll.scroll_y = 1
        Clock.schedule_once(self._reset_scroll, 0)

    # ── Scroll layout (dynamic section composition) ───────────────────────────

    def _rebuild_scroll_layout(self, has_intel, has_subs):
        """Compose scroll_content out of only the sections with content.

        We detach *all* sections, then re-add them top-to-bottom in the
        desired visual order. Re-adding without an index inserts at
        children[0]; in a vertical BoxLayout children[-1] is the topmost
        widget — so adding hero first, recent last, produces the right
        on-screen ordering.

        Sections that have no content (no alerts, no subscriptions) are
        simply left detached: the parent's dp(12) spacing only applies
        between widgets that are actually children.
        """
        container = self._scroll_content
        for w in list(container.children):
            container.remove_widget(w)

        order = [self._hero]
        if has_intel:
            order.append(self._intel)
        if has_subs:
            order.append(self._subs)
        order.extend([self._cats, self._recent])

        for w in order:
            container.add_widget(w)

    def _reset_scroll(self, _dt):
        self._scroll.scroll_y = 1

    # ── Subscriptions card ────────────────────────────────────────────────────

    def _refresh_subscriptions_card(self, currency):
        """Populate the dashboard Subscriptions card. Returns True if the
        card should be shown."""
        items = queries.get_all_recurring_expenses(category_name='Subscriptions')
        if not items:
            return False

        total = queries.get_monthly_recurring_total_for_category('Subscriptions')
        active = sum(1 for i in items if not i['recur_paused'])
        paused = sum(1 for i in items if i['recur_paused'])

        next_due_days = None
        for i in items:
            if i['recur_paused']:
                continue
            d = days_until(i['recur_next_date'])
            if d is None:
                continue
            if next_due_days is None or d < next_due_days:
                next_due_days = d

        parts = [f'{active} active']
        if paused:
            parts.append(f'{paused} paused')
        if next_due_days is not None:
            if next_due_days < 0:
                parts.append(f'{abs(next_due_days)}d overdue')
            elif next_due_days == 0:
                parts.append('due today')
            elif next_due_days == 1:
                parts.append('due tomorrow')
            else:
                parts.append(f'next in {next_due_days}d')

        self._subs.total_text = format_currency(total, currency)
        self._subs.summary_text = '  ·  '.join(parts)
        return True

    # ── Goal alert ────────────────────────────────────────────────────────────

    def _refresh_goal_alert(self, currency):
        """Set goal_alert_label text and attach/detach it from recent_card."""
        goals = queries.get_all_goals()
        urgent = [
            g for g in goals
            if not g['is_complete'] and g['deadline'] and days_until(g['deadline']) is not None
            and days_until(g['deadline']) <= 7
        ]
        urgent.sort(key=lambda g: g['deadline'])

        alert = ''
        if urgent:
            g = urgent[0]
            d = days_until(g['deadline'])
            left = g['target'] - g['saved']
            if d < 0:
                alert = f"Goal '{g['name']}' — deadline passed!"
            elif d == 0:
                alert = f"Goal '{g['name']}' due today! {format_currency(left, currency)} to go"
            else:
                alert = f"Goal '{g['name']}' due in {d}d — {format_currency(left, currency)} to go"

        lbl = self._goal_alert
        lbl.text = alert
        if alert:
            if lbl.parent is None:
                self._recent.add_widget(lbl)
        else:
            if lbl.parent is not None:
                lbl.parent.remove_widget(lbl)

    # ── Budget intelligence ───────────────────────────────────────────────────

    def _build_budget_intelligence(self, month, currency, income, days_left):
        """Populate intel_strip with budget warnings. Returns True if any."""
        container = self._intel
        container.clear_widgets()
        days_elapsed = days_elapsed_in_month()
        cats = queries.get_category_totals_for_month(month)
        warnings = []

        for cat in cats:
            if cat['budget'] <= 0 or cat['spent'] <= 0:
                continue
            days_to_exceed = predict_overspend_days(
                cat['spent'], cat['budget'], days_elapsed, days_left
            )
            if days_to_exceed is not None:
                if days_to_exceed == 0:
                    warnings.append((cat['name'], cat['color'],
                                     f"{cat['name']} budget exhausted!", True))
                elif days_to_exceed <= 5:
                    warnings.append((cat['name'], cat['color'],
                                     f"{cat['name']}: budget runs out in ~{days_to_exceed} days", True))
                elif days_to_exceed <= 12:
                    warnings.append((cat['name'], cat['color'],
                                     f"{cat['name']}: budget on track to exceed in {days_to_exceed}d", False))

        shown = warnings[:3]
        for _, color_hex, text, is_urgent in shown:
            col = category_accent(color_hex)
            container.add_widget(self._make_intel_row(text, col, is_urgent))
        return len(shown) > 0

    def _make_intel_row(self, text, color, urgent):
        row = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(46),
            padding=(dp(16), dp(12)),
            spacing=dp(10),
        )
        alpha = 0.16 if urgent else 0.10
        with row.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(color[0], color[1], color[2], alpha)
            bg = RoundedRectangle(pos=row.pos, size=row.size, radius=[dp(14)])
        row.bind(pos=lambda w, v, _bg=bg: setattr(_bg, 'pos', v))
        row.bind(size=lambda w, v, _bg=bg: setattr(_bg, 'size', v))
        lbl = Label(
            text=text,
            font_size=sp(12.5),
            bold=urgent,
            color=(color[0], color[1], color[2], 1) if urgent
                  else (color[0] * 0.55 + 0.40, color[1] * 0.55 + 0.40, color[2] * 0.55 + 0.45, 1),
            halign='left',
            valign='middle',
        )
        lbl.bind(size=lambda w, v: setattr(w, 'text_size', v))
        row.add_widget(lbl)
        return row

    # ── Category bars ─────────────────────────────────────────────────────────

    def _build_category_bars(self, month, currency):
        container = self.ids.category_bars
        container.clear_widgets()
        active = [c for c in queries.get_category_totals_for_month(month) if c['spent'] > 0]
        active.sort(key=lambda c: c['spent'], reverse=True)

        if not active:
            container.add_widget(self._empty_label('No spending recorded yet this month'))
            return

        max_spent = max(c['spent'] for c in active)
        for cat in active:
            ratio = cat['spent'] / max_spent if max_spent > 0 else 0
            container.add_widget(Factory.CategoryBar(
                cat_name=cat['name'],
                cat_amount=format_currency(cat['spent'], currency),
                cat_color=category_accent(cat['color']),
                bar_ratio=ratio,
                over_budget=cat['budget'] > 0 and cat['spent'] > cat['budget'],
            ))

    # ── Recent expenses ───────────────────────────────────────────────────────

    def _build_recent_expenses(self, month, currency):
        container = self.ids.recent_list
        container.clear_widgets()
        recent = queries.get_expenses_for_month(month)[:4]

        if not recent:
            container.add_widget(self._empty_label('No expenses yet  —  tap + to add one'))
            return

        for idx, e in enumerate(recent):
            container.add_widget(Factory.RecentExpenseRow(
                expense_id=e['id'],
                exp_category=e['category'],
                exp_amount=format_currency(e['amount'], currency),
                exp_note=e['note'] or '',
                exp_date=display_date(e['date']),
                exp_color=category_accent(e['color']),
            ))
            if idx < len(recent) - 1:
                container.add_widget(self._make_divider())

    def _make_divider(self):
        d = BoxLayout(size_hint_y=None, height=dp(1))
        with d.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(0.14, 0.16, 0.26, 1)
            r = Rectangle(pos=d.pos, size=d.size)
        d.bind(pos=lambda w, v, _r=r: setattr(_r, 'pos', v))
        d.bind(size=lambda w, v, _r=r: setattr(_r, 'size', v))
        return d

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_label(text):
        lbl = Label(
            text=text,
            font_size=sp(13),
            color=(0.45, 0.45, 0.55, 1),
            size_hint_y=None,
            height=dp(40),
            halign='center',
        )
        lbl.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        return lbl
