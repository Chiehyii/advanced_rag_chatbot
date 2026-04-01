import getpass
import bcrypt

def generate_hash():
    
    print("This script will generate a bcrypt hash of your admin password.")
    print("You can then put this hash in your .env file as ADMIN_PASSWORD_HASH")
    print("and safely delete the plaintext ADMIN_PASSWORD.")
    print("-" * 50)
    
    password = getpass.getpass("Enter your desired admin password: ")
    confirm_password = getpass.getpass("Confirm password: ")
    
    if password != confirm_password:
        print("Error: Passwords do not match!")
        return
        
    if not password:
        print("Error: Password cannot be empty!")
        return
        
    # Bcrypt limitation: password cannot exceed 72 bytes. We safely truncate it.
    password_to_hash = password[:72]
    if len(password) > 72:
        print("\n[Warning] Your password exceeds 72 characters. It has been securely truncated to 72 characters to be compatible with bcrypt.")
        
    hash_value = bcrypt.hashpw(password_to_hash.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    print("\nSuccess! Here is your password hash:")
    print("=" * 50)
    print(f"ADMIN_PASSWORD_HASH={hash_value}")
    print("=" * 50)
    print("\nInstructions:")
    print("1. Copy the value above.")
    print("2. Paste it into your .env file.")
    print("3. Comment out or delete ADMIN_PASSWORD from your .env file.")
    print("4. Restart your application.")

if __name__ == "__main__":
    generate_hash()
