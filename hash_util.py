import hashlib

def hash_string(input_str: str) -> str:
    """
    SHA1 hash using UTF-16 LE encoding to match the original C# implementation.
    C# UnicodeEncoding = UTF-16 LE (no BOM), which is what encode('utf-16-le') gives us.
    Output is uppercase hex, matching the X2 format from the original Hash.cs.
    """
    encoded = input_str.encode('utf-16-le')
    sha1 = hashlib.sha1(encoded)
    return sha1.hexdigest().upper()
