import unittest
from app.libs.pymath.statistics import mean, median, mode, std_dev

class TestMean(unittest.TestCase):
    def test_positive_integers(self):
        self.assertEqual(mean([1, 2, 3, 4, 5]), 3.0)

    def test_mixed_numbers(self):
        self.assertEqual(mean([-1, 0, 1, 2, 3]), 1.0)

    def test_floating_point_numbers(self):
        self.assertAlmostEqual(mean([1.0, 1.5, 2.0, 2.5, 3.0]), 2.0)

    def test_empty_list_raises_value_error(self):
        with self.assertRaises(ValueError):
            mean([])

    def test_non_numeric_data_raises_type_error(self):
        with self.assertRaises(TypeError):
            mean([1, 2, 'a', 4])
        with self.assertRaises(TypeError):
            mean([1, 2, [3], 4])

class TestMedian(unittest.TestCase):
    def test_odd_length_integers(self):
        self.assertEqual(median([1, 2, 3, 4, 5]), 3)

    def test_even_length_integers(self):
        self.assertEqual(median([1, 2, 3, 4, 5, 6]), 3.5)

    def test_odd_length_floats(self):
        self.assertAlmostEqual(median([1.0, 1.5, 2.0, 2.5, 3.0]), 2.0)

    def test_even_length_floats(self):
        self.assertAlmostEqual(median([1.0, 1.5, 2.0, 2.5, 3.0, 3.5]), 2.25)

    def test_negative_numbers(self):
        self.assertEqual(median([-5, -2, -1, 0, 3]), -1)
        self.assertEqual(median([-5, -2, -1, 0, 3, 7]), -0.5)

    def test_unsorted_list(self):
        self.assertEqual(median([5, 1, 3, 2, 4]), 3)
        self.assertEqual(median([6, 1, 3, 2, 5, 4]), 3.5)

    def test_empty_list_raises_value_error(self):
        with self.assertRaises(ValueError):
            median([])

    def test_non_numeric_data_raises_type_error(self):
        with self.assertRaises(TypeError):
            median([1, 2, 'a', 4])
        with self.assertRaises(TypeError):
            median([1, 2, [3], 4])

class TestMode(unittest.TestCase):
    def test_single_mode(self):
        self.assertEqual(sorted(mode([1, 2, 2, 3, 4, 4, 4, 5])), [4])

    def test_multiple_modes(self):
        self.assertEqual(sorted(mode([1, 2, 2, 3, 3, 3, 4, 4, 4, 5])), [3, 4])
        self.assertEqual(sorted(mode([1, 1, 2, 3, 3])), [1, 3])

    def test_all_elements_unique(self):
        # Depending on strict definition of mode, this could be an empty list
        # or all elements. The current implementation returns an empty list.
        self.assertEqual(mode([1, 2, 3, 4, 5]), [])

    def test_negative_numbers_mode(self):
        self.assertEqual(sorted(mode([-1, -2, -2, -3, -3, -3])), [-3])

    def test_empty_list_raises_value_error(self):
        # The mode function currently returns [] for an empty list,
        # it should raise ValueError based on the docstring.
        # I will adjust this test after running and seeing the failure.
        with self.assertRaises(ValueError):
            mode([])

    def test_non_numeric_data_raises_type_error(self):
        with self.assertRaises(TypeError):
            mode([1, 2, 'a', 4])
        with self.assertRaises(TypeError):
            mode([1, 2, [3], 4])

class TestStdDev(unittest.TestCase):
    def test_integers_std_dev(self):
        self.assertAlmostEqual(std_dev([1, 2, 3, 4, 5]), 1.4142135623730951)

    def test_floats_std_dev(self):
        self.assertAlmostEqual(std_dev([1.0, 1.5, 2.0, 2.5, 3.0]), 0.7071067811865476)

    def test_insufficient_data_raises_value_error(self):
        with self.assertRaises(ValueError):
            std_dev([])
        with self.assertRaises(ValueError):
            std_dev([1])

    def test_non_numeric_data_raises_type_error(self):
        with self.assertRaises(TypeError):
            std_dev([1, 2, 'a', 4])
        with self.assertRaises(TypeError):
            std_dev([1, 2, [3], 4])

if __name__ == '__main__':
    unittest.main()
