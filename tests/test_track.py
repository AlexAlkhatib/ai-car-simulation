"""Tests de la carte : chargement, bordures et requêtes hors limites."""

from __future__ import annotations

import unittest

from simulation import settings
from simulation.car import Car
from simulation.pygame_support import load_sprite
from simulation.track import Track


class TrackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.track = Track(settings.MAPS_DIR / settings.DEFAULT_MAP)

    def test_dimensions_match_scene(self) -> None:
        self.assertEqual((self.track.width, self.track.height), (settings.WIDTH, settings.HEIGHT))

    def test_border_is_white(self) -> None:
        self.assertEqual(self.track.rgb_at(0, 0), settings.BORDER_RGB)
        self.assertTrue(self.track.is_border_at(0, 0))

    def test_start_position_is_on_the_track(self) -> None:
        center = (
            settings.START_POSITION[0] + settings.CAR_SIZE_X / 2,
            settings.START_POSITION[1] + settings.CAR_SIZE_Y / 2,
        )
        self.assertFalse(self.track.is_border(center))

    def test_out_of_bounds_is_treated_as_border(self) -> None:
        for point in ((-1, 10), (10, -1), (self.track.width, 10), (10, self.track.height)):
            with self.subTest(point=point):
                self.assertIsNone(self.track.rgb_at(*point))
                self.assertTrue(self.track.is_border_at(*point))

    def test_as_dict_exposes_media_url(self) -> None:
        info = self.track.as_dict()
        self.assertEqual(info["name"], settings.DEFAULT_MAP)
        self.assertEqual(info["url"], f"/media/maps/{settings.DEFAULT_MAP}")

    def test_map_path_rejects_unsafe_names(self) -> None:
        for name in ("../config.txt", "map.gif", "unknown.png", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                settings.map_path(name)

    def test_available_maps(self) -> None:
        maps = settings.available_maps()
        self.assertIn(settings.DEFAULT_MAP, maps)
        self.assertGreaterEqual(len(maps), 5)

    def test_car_starts_inside_track_with_five_radars(self) -> None:
        car = Car(load_sprite(), self.track)
        car.update(self.track)
        self.assertTrue(car.is_alive())
        self.assertEqual(len(car.radars), settings.SENSOR_COUNT)
        self.assertEqual(len(car.get_data()), settings.SENSOR_COUNT)


if __name__ == "__main__":
    unittest.main()
