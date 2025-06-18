# PyMath Library

A collection of Python modules for mathematical operations.

## Modules

### Symbolic Mathematics (`symbolic`)

Contains tools for symbolic mathematics, allowing for manipulation of mathematical expressions.

*(Further details about the symbolic module can be added here.)*

### Statistics (`statistics`)

Provides a set of functions to perform common statistical calculations on numerical data.

**Available Functions:**

*   **`mean(data: list[Union[int, float]]) -> float`**:
    Calculates the arithmetic mean (average) of a list of numbers.
    *   `data`: A list of integers or floats.
    *   Returns the mean as a float.
    *   Raises `ValueError` if the input list is empty.
    *   Raises `TypeError` if the list contains non-numeric data.

*   **`median(data: list[Union[int, float]]) -> Union[int, float]`**:
    Calculates the median (middle value) of a list of numbers.
    *   `data`: A list of integers or floats.
    *   Returns the median. Can be an int or float.
    *   Raises `ValueError` if the input list is empty.
    *   Raises `TypeError` if the list contains non-numeric data.

*   **`mode(data: list[Union[int, float]]) -> list[Union[int, float]]`**:
    Calculates the mode(s) (most frequent value(s)) of a list of numbers.
    *   `data`: A list of integers or floats.
    *   Returns a list of mode(s). Returns an empty list if no mode is found (all values unique).
    *   Raises `ValueError` if the input list is empty.
    *   Raises `TypeError` if the list contains non-numeric data.

*   **`std_dev(data: list[Union[int, float]]) -> float`**:
    Calculates the population standard deviation of a list of numbers.
    *   `data`: A list of integers or floats.
    *   Returns the standard deviation as a float.
    *   Raises `ValueError` if the list has fewer than two elements.
    *   Raises `TypeError` if the list contains non-numeric data.

*   **`pearson_correlation(data_x: List[Union[int, float]], data_y: List[Union[int, float]]) -> float`**:
    Calculates the Pearson correlation coefficient between two lists of numbers (`data_x` and `data_y`). This coefficient measures the linear correlation between the two datasets.
    *   **Parameters:**
        *   `data_x (List[Union[int, float]])`: A list of numbers (independent variable).
        *   `data_y (List[Union[int, float]])`: A list of numbers (dependent variable), must be the same length as `data_x`.
    *   **Returns:**
        *   `float`: The Pearson correlation coefficient, a value between -1 (perfect negative correlation) and 1 (perfect positive correlation). Returns `0.0` if the standard deviation of either `data_x` or `data_y` is zero.
    *   **Raises:**
        *   `ValueError`: If input lists are empty, of different lengths, or contain fewer than two data points.
        *   `TypeError`: If input lists contain non-numeric data.

*   **`simple_linear_regression(data_x: List[Union[int, float]], data_y: List[Union[int, float]]) -> Tuple[float, float]`**:
    Calculates the slope (m) and y-intercept (b) of the simple linear regression line (y = mx + b) for two lists of numbers (`data_x` and `data_y`).
    *   **Parameters:**
        *   `data_x (List[Union[int, float]])`: A list of numbers (independent variable).
        *   `data_y (List[Union[int, float]])`: A list of numbers (dependent variable), must be the same length as `data_x`.
    *   **Returns:**
        *   `Tuple[float, float]`: A tuple containing two floats: `(slope, y_intercept)`.
    *   **Raises:**
        *   `ValueError`: If input lists are empty, of different lengths, contain fewer than two data points, or if all values in `data_x` are the same (leading to an undefined slope).
        *   `TypeError`: If input lists contain non-numeric data.

**How to Import and Examples:**

Functions from the statistics module can be imported as follows:

```python
from app.libs.pymath.statistics import mean, median, mode, std_dev, pearson_correlation, simple_linear_regression
from typing import List, Union, Tuple # For type hints if needed in calling code

# Example for basic stats:
data = [1, 2, 3, 4, 5, 5, 6]
print(f"Data: {data}")
print(f"Mean: {mean(data)}")
print(f"Median: {median(data)}")
print(f"Mode: {mode(data)}")
print(f"Standard Deviation: {std_dev(data)}")

# Example for advanced stats:
x_data = [1, 2, 3, 4, 5]
y_data = [2, 3, 4.5, 5, 6.2] # y approx 0.95x + 1.13
print(f"\nX Data: {x_data}")
print(f"Y Data: {y_data}")

try:
    correlation = pearson_correlation(x_data, y_data)
    print(f"Pearson Correlation: {correlation:.4f}")

    slope, intercept = simple_linear_regression(x_data, y_data)
    print(f"Linear Regression: y = {slope:.2f}x + {intercept:.2f}")

    # Example with constant X values for regression (will raise ValueError)
    # x_const = [2, 2, 2, 2, 2]
    # y_vals = [1, 2, 3, 4, 5]
    # slope_const, intercept_const = simple_linear_regression(x_const, y_vals)
    # print(f"Regression with constant X: y = {slope_const:.2f}x + {intercept_const:.2f}")

except ValueError as e:
    print(f"Calculation Error: {e}")
except TypeError as e:
    print(f"Data Type Error: {e}")
```
