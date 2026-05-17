from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.properties import StringProperty, ListProperty, NumericProperty, BooleanProperty
from kivy.metrics import dp


def _scroll_active(touch):
    """Return True if any ScrollView parent has entered scroll mode for this touch."""
    for val in touch.ud.values():
        if isinstance(val, dict) and val.get('mode') == 'scroll':
            return True
    return False


class ExpenseItem(RecycleDataViewBehavior, BoxLayout):
    """Tappable expense row used in the history RecycleView.

    No ButtonBehavior — returning False from on_touch_down leaves the outer
    ScrollView in full control of scroll gestures.

    touch.grab(self) is used purely for cleanup: it guarantees on_touch_move
    and on_touch_up reach this widget via the grab path even after the
    ScrollView steals the gesture, so 'state' is always reset.
    """
    expense_id   = NumericProperty(0)
    amount       = StringProperty('')
    category     = StringProperty('')
    note         = StringProperty('')
    date_display = StringProperty('')
    cat_color    = ListProperty([0.5, 0.5, 0.5, 1])
    is_recurring = BooleanProperty(False)
    state        = StringProperty('normal')   # 'normal' | 'down' — drives KV press style

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._is_tap = False
        self._tap_ox = 0.0
        self._tap_oy = 0.0

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self._is_tap = False
        self.state = 'normal'
        return super().refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)          # guarantees move/up delivery even after ScrollView steals
            self._tap_ox = touch.x
            self._tap_oy = touch.y
            self._is_tap = True
            self.state = 'down'
        return False                  # don't consume — ScrollView keeps scroll ownership

    def on_touch_move(self, touch):
        if touch.grab_current is self and self._is_tap:
            dx = abs(touch.x - self._tap_ox)
            dy = abs(touch.y - self._tap_oy)
            if dx > dp(8) or dy > dp(8) or _scroll_active(touch):
                self._is_tap = False
                self.state = 'normal'
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            # Double-gate: movement AND no scroll-mode activation at any point
            fire = (self._is_tap
                    and not _scroll_active(touch)
                    and self.collide_point(*touch.pos))
            self._is_tap = False
            self.state = 'normal'
            if fire:
                self._fire_release()
        return False

    def on_touch_cancel(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self._is_tap = False
            self.state = 'normal'
        return False

    def _fire_release(self):
        app = App.get_running_app()
        if app and self.expense_id:
            app.open_expense(self.expense_id, return_to='history')
