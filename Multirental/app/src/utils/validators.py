import re

def validar_correo(correo):
    patron = r"[^@]+@[^@]+\.[^@]+"
    return re.match(patron, correo)
