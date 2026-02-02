from werkzeug.security import generate_password_hash

def generar_hash(password):
    return generate_password_hash(password)
