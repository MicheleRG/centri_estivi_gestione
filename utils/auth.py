import streamlit_authenticator as stauth
import bcrypt # Assicurati di averlo installato: pip install bcrypt

def generate_hashed_passwords():
    """Utility per generare password hashate."""
    # Esempio: inserisci qui le password che vuoi hashare
    passwords_to_hash = ['CambiaQuestaPasswordAdmin', 'CambiaQuestaPasswordUser'] 
    hashed_passwords = stauth.Hasher(passwords_to_hash[0]).generate()
    
    print("--- Password Hashate ---")
    print("Copia queste password nel tuo file config.yaml sotto la sezione 'password' per ogni utente.")
    for i, hashed_pw in enumerate(hashed_passwords):
        print(f"Password per utente (esempio {i+1}): {hashed_pw}")
    print("------------------------")
    print("Ricorda di aggiornare il file config.yaml con le password hashate generate e di impostare i ruoli (admin/user).")


if __name__ == '__main__':
    generate_hashed_passwords()
    print("\nRicorda di aggiornare il file config.yaml con le password hashate generate e di impostare i ruoli (admin/user).")