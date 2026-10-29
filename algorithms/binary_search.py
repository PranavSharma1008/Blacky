"""
Binary Search Algorithm Implementation in Python.

This module provides both iterative and recursive implementations of the
Binary Search algorithm, designed to find the index of a target element in a
sorted list in O(log n) time.
"""

from typing import List, Optional


def binary_search(arr: List[int], target: int) -> Optional[int]:
    """
    Perform an iterative binary search on a sorted list.

    Args:
        arr (List[int]): A list of sorted elements.
        target (int): The element to search for.

    Returns:
        Optional[int]: The 0-based index of target if found, else None.

    Examples:
        >>> binary_search([1, 3, 5, 7, 9], 5)
        2
        >>> binary_search([1, 3, 5, 7, 9], 4)
        None
    """
    left, right = 0, len(arr) - 1

    while left <= right:
        mid = left + (right - left) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return None


def binary_search_recursive(
    arr: List[int], target: int, left: int = 0, right: Optional[int] = None
) -> Optional[int]:
    """
    Perform a recursive binary search on a sorted list.

    Args:
        arr (List[int]): A list of sorted elements.
        target (int): The element to search for.
        left (int): Lower bound index for sub-array (default 0).
        right (Optional[int]): Upper bound index for sub-array (default len(arr) - 1).

    Returns:
        Optional[int]: The 0-based index of target if found, else None.
    """
    if right is None:
        right = len(arr) - 1

    if left > right:
        return None

    mid = left + (right - left) // 2

    if arr[mid] == target:
        return mid
    elif arr[mid] < target:
        return binary_search_recursive(arr, target, mid + 1, right)
    else:
        return binary_search_recursive(arr, target, left, mid - 1)


def run_tests():
    """Run test cases to verify the binary search functions."""
    test_cases = [
        # (arr, target, expected)
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 7, 6),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 1, 0),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 10, 9),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 11, None),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], -5, None),
        ([42], 42, 0),
        ([42], 99, None),
        ([], 5, None),
        ([-10, -5, 0, 5, 10, 15], -5, 1),
    ]

    print("Running Binary Search Test Cases...\n" + "=" * 40)

    for i, (arr, target, expected) in enumerate(test_cases, start=1):
        result_iter = binary_search(arr, target)
        result_rec = binary_search_recursive(arr, target)

        assert result_iter == expected, (
            f"Test #{i} (Iterative) Failed: arr={arr}, target={target}, "
            f"expected={expected}, got={result_iter}"
        )
        assert result_rec == expected, (
            f"Test #{i} (Recursive) Failed: arr={arr}, target={target}, "
            f"expected={expected}, got={result_rec}"
        )

        print(
            f"Test #{i}: Searching target {target} in {arr} -> "
            f"Result: {result_iter} [PASSED]"
        )

    print("=" * 40 + "\nAll 9 test cases passed successfully!")


if __name__ == "__main__":
    run_tests()
