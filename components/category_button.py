from kivy.uix.togglebutton import ToggleButton
from kivy.properties import ListProperty, NumericProperty, StringProperty


class CategoryButton(ToggleButton):
    cat_color = ListProperty([0.92, 0.92, 0.92, 1])
    category_id = NumericProperty(-1)
    # Canonical category name; KV builds the markup-with-icon `text` from this
    # so call sites stay clean and the icon mapping lives in one place.
    category_name = StringProperty('')
