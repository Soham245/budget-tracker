from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, ListProperty


class CategoryBar(BoxLayout):
    """Compact single-row category bar: name | proportional bar | amount."""
    cat_name = StringProperty('')
    cat_amount = StringProperty('')
    cat_color = ListProperty([0.5, 0.5, 0.5, 1])
    bar_ratio = NumericProperty(0.0)          # 0–1, relative to biggest category
    over_budget = BooleanProperty(False)
