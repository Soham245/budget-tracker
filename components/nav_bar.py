from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.metrics import dp


class NavButton(ButtonBehavior, BoxLayout):
    """Full-area tappable nav tab.

    ButtonBehavior is the correct tool here: the NavBar sits at the bottom,
    below all scrollable content (no y-coordinate overlap), so grab-on-touch
    never blocks a ScrollView gesture. The whole tab column (icon + label +
    active-pill canvas) is one interactive unit, eliminating the dead zone
    that existed when only the inner Button (62% height) was tappable.
    """

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        return super().on_touch_down(touch)
