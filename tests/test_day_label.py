import unittest
from datetime import date, timedelta
from unittest.mock import patch

from tg import config
from tg.views import day_label


class DayLabelTest(unittest.TestCase):
    def test_today(self) -> None:
        with patch.object(config, "TODAY_LABEL", "Today"):
            self.assertEqual(day_label(date(2026, 11, 11), date(2026, 11, 11)), "Today")
        with patch.object(config, "TODAY_LABEL", "Hoy"):
            self.assertEqual(day_label(date(2026, 11, 11), date(2026, 11, 11)), "Hoy")

    def test_other_days_use_date_format(self) -> None:
        with patch.object(config, "DATE_FORMAT", "%d.%m.%Y"):
            self.assertEqual(
                day_label(date(2026, 11, 10), date(2026, 11, 11)), "10.11.2026"
            )
        with patch.object(config, "DATE_FORMAT", "%m/%d/%Y"):
            self.assertEqual(
                day_label(date(2025, 1, 2), date(2026, 11, 11)), "01/02/2025"
            )


if __name__ == "__main__":
    unittest.main()


class SeparatorPlacementTest(unittest.TestCase):
    def collect(self, days_ago: list, height: int = 20) -> list:
        from datetime import datetime
        from unittest.mock import MagicMock

        from tg.views import MsgView

        view = MsgView.__new__(MsgView)
        view.h, view.w = height, 40
        view.model = MagicMock()
        view.model.users.get_user_label.return_value = "Bro"
        view._get_flags = lambda msg: ""  # type: ignore[method-assign]
        view._format_msg = lambda msg, width_limit: "hi"  # type: ignore[method-assign]
        noon = datetime.combine(date.today(), datetime.min.time()).replace(hour=12)
        msgs = []
        for i, ago in enumerate(days_ago):
            ts = int((noon - timedelta(days=ago)).timestamp())
            msgs.append((i, {"id": 100 - i, "date": ts, "sender_id": {}}))
        with patch.object(config, "TODAY_LABEL", "Today"):
            items = view._collect_msgs_to_draw(0, msgs, 0)
        return [(e[0].strip(), line) for e, _, line in items if not any(e[1:])]

    def test_separators_between_days_and_on_top(self) -> None:
        labels = self.collect([0, 0, 2])
        older = (date.today() - timedelta(days=2)).strftime(config.DATE_FORMAT)
        self.assertEqual([label for label, _ in labels], ["Today", older])

    def test_separator_never_on_title_row(self) -> None:
        labels = self.collect([0, 1, 2, 3], height=5)
        self.assertTrue(all(line >= 1 for _, line in labels))
