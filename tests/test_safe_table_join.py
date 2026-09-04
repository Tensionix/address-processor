from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from system_core.safe_table_join import detect_address_columns, normalized_building_key, parse_column_spec


class SafeTableJoinTests(unittest.TestCase):
    def test_parse_multiple_column_slots(self) -> None:
        self.assertEqual(parse_column_spec("B, C, AA"), (2, 3, 27))

    def test_detect_split_address_columns_in_multiline_header(self) -> None:
        matrix = (
            ("№ п/п", "Адрес многоквартирного дома", None, None, "Дата"),
            (None, None, "№ дома", "Корпус, литера", None),
            ("1", "2", "3", "4", "5"),
            (1, "60 лет Октября", 1, None, 1978),
        )
        self.assertEqual(detect_address_columns(matrix, 4), (2, 3, 4))

    def test_detect_street_and_house_columns(self) -> None:
        matrix = (
            ("№ п/п", "Название улицы (переулка)", "№ дома", "Решение"),
            (1, "Выучейского", 7, "снесен"),
        )
        self.assertEqual(detect_address_columns(matrix, 2), (2, 3))

    def test_building_key_ignores_room_but_keeps_house_letter(self) -> None:
        self.assertEqual(
            normalized_building_key(("Заводская", "5 А кв.3")),
            normalized_building_key(("Заводская", "5", "А")),
        )


if __name__ == "__main__":
    unittest.main()
