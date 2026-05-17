from kivy.animation import Animation
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import (
    ListProperty, NumericProperty, BooleanProperty, StringProperty,
)
from kivy.metrics import dp, sp

import db.queries as queries
from utils.helpers import (
    current_month, format_currency, days_elapsed_in_month,
    days_remaining_in_month, category_accent,
)


# ── Animation easing tokens (kept lightweight) ────────────────────────────────
_BAR_ANIM_DURATION   = 0.42
_SCORE_ANIM_DURATION = 0.55
_VALUE_ANIM_DURATION = 0.55


# ── Month bar widget ──────────────────────────────────────────────────────────

class MonthBar(Widget):
    """Single vertical bar in the 6-month chart.

    `ratio` is the target fill (0–1, height relative to widget). `anim_ratio`
    is the visually-rendered fill — animated from 0 to `ratio` on each rebuild
    so bars grow upward on entry instead of popping in. The selected bar gets
    a faint outer glow drawn behind the fill."""
    ratio       = NumericProperty(0.0)
    anim_ratio  = NumericProperty(0.0)
    is_current  = BooleanProperty(False)
    is_selected = BooleanProperty(False)

    def on_ratio(self, *a):       self._safe_redraw()
    def on_anim_ratio(self, *a):  self._safe_redraw()
    def on_is_current(self, *a):  self._safe_redraw()
    def on_is_selected(self, *a): self._safe_redraw()
    def on_size(self, *a):        self._safe_redraw()
    def on_pos(self, *a):         self._safe_redraw()

    def _safe_redraw(self):
        if self.canvas is None:
            return
        self._redraw()

    def _redraw(self):
        from kivy.graphics import Color, RoundedRectangle, Line
        self.canvas.before.clear()
        with self.canvas.before:
            # Track (background slot) — always fills the full widget bounds
            Color(0.12, 0.14, 0.22, 1)
            RoundedRectangle(
                pos=(self.x + dp(3), self.y),
                size=(self.width - dp(6), self.height),
                radius=[dp(7)],
            )

            r = max(0.0, min(self.anim_ratio, 1.0))
            bar_h = self.height * r
            if r > 0 and bar_h < dp(4):
                bar_h = dp(4)
            if bar_h <= 0:
                return

            # Fill color
            if self.is_selected:
                Color(0.97, 0.85, 0.58, 1)
            elif self.is_current:
                Color(0.80, 0.82, 0.99, 1)
            else:
                Color(0.40, 0.42, 0.66, 0.50)

            RoundedRectangle(
                pos=(self.x + dp(3), self.y),
                size=(self.width - dp(6), bar_h),
                radius=[dp(7)],
            )

            # Selected-state emphasis — a thin amber ring AROUND the FILL only.
            # Everything stays strictly inside the widget bounds (no protrusion
            # above/below), so selecting a bar can never paint pixels into the
            # neighbouring section and create perceived layout drift.
            if self.is_selected:
                Color(0.97, 0.85, 0.58, 0.55)
                Line(
                    rounded_rectangle=(
                        self.x + dp(3), self.y,
                        self.width - dp(6), bar_h, dp(7),
                    ),
                    width=1.4,
                )


# ── Chart column (clickable) ──────────────────────────────────────────────────

class ChartColumn(ButtonBehavior, BoxLayout):
    """Vertical column: bar + month label. Tappable."""
    year_month = StringProperty('')

    def on_release(self):
        app = App.get_running_app()
        if app is None or app.root is None:
            return
        try:
            screen = app.root.get_screen('analytics')
        except Exception:
            return
        screen.select_month(self.year_month)


# ── 6-month bar chart ─────────────────────────────────────────────────────────

class SpendingChart(BoxLayout):
    """6-month spending chart.

    Layout stability rules:
      • Widget tree is rebuilt ONLY when `months_data` changes (full data
        refresh). Selecting a different month never recreates widgets — it
        just toggles `is_selected` and re-paints labels in place. This keeps
        the chart's geometry perfectly locked across selections.
      • Every column is identical in size, every label has a fixed dp(18)
        height and fixed sp(10) font size — typography never grows on select
        (only color / bold flip), so no measurable text-metric drift.
      • The bar-grow animation only fires on data refresh, not on selection,
        so tapping a bar can't restart the chart-wide animation either."""
    months_data    = ListProperty([])
    selected_month = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Mirror-cached widget references — populated by _rebuild and reused
        # by _apply_selection so we never have to walk the widget tree.
        self._columns = []   # list of (year_month, ChartColumn, MonthBar, Label)
        self._signature = () # used to detect "real" data changes

    def on_months_data(self, *a):
        self._maybe_rebuild()

    # NOTE: no on_size handler. The chart is a BoxLayout; resizing it
    # propagates to its column children automatically, and each MonthBar's
    # own on_size already triggers a canvas redraw at the new dimensions.
    # Listening to on_size here would either rebuild the widget tree (which
    # restarts the bar-grow animation mid-resize) or do redundant work.

    def on_selected_month(self, *a):
        self._apply_selection()

    # ── Data-change rebuild (rare) ───────────────────────────────────────────
    def _maybe_rebuild(self):
        sig = tuple((m['year_month'], m['total']) for m in self.months_data)
        if sig == self._signature:
            return
        self._signature = sig
        self._rebuild()

    def _rebuild(self):
        self.clear_widgets()
        self._columns = []
        if not self.months_data:
            return
        max_total = max(m['total'] for m in self.months_data) or 1

        bars = []
        for m in self.months_data:
            ym     = m['year_month']
            is_cur = m.get('is_current', False)
            is_sel = (ym == self.selected_month)

            col = ChartColumn(orientation='vertical', spacing=dp(6),
                              year_month=ym)

            bar = MonthBar(
                ratio=m['total'] / max_total,
                is_current=is_cur,
                is_selected=is_sel,
            )
            col.add_widget(bar)
            bars.append(bar)

            # Month label — typography is INVARIANT across states. Only color
            # and bold flip on selection, both of which leave the texture
            # dimensions effectively unchanged at this size.
            lbl = Label(
                text=m['label'],
                font_size=sp(10),
                color=self._label_color(is_sel, is_cur),
                size_hint_y=None,
                height=dp(18),
                halign='center',
                bold=is_sel or is_cur,
            )
            lbl.bind(size=lambda w, v: setattr(w, 'text_size', v))
            col.add_widget(lbl)

            self.add_widget(col)
            self._columns.append((ym, col, bar, lbl))

        # Bar-grow animation fires only on real data refresh.
        for bar in bars:
            target = bar.ratio
            bar.anim_ratio = 0
            Animation(anim_ratio=target,
                      d=_BAR_ANIM_DURATION, t='out_cubic').start(bar)

    # ── Selection-only update (no widget churn, no animation restart) ────────
    def _apply_selection(self):
        for ym, _col, bar, lbl in self._columns:
            is_sel = (ym == self.selected_month)
            if bar.is_selected != is_sel:
                bar.is_selected = is_sel
            lbl.color = self._label_color(is_sel, bar.is_current)
            lbl.bold  = is_sel or bar.is_current

    @staticmethod
    def _label_color(is_sel, is_cur):
        if is_sel: return (0.97, 0.85, 0.58, 1)
        if is_cur: return (0.80, 0.82, 0.99, 1)
        return (0.42, 0.44, 0.55, 1)


# ── Score progress bar ────────────────────────────────────────────────────────

class ScoreProgressBar(Widget):
    """Thin horizontal bar representing the health score (0–100).

    `ratio` is the data-driven target; `anim_ratio` is what's actually drawn
    so callers can animate the fill via Animation(anim_ratio=...)."""
    ratio      = NumericProperty(0.0)
    anim_ratio = NumericProperty(0.0)
    bar_color  = ListProperty([0.75, 0.77, 0.95, 1])

    def on_ratio(self, *a):
        # When ratio changes, restart the fill animation from zero.
        Animation.cancel_all(self, 'anim_ratio')
        self.anim_ratio = 0
        Animation(anim_ratio=self.ratio,
                  d=_SCORE_ANIM_DURATION, t='out_cubic').start(self)

    def on_anim_ratio(self, *a): self._safe_redraw()
    def on_bar_color(self, *a):  self._safe_redraw()
    def on_size(self, *a):       self._safe_redraw()
    def on_pos(self, *a):        self._safe_redraw()

    def _safe_redraw(self):
        if self.canvas is None:
            return
        self._redraw()

    def _redraw(self):
        from kivy.graphics import Color, RoundedRectangle
        self.canvas.before.clear()
        c = self.bar_color
        radius = self.height / 2
        with self.canvas.before:
            # Track
            Color(0.14, 0.16, 0.26, 1)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])

            fill_w = self.width * max(0.0, min(self.anim_ratio, 1.0))
            if fill_w > 0:
                # Soft glow tucked just under the fill — barely visible but
                # makes the line feel lit rather than painted on.
                Color(c[0], c[1], c[2], 0.18)
                RoundedRectangle(
                    pos=(self.x, self.y - dp(1)),
                    size=(fill_w, self.height + dp(2)),
                    radius=[radius + dp(1)],
                )
                Color(c[0], c[1], c[2], 1)
                RoundedRectangle(pos=self.pos, size=(fill_w, self.height),
                                 radius=[radius])


# ── Financial Health card ─────────────────────────────────────────────────────

class HealthScoreCard(BoxLayout):
    """Prominent summary card: score + status + two short reason bullets.

    `score` is animated via `display_score` so the number ticks up on entry
    rather than appearing all at once."""
    score          = NumericProperty(0)
    display_score  = NumericProperty(0)
    status         = StringProperty('—')
    status_color   = ListProperty([0.75, 0.77, 0.95, 1])
    status_icon    = StringProperty('')  # trending_flat (default)
    summary_a      = StringProperty('')
    summary_b      = StringProperty('')

    def on_score(self, *a):
        Animation.cancel_all(self, 'display_score')
        self.display_score = 0
        Animation(display_score=self.score,
                  d=_SCORE_ANIM_DURATION, t='out_cubic').start(self)


# ── Insight row ───────────────────────────────────────────────────────────────

class InsightRow(BoxLayout):
    """Single tinted insight card. Visuals defined in KV (analytics.kv).

    `icon_glyph` is a MaterialIcons codepoint that hints the insight's tone
    (alert, lightbulb, trending_up, etc.) — small leading affordance instead
    of the older heavy left-accent strip."""
    insight_text = StringProperty('')
    accent_color = ListProperty([0.75, 0.77, 0.95, 1])
    icon_glyph   = StringProperty('')  # info_outline


# ── Stacked category distribution bar ─────────────────────────────────────────

class StackedCategoryBar(Widget):
    """Single thin horizontal bar split into colored segments by category share."""
    segments = ListProperty([])  # list of (ratio_0_1, [r,g,b,a])

    def on_segments(self, *a): self._safe_redraw()
    def on_size(self, *a):     self._safe_redraw()
    def on_pos(self, *a):      self._safe_redraw()

    def _safe_redraw(self):
        if self.canvas is None:
            return
        from kivy.graphics import (
            Color, RoundedRectangle, StencilPush, StencilUse, StencilUnUse,
            StencilPop, Rectangle,
        )
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.14, 0.16, 0.26, 1)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.height / 2])
            StencilPush()
            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.height / 2])
            StencilUse()
            x = self.x
            for ratio, c in self.segments:
                w = self.width * max(0.0, min(ratio, 1.0))
                if w <= 0:
                    continue
                Color(c[0], c[1], c[2], 1)
                Rectangle(pos=(x, self.y), size=(w, self.height))
                x += w
            StencilUnUse()
            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.height / 2])
            StencilPop()


class CategoryLegendRow(ButtonBehavior, BoxLayout):
    """One row in the category breakdown legend: name, %, amount + a thin
    progress fill at the bottom showing this category's share of the total.

    Tapping a row deep-links into the History screen pre-filtered to this
    category (using the same active_filter chip History uses internally),
    showing every transaction that contributed to this row's amount."""
    cat_name    = StringProperty('')
    cat_color   = ListProperty([0.5, 0.5, 0.5, 1])
    pct_text    = StringProperty('')
    amount_text = StringProperty('')
    share       = NumericProperty(0.0)  # 0–1 — drives the mini progress fill

    def on_release(self):
        app = App.get_running_app()
        if app is None or app.root is None or not self.cat_name:
            return
        try:
            history = app.root.get_screen('history')
            analytics = app.root.get_screen('analytics')
        except Exception:
            return
        # Pre-seed History with this category as the active filter chip,
        # and with the month currently being viewed in Analytics so the
        # filtered rows are the same ones that drove this legend row's
        # amount. History.on_enter consumes both pre-seeds once.
        month = getattr(analytics, 'selected_month', '') or ''
        history.deep_link(category=self.cat_name, month=month or None)
        app.go_to('history')


# ── Animated counter label (Total Spent) ──────────────────────────────────────

class CounterLabel(Label):
    """Label whose displayed currency value animates from 0 → `value`.

    `currency` is the prefix symbol; `value` is the actual amount. Use it
    anywhere the user benefits from a counting-up feel instead of a sudden
    number swap."""
    value          = NumericProperty(0.0)
    display_value  = NumericProperty(0.0)
    currency       = StringProperty('₹')

    def on_value(self, *a):
        Animation.cancel_all(self, 'display_value')
        # Force a text refresh even if display_value is already 0 (Kivy skips
        # the on_display_value callback when the value doesn't actually change).
        self.display_value = 0.0
        self.text = f'{self.currency}0.00'
        Animation(display_value=self.value,
                  d=_VALUE_ANIM_DURATION, t='out_cubic').start(self)

    def on_display_value(self, *a):
        self.text = f'{self.currency}{self.display_value:,.2f}'


# ── Analytics screen ──────────────────────────────────────────────────────────

class AnalyticsScreen(Screen):
    selected_month       = StringProperty('')
    selected_month_label = StringProperty('This Month')

    def on_enter(self, *args):
        if not self.selected_month:
            self.selected_month = current_month()
        self._refresh_data()

    def select_month(self, year_month):
        self.selected_month = year_month
        from utils.helpers import display_month
        self.selected_month_label = display_month(year_month)
        self.ids.spend_chart.selected_month = year_month
        self._refresh_cards()

    def _refresh_data(self):
        month = self.selected_month or current_month()
        months_raw = queries.get_last_n_months_totals(6)
        for m in months_raw:
            m['is_current'] = (m['year_month'] == current_month())
        self.ids.spend_chart.months_data    = months_raw
        self.ids.spend_chart.selected_month = month

        from utils.helpers import display_month
        self.selected_month_label = display_month(month)
        self._refresh_cards()

    def _refresh_cards(self):
        month    = self.selected_month or current_month()
        currency = queries.get_setting('currency') or '₹'
        income   = float(queries.get_setting('monthly_income') or 0)

        total        = queries.get_monthly_total(month)
        days_elapsed = days_elapsed_in_month(month)
        days_left    = days_remaining_in_month(month)

        # TOTAL SPENT — animate the counter up from 0
        total_lbl = self.ids.total_card_value
        total_lbl.currency = currency
        total_lbl.value    = float(total)

        if days_elapsed > 0:
            daily_avg = total / days_elapsed
            self.ids.daily_avg_value.text = format_currency(daily_avg, currency)
        else:
            daily_avg = 0
            self.ids.daily_avg_value.text = '—'

        prev_month  = self._prev_month(month)
        prev_total  = queries.get_monthly_total(prev_month)
        if prev_total > 0:
            delta_pct = ((total - prev_total) / prev_total) * 100
            sign = '+' if delta_pct > 0 else ''
            self.ids.vs_last_value.text  = f'{sign}{delta_pct:.0f}%'
            self.ids.vs_last_value.color = (
                (0.95, 0.42, 0.42, 1) if delta_pct > 0 else (0.45, 0.85, 0.55, 1)
            )
        else:
            self.ids.vs_last_value.text  = '—'
            self.ids.vs_last_value.color = (0.55, 0.55, 0.65, 1)

        # ── Category breakdown (stacked bar + legend) ─────────────────────────
        self._build_category_breakdown(month, currency)

        # ── Chart budget caption (sum of category budgets) ───────────────────
        cats_all = queries.get_category_totals_for_month(month)
        budget_total = sum(c['budget'] for c in cats_all if c['budget'] > 0)
        if budget_total > 0:
            self.ids.chart_budget_label.text = (
                f'Budget {self._short_money(budget_total, currency)} per month'
            )
        else:
            self.ids.chart_budget_label.text = ''

        # ── Financial intelligence (health + insights) ─────────────────────────
        from utils.intelligence import gather_data, compute_health_score, top_insights
        data   = gather_data(month, income)
        health = compute_health_score(data)

        card = self.ids.health_score_card
        card.score        = health['score']
        card.status       = health['status']
        card.status_color = health['color']
        card.status_icon  = self._icon_for_status(health['score'])
        reasons           = health['reasons']
        card.summary_a    = reasons[0] if len(reasons) > 0 else ''
        card.summary_b    = reasons[1] if len(reasons) > 1 else ''

        # Top 3 insights (was 4) — user spec calls for the most-valuable few,
        # not a wall of cards.
        insights = top_insights(data, currency, n=3)
        self._build_insights(insights)

        # ── Recurring total card ──────────────────────────────────────────────
        # The card's physical slot in the scroll content is ALWAYS dp(56) —
        # we only toggle `opacity` to show/hide. If we shrank the height when
        # switching to a past month, scroll_content.height would change and
        # the ScrollView would re-position everything above (chart card,
        # this-month section, etc.), giving the user a 10-ish dp drift on
        # every selection. Keeping the slot constant pins the page in place.
        rec_total = data['rec_total'] if month == current_month() else 0
        if rec_total > 0:
            self.ids.recurring_card.opacity = 1
            self.ids.recurring_total_value.text = format_currency(rec_total, currency)
        else:
            self.ids.recurring_card.opacity = 0
            self.ids.recurring_total_value.text = ''

        # Final pass: every variable section gets an explicit height.
        self._recompute_section_heights()

    @staticmethod
    def _icon_for_status(score):
        # MaterialIcons codepoints for the top-right badge on the health card.
        if score >= 80: return chr(0xE8D0)   # stars
        if score >= 60: return chr(0xE86C)   # check_circle
        if score >= 40: return chr(0xE002)   # warning
        return chr(0xE000)                   # error

    @staticmethod
    def _short_money(amount, currency='₹'):
        if amount >= 100000:
            return f'{currency}{amount / 100000:.1f}L'
        if amount >= 1000:
            return f'{currency}{amount / 1000:.1f}k'
        return f'{currency}{int(amount)}'

    @staticmethod
    def _prev_month(year_month):
        year, mo = int(year_month[:4]), int(year_month[5:7])
        if mo == 1:
            return f'{year - 1}-12'
        return f'{year}-{mo - 1:02d}'

    def _build_category_breakdown(self, month, currency):
        cats = queries.get_category_totals_for_month(month)
        cats = [c for c in cats if c['spent'] > 0]
        cats.sort(key=lambda c: c['spent'], reverse=True)
        total = sum(c['spent'] for c in cats)

        bar = self.ids.cat_bar
        legend = self.ids.cat_legend
        legend.clear_widgets()

        # Tighter row rhythm + extra dp(4) for the mini share bar that's now
        # baked into each legend row (see <CategoryLegendRow> in KV).
        ROW_H = dp(38)
        ROW_SPACING = dp(8)

        if total <= 0:
            bar.segments = []
            empty = Label(
                text='No spending logged yet this month',
                font_size=sp(13),
                color=(0.50, 0.52, 0.62, 1),
                size_hint_y=None,
                height=dp(28),
                halign='left',
                valign='middle',
                text_size=(dp(280), dp(28)),
            )
            legend.add_widget(empty)
            legend.height = dp(28)
            return 1, dp(28)

        bar.segments = [
            (c['spent'] / total, category_accent(c['color'])) for c in cats
        ]

        n = len(cats)
        for c in cats:
            share = c['spent'] / total
            pct = share * 100
            legend.add_widget(CategoryLegendRow(
                cat_name=c['name'],
                cat_color=category_accent(c['color']),
                pct_text=f'{pct:.0f}%' if pct >= 1 else '<1%',
                amount_text=format_currency(c['spent'], currency),
                share=share,
            ))
        legend_h = n * ROW_H + max(0, n - 1) * ROW_SPACING
        legend.height = legend_h
        return n, legend_h

    # Locked total — chosen to comfortably hold the largest possible content
    # for any month (max 3 insight pills + max ~10 categories + recurring +
    # all fixed cards + paddings). Concretely:
    #   212 chart + 210 this-month + 268 health
    # + 282 insights (3 pills cap) + 542 cat (10 rows cap)
    # + 56 recurring + 5*14 spacing + 4+100 padding ≈ dp(1744)
    # Round up to dp(1780) for headroom. Sections size to actual content
    # within this budget; any slack lands at the bottom of scroll_content,
    # below the recurring card and inside the bottom-pad, where it's hidden.
    _SCROLL_CONTENT_LOCK = dp(1780)

    def _recompute_section_heights(self):
        """Variable sections size to their content; the scroll_content total
        is LOCKED to a constant. This keeps the ScrollView's content origin
        invariant across month selections — chart_card and every other top-
        of-page widget stay pinned to the same screen y on every tap."""
        # Variable section sizing (these still adapt for proper internal look)
        # cat_section: padding_top(18) + label(18) + spacing(14) + bar(8)
        #            + spacing(14) + legend + padding_bottom(18)
        legend_h = self.ids.cat_legend.height
        self.ids.cat_section.height = dp(18 + 18 + 14 + 8 + 14 + 18) + legend_h
        # insights_section: label(18) + spacing(12) + container
        self.ids.insights_section.height = (
            dp(18) + dp(12) + self.ids.insights_container.height
        )

        # Locked total — see class doc above.
        self.ids.scroll_content.height = self._SCROLL_CONTENT_LOCK

        # Belt-and-braces: re-pin the ScrollView to the top on the next frame
        # in case any intermediate layout pass nudged scroll_y.
        from kivy.clock import Clock
        Clock.schedule_once(self._pin_scroll_top, 0)

    def _pin_scroll_top(self, *a):
        sv = self._find_scrollview()
        if sv is not None and sv.scroll_y != 1.0:
            sv.scroll_y = 1.0

    def _find_scrollview(self):
        if getattr(self, '_cached_sv', None) is not None:
            return self._cached_sv
        stack = list(self.children)
        while stack:
            w = stack.pop()
            if w.__class__.__name__ == 'ScrollView':
                self._cached_sv = w
                return w
            stack.extend(w.children)
        return None

    def _build_insights(self, insights):
        container = self.ids.insights_container
        container.clear_widgets()

        # Slightly desaturated tints — more "premium" than the punchy primaries
        # used elsewhere, so the insight row feels like ambient context rather
        # than an alarm panel.
        _COLORS = {
            'low':    [0.50, 0.82, 0.62, 1],
            'ok':     [0.75, 0.77, 0.95, 1],
            'warn':   [0.95, 0.78, 0.45, 1],
            'danger': [0.95, 0.46, 0.46, 1],
            'info':   [0.62, 0.66, 0.85, 1],
        }
        _ICONS = {
            'low':    '',  # trending_flat-ish (positive but neutral)
            'ok':     '',  # check
            'warn':   '',  # warning
            'danger': '',  # error
            'info':   '',  # lightbulb_outline
        }

        # Every insight pill is locked to the same height — the only thing
        # that varies between cards is the text, color theme, and icon glyph.
        # Long text wraps within the fixed box (handled in <InsightRow> KV).
        PILL_H  = dp(76)
        SPACING = dp(12)

        total_h = 0
        for i, (kind, text) in enumerate(insights):
            row = InsightRow(
                insight_text=text,
                accent_color=_COLORS.get(kind, _COLORS['info']),
                icon_glyph=_ICONS.get(kind, _ICONS['info']),
            )
            container.add_widget(row)
            total_h += PILL_H
            if i > 0:
                total_h += SPACING

        container.height = total_h
