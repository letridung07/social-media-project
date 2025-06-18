import math
from typing import List, Union

def mean(data: List[Union[int, float]]):
  """
  Calculates the arithmetic mean of a list of numbers.

  Args:
    data (list[Union[int, float]]): A list of numbers (integers or floats).

  Returns:
    float: The arithmetic mean of the numbers.

  Raises:
    ValueError: If the input list is empty.
    TypeError: If the list contains non-numeric data.
  """
  if not data:
    raise ValueError("Input list cannot be empty. Cannot calculate mean of an empty list.")
  if not all(isinstance(x, (int, float)) for x in data):
    raise TypeError("All elements in the list must be numeric (int or float).")
  return sum(data) / len(data)

def median(data: List[Union[int, float]]):
  """
  Calculates the median of a list of numbers.
  The median is the middle value of a dataset that has been sorted.
  If the dataset has an even number of values, the median is the average of the two middle values.

  Args:
    data (list[Union[int, float]]): A list of numbers (integers or floats).

  Returns:
    Union[int, float]: The median value. This can be an integer or a float
                       depending on the input data and whether the list length is even or odd.

  Raises:
    ValueError: If the input list is empty.
    TypeError: If the list contains non-numeric data.
  """
  if not data:
    raise ValueError("Input list cannot be empty. Cannot calculate median of an empty list.")
  if not all(isinstance(x, (int, float)) for x in data):
    raise TypeError("All elements in the list must be numeric (int or float).")

  sorted_data = sorted(data)
  n = len(sorted_data)
  mid = n // 2

  if n % 2 == 0:
    # Even number of elements
    return (sorted_data[mid - 1] + sorted_data[mid]) / 2
  else:
    # Odd number of elements
    return sorted_data[mid]

def mode(data):
  """
  Calculates the mode(s) of a list of numbers.
  The mode is the value that appears most frequently in a data set.
  A list of modes is returned because a dataset can have more than one mode (multimodal).

  Args:
    data (list[Union[int, float]]): A list of numbers (integers or floats).

  Returns:
    list[Union[int, float]]: A list containing the mode(s).
                             Returns an empty list if all elements are unique (no mode),
                             or if the input list is empty (after validation).
                             The modes will be of the same type as found in the input data.

  Raises:
    ValueError: If the input list is empty.
    TypeError: If the list contains non-numeric data.
  """
  if not data:
    raise ValueError("Input list cannot be empty. Cannot calculate mode of an empty list.")
  if not all(isinstance(x, (int, float)) for x in data):
    raise TypeError("All elements in the list must be numeric (int or float).")

  counts = {}
  for item in data:
    counts[item] = counts.get(item, 0) + 1

  max_count = 0
  for count in counts.values():
      if count > max_count:
          max_count = count

  # In case all elements are unique, there is no mode.
  if max_count == 1 and len(set(data)) == len(data):
      return []

  modes = [key for key, value in counts.items() if value == max_count]
  return modes

def std_dev(data):
  """
  Calculates the population standard deviation of a list of numbers.
  Standard deviation is a measure of the amount of variation or dispersion of a set of values.
  A low standard deviation indicates that the values tend to be close to the mean (also called the expected value) of the set,
  while a high standard deviation indicates that the values are spread out over a wider range.
  This function calculates the *population* standard deviation, not the sample standard deviation.

  Args:
    data (list[Union[int, float]]): A list of numbers (integers or floats).

  Returns:
    float: The population standard deviation.

  Raises:
    ValueError: If the list has fewer than two elements, as standard deviation requires at least two data points.
    TypeError: If the list contains non-numeric data (elements are not int or float).
  """
  if not all(isinstance(x, (int, float)) for x in data):
    raise TypeError("All elements in the list must be numeric (int or float).")
  if len(data) < 2: # Changed from 1 to 2 as per docstring and common practice for population std dev
    raise ValueError("List must contain at least two data points to calculate standard deviation.")

  mean_val = mean(data)
  variance = sum([(x - mean_val) ** 2 for x in data]) / len(data)
  return math.sqrt(variance)
