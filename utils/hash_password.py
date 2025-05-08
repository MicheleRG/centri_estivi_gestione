import streamlit_authenticator as stauth
import sys

def generate_hashed_password(password):
    """Genera la password hashata per la password fornita."""
    hashed_passwords = stauth.Hasher([password]).generate()
    return hashed_passwords[0]

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python hash_password.py <password>")
        sys.exit(1)

    password = sys.argv[1]
    hashed_password = generate_hashed_password(password)
    print("Password hashata:", hashed_password)