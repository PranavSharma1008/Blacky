def reverse_string(s: str) -> str:
    """Reverses the given string."""
    return s[::-1]

def is_palindrome(s: str) -> bool:
    """Checks if a string is a palindrome (ignores case and non-alphanumeric)."""
    clean_s = "".join(char.lower() for char in s if char.isalnum())
    return clean_s == clean_s[::-1]

def to_camel_case(s: str) -> str:
    """Converts snake_case or space-separated string to camelCase."""
    words = s.replace("_", " ").split()
    if not words:
        return ""
    return words[0].lower() + "".join(word.capitalize() for word in words[1:])

def to_snake_case(s: str) -> str:
    """Converts camelCase or space-separated string to snake_case."""
    import re
    s = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', s)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s).lower().replace(" ", "_")

def truncate(s: str, length: int, suffix: str = "...") -> str:
    """Truncates a string to a specific length and adds a suffix."""
    if len(s) <= length:
        return s
    return s[:length].rsplit(' ', 1)[0] + suffix

if __name__ == "__main__":
    # Test cases
    test_str = "Hello World"
    print(f"Original: {test_str}")
    print(f"Reversed: {reverse_string(test_str)}")
    print(f"Is Palindrome ('Racecar'): {is_palindrome('Racecar')}")
    print(f"Camel Case: {to_camel_case('hello_world_test')}")
    print(f"Snake Case: {to_snake_case('helloWorldTest')}")
    print(f"Truncated: {truncate('The quick brown fox jumps over the lazy dog', 20)}")
