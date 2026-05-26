import hashlib
import bcrypt

def hash_string(input_str: str) -> str:
    """
    Legacy SHA1 hash — kept for backward compatibility with existing
    stored passwords (Staff.xml seeded entries, original demo data).
    UTF-16 LE encoding matches the original C# UnicodeEncoding behavior.
    """
    encoded = input_str.encode('utf-16-le')
    sha1 = hashlib.sha1(encoded)
    return sha1.hexdigest().upper()

def hash_password(password: str) -> str:
    """
    Bcrypt hash for new user registrations.
    Automatically salted, work factor 12.
    Returns a string for easy XML storage.
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    """
    Verify a password against a bcrypt hash.
    Also handles legacy SHA1 hashes for backward compatibility.
    """
    # Detect legacy SHA1 hash (40 char uppercase hex)
    if len(hashed) == 40 and hashed.isupper():
        return hash_string(password) == hashed
    # Bcrypt hash
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False
