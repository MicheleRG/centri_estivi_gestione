#./hash_password.py
import streamlit_authenticator as stauth
import sys
import getpass # Per nascondere l'input della password

def generate_hashed_password(password: str) -> str:
    """Genera la password hashata per la password fornita."""
    hashed_passwords = stauth.Hasher([password]).generate()
    return hashed_passwords[0]

if __name__ == "__main__":
    if len(sys.argv) == 2:
        password_to_hash = sys.argv[1]
    elif len(sys.argv) == 1:
        print("Inserisci la password da hashare:")
        password_to_hash = getpass.getpass() # Input nascosto
    else:
        print("Usage: python hash_password.py [password]")
        print("Se la password non è fornita come argomento, ti verrà chiesta in modo sicuro.")
        sys.exit(1)

    if not password_to_hash:
        print("Password non fornita. Uscita.")
        sys.exit(1)
        
    hashed_password_output = generate_hashed_password(password_to_hash)
    print("\nPassword hashata (copia questa nel tuo config.yaml):")
    print(hashed_password_output)
#./hash_password.py