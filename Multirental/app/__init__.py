import os
from flask import Flask
from app.src.database.database import db, migrate
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from app.config import Config
import pymysql
pymysql.install_as_MySQLdb()

  # Importar las extensiones

mail = Mail()
serializer = None

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    

    # Establecer la clave secreta para proteger las sesiones
    app.config["SECRET_KEY"] = os.getenv(
        "SECRET_KEY", "8b1ac95e69492bdb3ad740420f3a1498"
    )

    # Configuración de la base de datos MariaDB
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "mysql://root:Proyectorental@localhost:3307/multirental?charset=utf8mb4"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Desactiva las advertencias
    
    __all__ = ["app", "serializer", "mail", "db"]

    app.config["SECRET_KEY"] = "d54db7a949887df6d0a2a281536fd99283b5330f13d64631444679c5ad247803"  # Asegúrate de tener una clave secreta configurada
    global serializer
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    
        # Configuración de Flask
    app.config["MAIL_SERVER"] = "smtp.gmail.com"
    app.config["MAIL_PORT"] = 587
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USE_SSL"] = False
    app.config["MAIL_USERNAME"] = "multirentalstorage@gmail.com"
    app.config["MAIL_PASSWORD"] = "creb njtg kdsr nbuz"
    app.config["MAIL_DEFAULT_SENDER"] = "multirentalstorage@gmail.com"



    MAIL_SERVER = 'smtp.gmail.com'  # Cambiar según tu proveedor
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = 'tu_correo@gmail.com'
    MAIL_PASSWORD = 'tu_contraseña_de_aplicación'  # Usa contraseñas de aplicación para mayor seguridad
    MAIL_DEFAULT_SENDER = 'tu_correo@gmail.com'

    # Inicializar las extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # Importar modelos
    # Importamos aquí para evitar importaciones circulares
    with app.app_context():
        from app.src.models.models import (
            Herramienta,
            Sucursal,
            Usuario,
            Transaccion,
            HerramientaSucursal,
        )

    # Registrar los Blueprints
    from app.src.routes.main_routes import main_bp

    app.register_blueprint(main_bp)

    return app
