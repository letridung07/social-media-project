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

*   **`binomial_pmf(k: int, n: int, p: float) -> float`**:
    Calculates the Probability Mass Function (PMF) for the Binomial distribution. This gives the probability of observing exactly `k` successes in `n` independent Bernoulli trials, where `p` is the probability of success on a single trial.
    *   **Parameters:**
        *   `k (int)`: The number of successes (non-negative, `k <= n`).
        *   `n (int)`: The number of trials (non-negative).
        *   `p (float)`: The probability of success on a single trial (`0 <= p <= 1`).
    *   **Returns:**
        *   `float`: The probability P(X=k).
    *   **Raises:**
        *   `TypeError`: If `k` or `n` are not integers, or `p` is not a float.
        *   `ValueError`: If `p` is outside [0, 1], `n` is negative, or `k` is negative or `k > n`.

*   **`poisson_pmf(k: int, lambda_val: float) -> float`**:
    Calculates the Probability Mass Function (PMF) for the Poisson distribution. This gives the probability of observing exactly `k` events in a fixed interval, given `lambda_val` (λ) as the average number of events in that interval.
    *   **Parameters:**
        *   `k (int)`: The number of occurrences of the event (non-negative).
        *   `lambda_val (float)`: The average rate of occurrences (λ, must be >= 0). Accepts int, casts to float.
    *   **Returns:**
        *   `float`: The probability P(X=k).
    *   **Raises:**
        *   `TypeError`: If `k` is not an integer or `lambda_val` is not a number.
        *   `ValueError`: If `k` is negative or `lambda_val` is negative.

*   **`normal_pdf(x: float, mu: float, sigma: float) -> float`**:
    Calculates the Probability Density Function (PDF) for the Normal (Gaussian) distribution at a given value `x`.
    *   **Parameters:**
        *   `x (float)`: The value at which to evaluate the PDF. Accepts int, casts to float.
        *   `mu (float)`: The mean (μ) of the distribution. Accepts int, casts to float.
        *   `sigma (float)`: The standard deviation (σ) of the distribution (must be > 0). Accepts int, casts to float.
    *   **Returns:**
        *   `float`: The value of the PDF at `x`.
    *   **Raises:**
        *   `TypeError`: If `x`, `mu`, or `sigma` are not numbers.
        *   `ValueError`: If `sigma` is not positive (`sigma <= 0`).

*   **`two_sample_ttest_statistic(sample1: List[Union[int, float]], sample2: List[Union[int, float]], equal_variances: bool = True) -> Tuple[float, float]`**:
    Calculates the t-statistic and degrees of freedom for a two-sample independent t-test. This test is used to determine if there is a significant difference between the means of two independent groups.
    *   **Parameters:**
        *   `sample1 (List[Union[int, float]])`: A list of numbers representing the first sample. Must contain at least 2 elements.
        *   `sample2 (List[Union[int, float]])`: A list of numbers representing the second sample. Must contain at least 2 elements.
        *   `equal_variances (bool, optional)`: If `True` (default), assumes equal population variances and calculates Student's t-statistic and corresponding degrees of freedom (`n1 + n2 - 2`). If `False`, performs Welch's t-test which does not assume equal population variances, and calculates the t-statistic and degrees of freedom using the Welch-Satterthwaite equation.
    *   **Returns:**
        *   `Tuple[float, float]`: A tuple `(t_statistic, degrees_of_freedom)`.
        *   Note: This function returns the t-statistic and degrees of freedom only. Calculation of the p-value is not included and would typically require a CDF of the t-distribution.
        *   Returns `(float('nan'), float('nan'))` or `(float('inf'), ...)` for t-statistic or df if calculations involve division by zero or undefined conditions.
    *   **Raises:**
        *   `TypeError`: If `sample1` or `sample2` are not lists, if samples contain non-numeric data, or if `equal_variances` is not a boolean.
        *   `ValueError`: If `sample1` or `sample2` contain fewer than 2 elements.

**How to Import and Examples:**

Functions from the statistics module can be imported as follows:

```python
from app.libs.pymath.statistics import (
    mean, median, mode, std_dev,
    pearson_correlation, simple_linear_regression,
    multiple_linear_regression, polynomial_regression,
    binomial_pmf, poisson_pmf, normal_pdf,
    two_sample_ttest_statistic
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

    # Example for Binomial PMF
    try:
        prob_binom = binomial_pmf(k=2, n=5, p=0.5)
        print(f"\nBinomial P(X=2; n=5, p=0.5): {prob_binom:.5f}") # Expected: 0.31250
    except (ValueError, TypeError) as e_binom:
        print(f"Binomial PMF Error: {e_binom}")

    # Example for Poisson PMF
    try:
        prob_poisson = poisson_pmf(k=2, lambda_val=1.0)
        print(f"Poisson P(X=2; lambda=1.0): {prob_poisson:.5f}") # Expected: 0.18394
    except (ValueError, TypeError) as e_poisson:
        print(f"Poisson PMF Error: {e_poisson}")

    # Example for Normal PDF
    try:
        density_normal = normal_pdf(x=0.0, mu=0.0, sigma=1.0)
        print(f"Normal PDF N(0,1) at x=0: {density_normal:.5f}") # Expected: 0.39894
    except (ValueError, TypeError) as e_normal:
        print(f"Normal PDF Error: {e_normal}")

    # Example for Two-Sample T-Test Statistic
    s1_ttest = [17, 20, 22, 18, 19]
    s2_ttest = [10, 12, 15, 11, 13, 14, 12]
    print(f"\nTwo-Sample T-Test Data:")
    print(f"Sample 1: {s1_ttest}")
    print(f"Sample 2: {s2_ttest}")
    try:
        # Student's t-test (assuming equal variances)
        t_stat_students, df_students = two_sample_ttest_statistic(s1_ttest, s2_ttest, equal_variances=True)
        print(f"Student's t-test: t-statistic = {t_stat_students:.3f}, df = {df_students:.0f}")

        # Welch's t-test (not assuming equal variances)
        t_stat_welch, df_welch = two_sample_ttest_statistic(s1_ttest, s2_ttest, equal_variances=False)
        print(f"Welch's t-test: t-statistic = {t_stat_welch:.3f}, df = {df_welch:.3f}")
    except (ValueError, TypeError) as e_ttest:
        print(f"T-test Error: {e_ttest}")

except ValueError as e:
    print(f"Calculation Error: {e}")
except TypeError as e:
    print(f"Data Type Error: {e}")
```
