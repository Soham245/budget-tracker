from datetime import datetime

from kivy.uix.screenmanager import Screen
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from kivy.metrics import dp

import db.queries as queries
from components.goal_card import GoalCard
from utils.popups import AppModal, ConfirmPopup
from utils.helpers import (
    format_currency, display_date, days_until, advance_by_interval,
    current_date, RECUR_MAX, goal_weekly_needed,
)

_RECUR_MAX = RECUR_MAX  # local alias for KV compat


class AddGoalPopup(AppModal):
    is_recurring = BooleanProperty(False)
    recur_value = NumericProperty(1)
    recur_unit = StringProperty('month')
    recur_preview = StringProperty('')

    def on_toggle_changed(self, active):
        if self.is_recurring != active:
            self.is_recurring = active
        if active:
            self.recur_value = 1
            self.recur_unit = 'month'
            self.ids.goal_recur_value_input.text = '1'
            self._update_preview()
        else:
            self.recur_preview = ''

    def set_recur_unit(self, unit):
        self.recur_unit = unit
        hi = RECUR_MAX.get(unit, 12)
        if int(self.recur_value) > hi:
            self.recur_value = hi
            self.ids.goal_recur_value_input.text = str(hi)
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
            amt_str = self.ids.recur_amount_input.text.strip()
            amount = float(amt_str) if amt_str else 0.0
            currency = queries.get_setting('currency') or '₹'
            next_date = advance_by_interval(current_date(), v, self.recur_unit)
            next_display = display_date(next_date)
            self.recur_preview = (
                f'Auto-contributes {format_currency(amount, currency)} every '
                f'{v} {unit_label}{plural}  (next: {next_display})'
            ) if amount > 0 else (
                f'Every {v} {unit_label}{plural}  (next: {next_display})'
            )
        except Exception:
            self.recur_preview = f'Every {v} {unit_label}{plural}'

    def save_goal(self):
        name = self.ids.name_input.text.strip()
        amount_str = self.ids.amount_input.text.strip()

        if not name:
            self.ids.error_label.text = 'Please enter a goal name.'
            return
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            self.ids.error_label.text = 'Enter a valid target amount.'
            return

        if self.is_recurring:
            try:
                recur_amount = float(self.ids.recur_amount_input.text.strip())
                if recur_amount <= 0:
                    raise ValueError
            except ValueError:
                self.ids.error_label.text = 'Enter a valid contribution amount.'
                return
            val_str = self.ids.goal_recur_value_input.text.strip()
            try:
                val = max(1, int(val_str))
            except (ValueError, TypeError):
                val = 1
            hi = RECUR_MAX.get(self.recur_unit, 12)
            val = min(val, hi)
            queries.add_goal(
                name, amount,
                is_recurring=1,
                recur_amount=recur_amount,
                recur_interval=val,
                recur_unit=self.recur_unit,
                recur_next_date=advance_by_interval(current_date(), val, self.recur_unit),
            )
        else:
            queries.add_goal(name, amount)
        self.dismiss()


class AddSavingsPopup(AppModal):
    goal_id = NumericProperty(0)
    goal_name = StringProperty('')

    def add_savings(self):
        try:
            amount = float(self.ids.amount_input.text.strip())
            if amount <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            self.ids.error_label.text = 'Enter a valid amount.'
            return
        queries.add_to_goal(self.goal_id, amount)
        self.dismiss()


class GoalsScreen(Screen):

    def on_enter(self, *args):
        self._refresh()

    # Accent palette — cycles per goal: green, violet, blue, amber
    _ACCENTS = [
        [0.42, 0.82, 0.52, 1],   # green
        [0.62, 0.50, 0.96, 1],   # violet
        [0.45, 0.66, 0.92, 1],   # blue
        [0.95, 0.78, 0.45, 1],   # amber
    ]

    def _refresh(self):
        container = self.ids.goals_list
        container.clear_widgets()
        goals = queries.get_all_goals()
        currency = queries.get_setting('currency') or '₹'


        # ── Top progress summary card ────────────────────────────────────────
        total_saved  = sum(g['saved']  for g in goals)
        total_target = sum(g['target'] for g in goals if g['target'] > 0)
        n_goals      = len(goals)
        overall_pct  = int((total_saved / total_target) * 100) if total_target > 0 else 0
        summary = self.ids.summary_card
        summary.saved_text       = format_currency(total_saved, currency)
        summary.target_text      = f'of {format_currency(total_target, currency)}' if total_target > 0 else ''
        summary.pct_text         = f'{overall_pct}%'
        summary.goals_count_text = f'{n_goals} goal{"s" if n_goals != 1 else ""}'
        if overall_pct >= 80:
            summary.pct_color = [0.42, 0.82, 0.52, 1]
        elif overall_pct >= 50:
            summary.pct_color = [0.45, 0.66, 0.92, 1]
        elif overall_pct >= 25:
            summary.pct_color = [0.62, 0.50, 0.96, 1]
        else:
            summary.pct_color = [0.95, 0.78, 0.45, 1]

        # ── Empty state ──────────────────────────────────────────────────────
        if not goals:
            from kivy.uix.boxlayout import BoxLayout as _Box
            from kivy.uix.label import Label as _Lbl
            from kivy.metrics import dp as _dp, sp as _sp
            box = _Box(orientation='vertical', size_hint_y=None,
                       height=_dp(120), spacing=_dp(4))
            box.add_widget(_Lbl(size_hint_y=None, height=_dp(36)))
            t = _Lbl(text='No goals yet', font_size=_sp(15), bold=True,
                     color=(0.7, 0.7, 0.8, 1), size_hint_y=None, height=_dp(28),
                     halign='center', valign='middle')
            s = _Lbl(text='Tap + to create your first goal', font_size=_sp(12),
                     color=(0.45, 0.45, 0.55, 1), size_hint_y=None, height=_dp(20),
                     halign='center', valign='top')
            for lbl in (t, s):
                lbl.text_size = (_dp(280), lbl.height)
            box.add_widget(t)
            box.add_widget(s)
            container.add_widget(box)
            container.height = _dp(120)
            self.ids.scroll_content.height = dp(4 + 20) + dp(92) + dp(10) + dp(120)
            self.ids.goals_scroll.scroll_y = 1
            return

        # ── Goal cards ───────────────────────────────────────────────────────
        for i, g in enumerate(goals):
            ratio = min(g['saved'] / g['target'], 1.0) if g['target'] > 0 else 0
            pct = int(ratio * 100)

            due_text = ''
            if g['deadline']:
                try:
                    dt = datetime.strptime(g['deadline'], '%Y-%m-%d')
                    due_text = 'Due ' + dt.strftime('%b %d, %y').replace(' 0', ' ')
                except Exception:
                    due_text = ''
                d = days_until(g['deadline'])
                if d is not None and not g['is_complete']:
                    if d < 0:
                        due_text = 'Deadline passed'
                    elif d == 0:
                        due_text = 'Due today'

            forecast_text = ''
            if not g['is_complete'] and g['deadline'] and g['saved'] < g['target']:
                forecast_text = goal_weekly_needed(g['saved'], g['target'], g['deadline'], currency)

            accent = self._ACCENTS[i % len(self._ACCENTS)]
            if g['is_complete']:
                accent = self._ACCENTS[0]

            container.add_widget(GoalCard(
                goal_id=g['id'],
                goal_name=g['name'],
                saved_text=(
                    f"{format_currency(g['saved'], currency)} of "
                    f"{format_currency(g['target'], currency)}"
                ),
                pct=pct,
                pct_text=f'{pct}%',
                ratio=ratio,
                due_text=due_text,
                forecast_text=forecast_text,
                accent_color=accent,
                is_complete=bool(g['is_complete']),
            ))

        # Explicit container + scroll heights \u2014 no minimum_height anywhere.
        CARD_H  = dp(204)
        SPACING = dp(14)
        list_h = n_goals * CARD_H + max(0, n_goals - 1) * SPACING
        container.height = list_h
        # scroll_content padding (4 top + 100 bottom) + summary(92)
        # + scroll_content spacing (14) + list
        self.ids.scroll_content.height = dp(4 + 100) + dp(92) + dp(14) + list_h
        # Reset scroll to top after rebuild
        self.ids.goals_scroll.scroll_y = 1

    def open_add_goal(self):
        popup = AddGoalPopup()
        popup.bind(on_dismiss=lambda _: self._refresh())
        popup.open()

    def open_add_savings(self, goal_id, goal_name):
        popup = AddSavingsPopup(goal_id=goal_id, goal_name=goal_name)
        popup.bind(on_dismiss=lambda _: self._refresh())
        popup.open()

    def confirm_delete_goal(self, goal_id):
        popup = ConfirmPopup(
            message='Delete this goal?\nThis cannot be undone.',
            on_confirm=lambda: self._do_delete_goal(goal_id),
        )
        popup.open()

    def _do_delete_goal(self, goal_id):
        queries.delete_goal(goal_id)
        self._refresh()
