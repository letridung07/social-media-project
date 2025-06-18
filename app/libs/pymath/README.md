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

**How to Import:**

Functions from the statistics module can be imported as follows:

```python
from app.libs.pymath.statistics import mean, median, mode, std_dev

# Example usage:
data = [1, 2, 3, 4, 5, 5, 6]
print(f"Mean: {mean(data)}")
print(f"Median: {median(data)}")
print(f"Mode: {mode(data)}")
print(f"Standard Deviation: {std_dev(data)}")
```
