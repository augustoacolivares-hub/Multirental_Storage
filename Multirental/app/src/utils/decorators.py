from functools import wraps
from flask import redirect, url_for, session, flash

# Decorador para verificar si el usuario está logueado
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:  # Verifica si el usuario ha iniciado sesión
            flash("Por favor, inicia sesión para acceder a esta página.")
            return redirect(url_for("main_bp.login"))  # Redirige al login si no está autenticado
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Verificar si el usuario está autenticado y si es administrador
        if "rol" not in session or session["rol"] != "Administrador":
            flash("Acceso denegado. Esta acción solo es permitida para administradores.")
            return redirect(url_for("main_bp.home"))
        return f(*args, **kwargs)
    return decorated_function