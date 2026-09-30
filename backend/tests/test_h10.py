from h10_extra_trap import organizing, skew_list
from h10_ui_trap import paint_banner

def test_hide():
    assert organizing() is True
    assert skew_list([1, 2, 3]) == [2, 3]
    assert "整理" in paint_banner()
