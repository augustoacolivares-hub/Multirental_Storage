from app.src.database.database import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import enum  # Cambia a usar enum de Python para definir los enumerados
from sqlalchemy import Enum, UniqueConstraint  # SQLAlchemy Enum para la base de datos


# Enumeración para los estados de la herramienta
class EstadoHerramientaEnum(enum.Enum):
    Disponible = "Disponible"
    Reservada = "Reservada"
    En_Mantenimiento = "En Mantenimiento"


# Enumeración para los roles de usuario
class RolEnum(enum.Enum):
    Usuario = "Usuario"
    Administrador = "Administrador"


# Enumeración para el estado del arriendo
class EstadoArriendoEnum(enum.Enum):
    EN_PROCESO = "En proceso"
    FINALIZADO = "Finalizado"


class Herramienta(db.Model):
    __tablename__ = "herramientas"

    id_herramienta = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    marca = db.Column(db.String(100), nullable=False)

    # Relaciones
    asociaciones_sucursal = db.relationship("HerramientaSucursal", back_populates="herramienta")




# Modelo Sucursal: representa las sucursales donde se almacenan herramientas
class Sucursal(db.Model):
    __tablename__ = "sucursales"

    id_sucursal = db.Column(db.Integer, primary_key=True)
    nombre_sucursal = db.Column(db.String(100), nullable=False)
    ubicacion = db.Column(db.String(200), nullable=False)

    herramientas = db.relationship("HerramientaSucursal", back_populates="sucursal")


# Modelo Usuario: representa los usuarios del sistema
class Usuario(db.Model):
    __tablename__ = "usuarios"
    id_usuario = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(120), unique=True, nullable=False)
    rol = db.Column(Enum(RolEnum), nullable=False, default=RolEnum.Usuario)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        """Genera un hash para la contraseña."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica si la contraseña coincide con el hash almacenado."""
        return check_password_hash(self.password_hash, password)


# Modelo Transaccion: representa las transacciones de herramientas
class Transaccion(db.Model):
    __tablename__ = "transacciones"
    id_transaccion = db.Column(db.Integer, primary_key=True)
    herramienta_sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("herramienta_sucursal.id", ondelete="CASCADE"),  # Configura borrado en cascada
        nullable=False
    )
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    estado_anterior = db.Column(db.String(50), nullable=False)
    estado_nuevo = db.Column(db.String(50), nullable=False)
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.id_sucursal", ondelete="CASCADE"),
        nullable=False
    )

    # Relaciones
    herramienta_sucursal = db.relationship(
        "HerramientaSucursal", backref=db.backref("transacciones", cascade="all, delete-orphan")
    )
    sucursal = db.relationship("Sucursal", backref="transacciones", passive_deletes=True)

    def __repr__(self):
        return f"<Transaccion {self.id_transaccion} - {self.estado_anterior} -> {self.estado_nuevo}, cantidad: {self.cantidad}>"


# Modelo HerramientaSucursal: modelo intermedio para manejar relación muchos a muchos
class HerramientaSucursal(db.Model):
    __tablename__ = "herramienta_sucursal"

    id = db.Column(db.Integer, primary_key=True)
    herramienta_id = db.Column(
        db.Integer, db.ForeignKey("herramientas.id_herramienta"), nullable=False
    )
    sucursal_id = db.Column(
        db.Integer, db.ForeignKey("sucursales.id_sucursal"), nullable=False
    )
    codigo = db.Column(db.String(50), nullable=False)
    cantidad_disponible = db.Column(db.Integer, default=1, nullable=False)
    estado = db.Column(
        db.Enum(
            "Disponible",
            "Reservada",
            "En Mantenimiento",
            name="estado_herramienta"
        ),
        default="Disponible",
        nullable=False,
    )

    # Relaciones
    herramienta = db.relationship("Herramienta", back_populates="asociaciones_sucursal")
    sucursal = db.relationship("Sucursal", back_populates="herramientas")

