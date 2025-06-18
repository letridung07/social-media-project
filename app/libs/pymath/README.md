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

*   **`multiple_linear_regression(X_data: List[List[Union[int, float]]], y_data: List[Union[int, float]]) -> List[float]`**:
    Performs multiple linear regression to model the relationship between multiple independent variables (features) and a single dependent variable.
    *   **Parameters:**
        *   `X_data (List[List[Union[int, float]]])`: A list of lists, where each inner list represents an observation and contains the feature values for that observation.
        *   `y_data (List[Union[int, float]])`: A list of dependent variable values corresponding to each observation.
    *   **Returns:**
        *   `List[float]`: A list of coefficients `[β₀, β₁, β₂, ..., βₚ]`, where `β₀` is the intercept, and `β₁` through `βₚ` are the coefficients for each feature in the order they appeared in `X_data`'s inner lists.
    *   **Raises:**
        *   `ValueError`: If input data is empty, dimensions are mismatched, number of observations is insufficient for the number of features, or if the `(X^T X)` matrix is singular (e.g., due to perfect multicollinearity).
        *   `TypeError`: If input data contains non-numeric values.

*   **`polynomial_regression(x_values: List[Union[int, float]], y_values: List[Union[int, float]], degree: int) -> List[float]`**:
    Performs polynomial regression to fit a polynomial model of a specified `degree` to the given `x_values` and `y_values`.
    *   **Parameters:**
        *   `x_values (List[Union[int, float]])`: A list of independent variable values.
        *   `y_values (List[Union[int, float]])`: A list of dependent variable values.
        *   `degree (int)`: The degree of the polynomial to fit (must be >= 1).
    *   **Returns:**
        *   `List[float]`: A list of coefficients `[β₀, β₁, β₂, ..., β_degree]`, where `β₀` is the intercept, `β₁` is the coefficient for `x`, `β₂` for `x²`, and so on, up to the specified `degree`.
    *   **Raises:**
        *   `ValueError`: If input lists are empty or have mismatched lengths, `degree` is less than 1, there are insufficient data points for the given `degree`, or if multicollinearity arises in the transformed polynomial features.
        *   `TypeError`: If `x_values` or `y_values` contain non-numeric data, or if `degree` is not an integer.

**How to Import and Examples:**

Functions from the statistics module can be imported as follows:

```python
from app.libs.pymath.statistics import (
    mean, median, mode, std_dev,
    pearson_correlation, simple_linear_regression,
    multiple_linear_regression, polynomial_regression
)
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

    # Example for Multiple Linear Regression
    X_mlr = [[1, 2], [2, 3], [3, 5], [4, 4], [5, 7]] # Two features
    y_mlr = [3, 5, 7, 6, 9]
    print(f"\nMultiple Linear Regression Data:")
    print(f"X_mlr: {X_mlr}")
    print(f"y_mlr: {y_mlr}")
    try:
        mlr_coeffs = multiple_linear_regression(X_mlr, y_mlr)
        # Output format: [intercept, beta_feature1, beta_feature2, ...]
        print(f"Multiple Linear Regression Coefficients (intercept, b1, b2): {mlr_coeffs}")
    except (ValueError, TypeError) as e_mlr:
        print(f"MLR Error: {e_mlr}")

    # Example for Polynomial Regression
    x_poly = [0, 1, 2, 3]
    y_poly = [1, 3, 7, 13] # y = 1*x^2 + 1*x + 1
    poly_degree = 2
    print(f"\nPolynomial Regression Data (degree {poly_degree}):")
    print(f"x_poly: {x_poly}")
    print(f"y_poly: {y_poly}")
    try:
        poly_coeffs = polynomial_regression(x_poly, y_poly, poly_degree)
        # Output format: [intercept, beta_x, beta_x^2, ...]
        print(f"Polynomial Regression (deg {poly_degree}) Coefficients (intercept, b_x, b_x^2): {poly_coeffs}")
    except (ValueError, TypeError) as e_poly:
        print(f"Polynomial Regression Error: {e_poly}")

except ValueError as e:
    print(f"Calculation Error: {e}")
except TypeError as e:
    print(f"Data Type Error: {e}")
```
