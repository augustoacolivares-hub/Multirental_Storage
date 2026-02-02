from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.src.models.models import (
    Herramienta,
    Sucursal,
    Usuario,
    Transaccion,
    HerramientaSucursal,
    db,
    EstadoHerramientaEnum,
)
from werkzeug.security import check_password_hash, generate_password_hash
from app.src.utils.decorators import login_required, admin_required
import csv
import io
from flask import send_file, Response
import pandas as pd
import pytz
from datetime import datetime
from sqlalchemy.orm import joinedload
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from app import serializer, mail
from app.src.utils.password_hashed import generar_hash
from app.src.utils.validators import validar_correo
  # Ajusta la ruta según tu estructura



main_bp = Blueprint("main_bp", __name__)


# Ruta de login aceptando tanto GET como POST
@main_bp.route("/", methods=["GET", "POST"])
def login():
    """Maneja la autenticación de usuarios."""
    if request.method == "POST":
        # Obtener los datos del formulario
        correo = request.form.get("correo")
        password = request.form.get("password")
        sucursal_id = request.form.get("sucursal")

        # Validar que todos los campos estén completos
        if not correo or not password or not sucursal_id:
            flash("Todos los campos son obligatorios.", "warning")
            return render_template("login.html", sucursales=Sucursal.query.all())

        # Validar si la sucursal fue seleccionada
        if not sucursal_id:
            flash("Por favor, selecciona una sucursal.", "warning")
            return render_template("login.html", sucursales=Sucursal.query.all())

        # Buscar al usuario por correo
        usuario = Usuario.query.filter_by(correo=correo).first()

        # Validar si el correo existe
        if not usuario:
            flash("Correo no encontrado. Verifica e inténtalo nuevamente.", "danger")
            return render_template("login.html", sucursales=Sucursal.query.all())

        # Validar si la contraseña es correcta
        if not check_password_hash(usuario.password_hash, password):
            flash("Contraseña incorrecta. Verifica e inténtalo nuevamente.", "danger")
            return render_template("login.html", sucursales=Sucursal.query.all())

        # Si las credenciales son válidas, guardar datos en la sesión
        session["usuario_id"] = usuario.id_usuario
        session["rol"] = usuario.rol.value
        session["nombre_usuario"] = usuario.nombre
        session["sucursal_id"] = sucursal_id
        session["nombre_sucursal"] = Sucursal.query.get(sucursal_id).nombre_sucursal

        flash(f"Bienvenido: {usuario.nombre}. Sucursal: {session['nombre_sucursal']}", "success")
        return redirect(url_for("main_bp.home"))

    # Si es un GET, cargar las sucursales para el formulario
    sucursales = Sucursal.query.all()
    return render_template("login.html", sucursales=sucursales)

#Home
@main_bp.route("/home")
@login_required
def home():
    sucursal_id = session.get("sucursal_id")
    search_query = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)

    search_query = request.args.get("search", "")
    if search_query and len(search_query) > 100:  # Validar tamaño de búsqueda
        flash("La búsqueda es demasiado larga.", "warning")
        return redirect(url_for("main_bp.home"))

    page = request.args.get("page", 1, type=int)
    if page < 1:  # Validar rango de página
        flash("Página no válida.", "warning")
        return redirect(url_for("main_bp.home"))

    # Construir la consulta base para herramientas en la sucursal activa
    query = (
        db.session.query(HerramientaSucursal, Herramienta)
        .join(Herramienta, Herramienta.id_herramienta == HerramientaSucursal.herramienta_id)
        .filter(
            HerramientaSucursal.sucursal_id == sucursal_id,
            HerramientaSucursal.estado.in_(["Disponible", "Reservada", "En Mantenimiento"]),
        )
        .order_by(
            # Ordenar primero por disponibilidad
            db.case(
                (HerramientaSucursal.estado == "Disponible", 1),  # Prioridad 1
                else_=2  # Menor prioridad para otros estados
            ),
            # Luego ordenar alfabéticamente por nombre
            Herramienta.nombre.asc()
        )
    )

    # Agregar búsqueda por nombre o código si se proporciona un query
    if search_query:
        query = query.filter(
            db.or_(
                Herramienta.nombre.ilike(f"%{search_query}%"),
                HerramientaSucursal.codigo.ilike(f"%{search_query}%"),
            )
        )

    # Paginación
    herramientas = query.paginate(page=page, per_page=10)

    return render_template(
        "home.html",
        herramientas=herramientas,
        search_query=search_query,
        nombre_sucursal=session.get("nombre_sucursal"),
    )


# Ruta para registrar herramientas
@main_bp.route("/registroHerramientas", methods=["GET", "POST"])
@login_required
def registroHerramientas():
    if request.method == "POST":
        # Primera fase del formulario
        if "nombre" in request.form and "marca" in request.form and "cantidad" in request.form:
            nombre = request.form.get("nombre").upper()
            marca = request.form.get("marca").upper()
            cantidad = request.form.get("cantidad")

            if not nombre or not marca or not cantidad or not cantidad.isdigit() or int(cantidad) <= 0:
                flash("El campo 'Cantidad a registrar' debe ser un número válido mayor a 0.", "danger")
                return render_template("registroHerramientas.html")

            return render_template(
                "registroHerramientasCodigos.html",
                nombre=nombre,
                marca=marca,
                cantidad=int(cantidad),
            )

        # Segunda fase del formulario
        elif "codigos" in request.form:
            nombre = request.form.get("nombre")
            marca = request.form.get("marca")
            codigos = request.form.getlist("codigos")
            sucursal_id = session.get("sucursal_id")

            if not sucursal_id:
                flash("Error: No se pudo identificar la sucursal activa.", "danger")
                return redirect(url_for("main_bp.home"))

            if not nombre or not marca or not codigos or any(not codigo.strip() for codigo in codigos):
                flash("Todos los campos son obligatorios y los códigos no deben estar vacíos.", "danger")
                return render_template(
                    "registroHerramientasCodigos.html",
                    nombre=nombre,
                    marca=marca,
                    cantidad=len(codigos),
                )

            # Validar unicidad de los códigos en los inputs
            codigos_limpios = [codigo.strip() for codigo in codigos]
            if len(codigos_limpios) != len(set(codigos_limpios)):
                flash("Los códigos deben ser únicos dentro del formulario.", "danger")
                return render_template(
                    "registroHerramientasCodigos.html",
                    nombre=nombre,
                    marca=marca,
                    cantidad=len(codigos),
                )

            # Validar contra la base de datos
            try:
                codigos_invalidos = []
                for codigo in codigos_limpios:
                    codigo_existente = (
                        db.session.query(HerramientaSucursal)
                        .filter_by(codigo=codigo, sucursal_id=sucursal_id)
                        .first()
                    )
                    if codigo_existente:
                        codigos_invalidos.append(codigo)

                # Si hay códigos duplicados en la base de datos, detener el proceso
                if codigos_invalidos:
                    flash(
                        f"Los siguientes códigos ya están registrados en esta sucursal: {', '.join(codigos_invalidos)}",
                        "danger",
                    )
                    return render_template(
                        "registroHerramientasCodigos.html",
                        nombre=nombre,
                        marca=marca,
                        cantidad=len(codigos),
                    )

                # Registrar herramienta y sus códigos si todo es válido
                herramienta = Herramienta(nombre=nombre, marca=marca)
                db.session.add(herramienta)
                db.session.flush()  # Obtener ID de la herramienta

                for codigo in codigos_limpios:
                    nueva_asociacion = HerramientaSucursal(
                        herramienta_id=herramienta.id_herramienta,
                        sucursal_id=sucursal_id,
                        codigo=codigo,
                        cantidad_disponible=1,
                        estado="Disponible",
                    )
                    db.session.add(nueva_asociacion)

                db.session.commit()  # Confirmar todo junto
                flash(f"{len(codigos_limpios)} herramientas registradas correctamente.", "success")
                return redirect(url_for("main_bp.home"))

            except Exception as e:
                db.session.rollback()  # Deshacer cualquier cambio en caso de error
                flash(f"Error al registrar herramientas: {str(e)}", "danger")
                return render_template(
                    "registroHerramientasCodigos.html",
                    nombre=nombre,
                    marca=marca,
                    cantidad=len(codigos),
                )

    return render_template("registroHerramientas.html")


# Transacciones
@main_bp.route("/transaccion/<string:herramienta_codigo>", methods=["GET", "POST"])
@login_required
def transaccion(herramienta_codigo):
    """Maneja las transacciones de una herramienta específica y las registra para reportes."""
    # Verificar si el código corresponde a una herramienta en la sucursal activa
    herramienta_sucursal = db.session.query(HerramientaSucursal).filter_by(
        codigo=herramienta_codigo,
        sucursal_id=session.get("sucursal_id")
    ).first()

    if not herramienta_sucursal:
        flash("La herramienta no existe o no pertenece a esta sucursal.", "danger")
        return redirect(url_for("main_bp.home"))

    if request.method == "POST":
        nuevo_estado = request.form.get("estado")
        try:
            # Validar que el nuevo estado sea diferente al actual
            estados_validos = ["Disponible", "Reservada", "En Mantenimiento"]
            if nuevo_estado not in estados_validos or nuevo_estado == herramienta_sucursal.estado:
                flash("Estado inválido o sin cambios.", "danger")
                return redirect(url_for("main_bp.transaccion", herramienta_codigo=herramienta_codigo))

            # Registrar la transacción en la tabla de Transacciones
            nueva_transaccion = Transaccion(
                herramienta_sucursal_id=herramienta_sucursal.id,
                estado_anterior=herramienta_sucursal.estado,
                estado_nuevo=nuevo_estado,
                fecha=datetime.utcnow(),
                sucursal_id=session.get("sucursal_id")
            )
            db.session.add(nueva_transaccion)

            # Actualizar el estado de la herramienta
            herramienta_sucursal.estado = nuevo_estado
            db.session.commit()

            # Calcular el stock total disponible para herramientas con el mismo nombre y marca
            stock_total = (
                db.session.query(db.func.sum(HerramientaSucursal.cantidad_disponible))
                .filter(
                    HerramientaSucursal.sucursal_id == session.get("sucursal_id"),
                    HerramientaSucursal.estado == "Disponible",
                    HerramientaSucursal.herramienta_id == herramienta_sucursal.herramienta_id
                )
                .scalar()
            )
            stock_total = stock_total if stock_total else 0

            flash(
                f"Estado actualizado correctamente. El stock actual de la herramienta "
                f"{herramienta_sucursal.herramienta.nombre} "
                f"{herramienta_sucursal.herramienta.marca} es: {stock_total}.",
                "success"
            )
        except Exception as e:
            db.session.rollback()
            flash(f"Ocurrió un error al actualizar el estado: {str(e)}", "danger")

        return redirect(url_for("main_bp.home"))

    # Calcular el stock total por sucursal para herramientas del mismo tipo
    stock_total_por_sucursal = (
        db.session.query(
            Sucursal.nombre_sucursal,
            db.func.sum(HerramientaSucursal.cantidad_disponible).label("stock_total"),
        )
        .join(HerramientaSucursal, Sucursal.id_sucursal == HerramientaSucursal.sucursal_id)
        .filter(
            HerramientaSucursal.herramienta_id == herramienta_sucursal.herramienta_id,  # Mismo tipo de herramienta
            HerramientaSucursal.estado == "Disponible"  # Solo herramientas disponibles
        )
        .group_by(Sucursal.nombre_sucursal)
        .all()
    )

    # Preparar los estados disponibles, excluyendo el estado actual
    estados_disponibles = ["Disponible", "Reservada", "En Mantenimiento"]
    if herramienta_sucursal.estado in estados_disponibles:
        estados_disponibles.remove(herramienta_sucursal.estado)

    # Renderizar la página de transacciones
    return render_template(
        "transacciones.html",
        herramienta=herramienta_sucursal.herramienta,
        herramienta_sucursal=herramienta_sucursal,
        stock_total_por_sucursal=stock_total_por_sucursal,
        estados_disponibles=estados_disponibles,
    )



# Ver transacciones
@main_bp.route("/ver_transacciones", methods=["GET"])
@login_required
def ver_transacciones():
    """Muestra todas las transacciones registradas en el sistema."""
    transacciones = Transaccion.query.all()

    # Definir la zona horaria de Chile
    tz = pytz.timezone("America/Santiago")

    return render_template("ver_transacciones.html", transacciones=transacciones, tz=tz)


# Logout
@main_bp.route("/logout", methods=["POST"])
def logout():
    """Cierra la sesión del usuario actual."""
    session.clear()  # Limpiar todos los datos de la sesión
    flash("Sesión cerrada con éxito.")
    return redirect(url_for("main_bp.login"))


# Ruta para manejar error 404
@main_bp.app_errorhandler(404)
def page_not_found(e):
    """Muestra una página personalizada para el error 404."""
    return render_template("404.html"), 404


# Listar usuarios
@main_bp.route("/usuarios", methods=["GET"])
@login_required
@admin_required
def listar_usuarios():
    """Lista todos los usuarios registrados en el sistema (solo accesible por administradores)."""
    # Obtener todos los usuarios de la base de datos
    usuarios = Usuario.query.all()
    return render_template("listar_usuarios.html", usuarios=usuarios)


# Listar sucursales
@main_bp.route("/sucursales", methods=["GET"])
@login_required
def listar_sucursales():
    """Permite a un administrador crear un nuevo usuario en el sistema."""
    # Obtener todas las sucursales de la base de datos
    sucursales = Sucursal.query.all()
    return render_template("listar_sucursales.html", sucursales=sucursales)


# Crear Usuario
@main_bp.route("/usuarios/crear", methods=["GET", "POST"])
@admin_required
def crear_usuario():
    """
    Crea un nuevo usuario en el sistema. Accesible solo para administradores.

    - Método GET: Renderiza el formulario para ingresar los datos del nuevo usuario.
    - Método POST:
        - Recibe el nombre, correo, rol, y contraseña desde el formulario.
        - Verifica si el correo ya está registrado.
        - Si no existe, crea el usuario con un hash de la contraseña y guarda en la base de datos.
        - Redirige al listado de usuarios y muestra un mensaje de éxito.
    """
    if request.method == "POST":
        nombre = request.form["nombre"]
        correo = request.form["correo"]
        rol = request.form["rol"]
        password = request.form["password"]

        usuario_existente = Usuario.query.filter_by(correo=correo).first()
        if usuario_existente:
            flash("Ya existe un usuario con ese correo", "danger")
            return redirect(url_for("main_bp.crear_usuario"))

        nuevo_usuario = Usuario(
            nombre=nombre,
            correo=correo,
            rol=rol,
            password_hash=generate_password_hash(password),
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        flash("Usuario creado correctamente", "success")
        return redirect(url_for("main_bp.listar_usuarios"))

    return render_template("crear_usuario.html")


# Crear Sucursal
@main_bp.route("/sucursales/crear", methods=["GET", "POST"])
@login_required
@admin_required
def crear_sucursal():
    """
    Crea una nueva sucursal en el sistema. Requiere autenticación y rol de administrador.

    - Método GET: Renderiza el formulario para ingresar los datos de la nueva sucursal.
    - Método POST:
        - Recibe el nombre y ubicación desde el formulario.
        - Valida que ambos campos no estén vacíos.
        - Crea la sucursal y la guarda en la base de datos.
        - Redirige al listado de sucursales y muestra un mensaje de éxito.
    """
    if request.method == "POST":
        nombre = request.form.get("nombre_sucursal")
        ubicacion = request.form.get("ubicacion")

        if not nombre or not ubicacion:
            flash("Todos los campos son obligatorios.", "danger")
            return render_template("crear_sucursal.html")

        nueva_sucursal = Sucursal(nombre_sucursal=nombre, ubicacion=ubicacion)
        db.session.add(nueva_sucursal)
        db.session.commit()
        flash("Sucursal creada correctamente", "success")
        return redirect(url_for("main_bp.listar_sucursales"))

    return render_template("crear_sucursal.html")


# Listar herramientas para eliminar
@main_bp.route("/herramientas/eliminar", methods=["GET", "POST"])
@login_required
@admin_required
def listar_herramientas_para_eliminar():
    # Obtener el ID de la sucursal activa desde la sesión
    sucursal_id = session.get("sucursal_id")
    if not sucursal_id:
        flash("No se encontró la sucursal activa. Por favor, inicia sesión nuevamente.", "danger")
        return redirect(url_for("main_bp.home"))

    # Parámetros de búsqueda y paginación
    search_query = request.args.get("search", "").strip().upper()
    page = request.args.get("page", 1, type=int)

    if page < 1:
        flash("Número de página no válido.", "warning")
        return redirect(url_for("main_bp.listar_herramientas_para_eliminar"))

    # Construir la consulta base
    query = (
        db.session.query(HerramientaSucursal)
        .join(Herramienta, HerramientaSucursal.herramienta_id == Herramienta.id_herramienta)
        .filter(HerramientaSucursal.sucursal_id == sucursal_id)
        .options(db.joinedload(HerramientaSucursal.herramienta))
    )

    # Filtros de búsqueda avanzados
    if search_query:
        search_terms = search_query.split()
        query = query.filter(
            db.or_(
                Herramienta.nombre.ilike(f"%{search_query}%"),
                Herramienta.marca.ilike(f"%{search_query}%"),
                HerramientaSucursal.codigo.ilike(f"%{search_query}%"),
                db.and_(
                    Herramienta.nombre.ilike(f"%{search_terms[0]}%"),
                    Herramienta.marca.ilike(f"%{' '.join(search_terms[1:])}%") if len(search_terms) > 1 else None,
                ),
                db.and_(
                    Herramienta.nombre.ilike(f"%{search_terms[0]}%"),
                    Herramienta.marca.ilike(f"%{search_terms[1]}%") if len(search_terms) > 1 else None,
                    HerramientaSucursal.codigo.ilike(f"%{search_terms[2]}%") if len(search_terms) > 2 else None,
                )
            )
        )

    # Aplicar paginación
    try:
        herramientas = query.paginate(page=page, per_page=10)
    except Exception as e:
        print(f"Error en paginación: {e}")
        herramientas = None
        flash("Error al obtener los resultados paginados.", "danger")

    # Manejo de eliminación
    if request.method == "POST":
        herramienta_sucursal_id = request.form.get("herramienta_sucursal_id")
        herramienta_sucursal = HerramientaSucursal.query.get_or_404(herramienta_sucursal_id)

        try:
            # Eliminar herramienta-sucursal
            db.session.delete(herramienta_sucursal)

            # Si no hay más relaciones, eliminar también la herramienta principal
            relaciones_restantes = HerramientaSucursal.query.filter_by(
                herramienta_id=herramienta_sucursal.herramienta_id
            ).count()

            if relaciones_restantes == 0:
                herramienta = Herramienta.query.get(herramienta_sucursal.herramienta_id)
                db.session.delete(herramienta)

            db.session.commit()
            flash("Herramienta eliminada con éxito.", "success")
            return redirect(url_for("main_bp.listar_herramientas_para_eliminar"))
        except Exception as e:
            db.session.rollback()
            flash(f"Ocurrió un error al eliminar la herramienta: {str(e)}", "danger")

    return render_template(
        "eliminar_herramienta.html", 
        herramientas=herramientas, 
        search_query=search_query
    )


@main_bp.route("/reportes")
@login_required
def reportes():
    """
    Genera un reporte detallado de transacciones de herramientas.
    """
    # Consulta para generar el reporte
    transacciones = (
        db.session.query(
            Herramienta.nombre,
            Herramienta.marca,
            HerramientaSucursal.codigo,
            Sucursal.nombre_sucursal,  # Obtener el nombre de la sucursal
            Transaccion.estado_anterior,
            Transaccion.estado_nuevo,
            Transaccion.fecha,
        )
        .join(HerramientaSucursal, HerramientaSucursal.id == Transaccion.herramienta_sucursal_id)
        .join(Herramienta, Herramienta.id_herramienta == HerramientaSucursal.herramienta_id)
        .join(Sucursal, Sucursal.id_sucursal == Transaccion.sucursal_id)  # Relación con la sucursal
        .filter(Transaccion.sucursal_id == session.get("sucursal_id"))  # Filtrar por sucursal activa
        .order_by(Transaccion.fecha.desc())  # Ordenar por fecha descendente
        .all()
    )

    return render_template("reportes.html", transacciones=transacciones)



# Descargar reporte en CSV
@main_bp.route("/reportes/csv")
@login_required
def descargar_csv():
    """
    Genera y permite la descarga de un reporte en formato CSV.
    """
    transacciones = (
        db.session.query(
            Herramienta.nombre,
            Herramienta.marca,
            HerramientaSucursal.codigo,
            Sucursal.nombre_sucursal,
            Transaccion.estado_anterior,
            Transaccion.estado_nuevo,
            Transaccion.fecha,
        )
        .join(HerramientaSucursal, HerramientaSucursal.id == Transaccion.herramienta_sucursal_id)
        .join(Herramienta, Herramienta.id_herramienta == HerramientaSucursal.herramienta_id)
        .join(Sucursal, Sucursal.id_sucursal == Transaccion.sucursal_id)
        .filter(Transaccion.sucursal_id == session.get("sucursal_id"))
        .order_by(Transaccion.fecha.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Nombre Herramienta", "Marca", "Código", "Sucursal", "Estado Anterior", "Estado Nuevo", "Fecha"]
    )

    for transaccion in transacciones:
        writer.writerow(
            [
                transaccion[0],  # Nombre Herramienta
                transaccion[1],  # Marca
                transaccion[2],  # Código
                transaccion[3],  # Sucursal
                transaccion[4],  # Estado Anterior
                transaccion[5],  # Estado Nuevo
                transaccion[6].strftime("%Y-%m-%d"),  # Fecha
            ]
        )

    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=reporte.csv"},
    )


# Descargar reporte en Excel
@main_bp.route("/reportes/excel")
@login_required
def descargar_excel():
    """
    Genera y permite la descarga de un reporte en formato Excel.
    """
    try:
        transacciones = (
            db.session.query(
                Herramienta.nombre,
                Herramienta.marca,
                HerramientaSucursal.codigo,
                Sucursal.nombre_sucursal,
                Transaccion.estado_anterior,
                Transaccion.estado_nuevo,
                Transaccion.fecha,
            )
            .join(HerramientaSucursal, HerramientaSucursal.id == Transaccion.herramienta_sucursal_id)
            .join(Herramienta, Herramienta.id_herramienta == HerramientaSucursal.herramienta_id)
            .join(Sucursal, Sucursal.id_sucursal == Transaccion.sucursal_id)
            .filter(Transaccion.sucursal_id == session.get("sucursal_id"))
            .order_by(Transaccion.fecha.desc())
            .all()
        )

        # Crear DataFrame para Excel
        df = pd.DataFrame(
            {
                "Nombre Herramienta": [t[0] for t in transacciones],
                "Marca": [t[1] for t in transacciones],
                "Código": [t[2] for t in transacciones],
                "Sucursal": [t[3] for t in transacciones],
                "Estado Anterior": [t[4] for t in transacciones],
                "Estado Nuevo": [t[5] for t in transacciones],
                "Fecha": [t[6].strftime("%Y-%m-%d %H:%M:%S") for t in transacciones],
            }
        )

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Reporte")

        output.seek(0)
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="reporte.xlsx",
        )
    except Exception as e:
        flash(f"Error al generar el reporte en Excel: {str(e)}", "danger")
        return redirect(url_for("main_bp.reportes"))


# Eliminar Sucursal
@main_bp.route("/sucursales/eliminar/<int:id_sucursal>", methods=["POST"])
@login_required
@admin_required
def eliminar_sucursal(id_sucursal):
    """
    Elimina una sucursal específica del sistema.
    Requiere autenticación y rol de administrador.

    - Busca la sucursal por su ID.
    - Intenta eliminar la sucursal de la base de datos.
    - Si ocurre un error, realiza rollback y muestra el error.
    - Muestra un mensaje de éxito si se elimina exitosamente.
    """
    sucursal = Sucursal.query.get_or_404(id_sucursal)

    try:
        db.session.delete(sucursal)
        db.session.commit()
        flash("Sucursal eliminada exitosamente", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al eliminar la sucursal: {str(e)}", "danger")

    return redirect(url_for("main_bp.listar_sucursales"))


# Listar Sucursales para Eliminar
@main_bp.route("/sucursales/eliminar", methods=["GET"])
@login_required
@admin_required
def listar_para_eliminar_sucursales():
    """
    Lista todas las sucursales en el sistema para que puedan ser seleccionadas y eliminadas.
    Requiere autenticación y rol de administrador.
    """
    sucursales = Sucursal.query.all()
    return render_template("eliminar_sucursal.html", sucursales=sucursales)


@login_required
def registrar_transaccion(herramienta_sucursal_id, estado_anterior, estado_nuevo, cantidad):
    try:
        # Validar que la cantidad no sea mayor al stock disponible
        herramienta_sucursal = HerramientaSucursal.query.get(herramienta_sucursal_id)
        if herramienta_sucursal.cantidad_disponible < cantidad:
            raise ValueError("Cantidad insuficiente para realizar la transacción")

        # Registrar la transacción
        nueva_transaccion = Transaccion(
            herramienta_sucursal_id=herramienta_sucursal_id,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            cantidad=cantidad,
            sucursal_id=session.get("sucursal_id"),  # Sucursal activa
        )
        db.session.add(nueva_transaccion)

        # Actualizar el stock disponible
        if estado_nuevo in ["Reservada", "En Mantenimiento"]:
            herramienta_sucursal.cantidad_disponible -= cantidad
        elif estado_anterior in ["Reservada", "En Mantenimiento"] and estado_nuevo == "Disponible":
            herramienta_sucursal.cantidad_disponible += cantidad

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise e

#Eliminar usuarios
@main_bp.route("/usuarios/eliminar/<int:id_usuario>", methods=["POST"])
@login_required
@admin_required
def eliminar_usuario(id_usuario):
    """
    Elimina un usuario específico del sistema.
    Requiere autenticación y rol de administrador.

    
Busca el usuario por su ID.
Intenta eliminar el usuario de la base de datos.
Si ocurre un error, realiza rollback y muestra el error.
Muestra un mensaje de éxito si se elimina exitosamente.
"""
    usuario = Usuario.query.get_or_404(id_usuario)

    try:
        db.session.delete(usuario)
        db.session.commit()
        flash("Usuario eliminado exitosamente", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al eliminar el usuario: {str(e)}", "danger")

    return redirect(url_for("main_bp.listar_usuarios"))

#Listar usuario para eliminar
@main_bp.route("/usuarios/eliminar", methods=["GET"])
@login_required
@admin_required
def listar_para_eliminar_usuarios():
    """
    Lista todos los usuarios en el sistema para que puedan ser seleccionados y eliminados.
    Requiere autenticación y rol de administrador.
    """
    usuarios = Usuario.query.all()
    return render_template("eliminar_usuarios.html", usuarios=usuarios)

#Recuperar contraseña
@main_bp.route("/recuperar_contraseña", methods=["GET", "POST"])
def recuperar_contraseña():
    if request.method == "POST":
        correo = request.form.get("correo")

        # Verifica si el correo está registrado
        usuario = Usuario.query.filter_by(correo=correo).first()
        if not usuario:
            flash("El correo no está registrado.", "danger")
            return redirect(url_for("main_bp.recuperar_contraseña"))
        
        if not validar_correo(correo):
            flash("El formato del correo es inválido.", "danger")
            return redirect(url_for("main_bp.recuperar_contraseña"))


        # Comprueba si serializer está inicializado
        if serializer is None:
            raise RuntimeError("El serializer no se inicializó correctamente")

        # Genera un token seguro
        token = serializer.dumps(correo, salt="recuperar-contrasena")

        # URL para resetear la contraseña
        reset_url = url_for("main_bp.resetear_contraseña", token=token, _external=True)

        # Enviar correo con el link
        mensaje = Message(
            "Recuperación de Contraseña",
            recipients=[correo],
            body=f"Haz clic en el siguiente enlace para resetear tu contraseña: {reset_url}",
        )
        mail.send(mensaje)

        flash("Se ha enviado un correo con las instrucciones para recuperar tu contraseña.", "info")
        return redirect(url_for("main_bp.login"))

    return render_template("recuperar_contraseña.html")

#Resetear contraseña
@main_bp.route("/resetear_contraseña/<token>", methods=["GET", "POST"])
def resetear_contraseña(token):
    try:
        # Decodificar el token
        correo = serializer.loads(token, salt="recuperar-contrasena", max_age=3600)
        print(f"Token válido, correo: {correo}")  # Para depuración
    except Exception as e:
        print(f"Error al procesar el token: {e}")  # Para depuración
        flash("El enlace para restablecer la contraseña ha expirado o no es válido.", "danger")
        return redirect(url_for("main_bp.recuperar_contraseña"))

    if request.method == "POST":
        # Obtener contraseñas desde el formulario
        nueva_contraseña = request.form.get("nueva_contraseña")
        confirmar_contraseña = request.form.get("confirmar_contraseña")

        # Validar contraseñas
        if nueva_contraseña != confirmar_contraseña:
            flash("Las contraseñas no coinciden.", "danger")
            return redirect(url_for("main_bp.resetear_contraseña", token=token))

        # Buscar usuario en la base de datos
        usuario = Usuario.query.filter_by(correo=correo).first()

        if usuario:
            try:
                # Genera un nuevo hash y actualiza en la columna password_hash
                usuario.password_hash = generar_hash(nueva_contraseña)
                db.session.commit()
                print(f"Contraseña actualizada para el usuario con correo: {correo}")  # Para depuración
                flash("Tu contraseña ha sido actualizada exitosamente.", "success")
                return redirect(url_for("main_bp.login"))
            except Exception as e:
                print(f"Error al actualizar la contraseña: {e}")  # Para depuración
                db.session.rollback()
                flash("Hubo un problema al actualizar la contraseña. Por favor, inténtalo nuevamente.", "danger")
                return redirect(url_for("main_bp.resetear_contraseña", token=token))
        else:
            flash("Usuario no encontrado.", "danger")
            return redirect(url_for("main_bp.recuperar_contraseña"))

    # En caso de método GET, renderizar el formulario
    return render_template("resetear_contraseña.html", token=token)

@main_bp.route('/modificar_ubicacion/<int:sucursal_id>', methods=['GET', 'POST'])
@login_required
def modificar_ubicacion(sucursal_id):
    # Obtener la sucursal por ID
    sucursal = Sucursal.query.get_or_404(sucursal_id)

    if request.method == 'POST':
        # Capturar la nueva ubicación desde el formulario
        nueva_ubicacion = request.form.get('ubicacion')

        # Validar que la ubicación no esté vacía
        if not nueva_ubicacion or nueva_ubicacion.strip() == "":
            flash("La ubicación no puede estar vacía.", "danger")
            return render_template('modificar_ubicacion.html', sucursal=sucursal)

        try:
            # Actualizar la ubicación
            sucursal.ubicacion = nueva_ubicacion.strip()
            db.session.commit()
            flash("Ubicación actualizada correctamente.", "success")
            return redirect(url_for('main_bp.listar_sucursales'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al actualizar la ubicación: {str(e)}", "danger")

    # Renderizar el formulario con la ubicación actual
    return render_template('modificar_ubicacion.html', sucursal=sucursal)

@main_bp.route("/sucursales/modificar_nombre/<int:sucursal_id>", methods=["GET", "POST"])
@login_required
def modificar_nombre(sucursal_id):
    sucursal = db.session.query(Sucursal).filter_by(id_sucursal=sucursal_id).first()

    if not sucursal:
        flash("Sucursal no encontrada.", "danger")
        return redirect(url_for("main_bp.listar_sucursales"))

    if request.method == "POST":
        nuevo_nombre = request.form.get("nombre_sucursal")

        if not nuevo_nombre or len(nuevo_nombre.strip()) == 0:
            flash("El nombre de la sucursal no puede estar vacío.", "danger")
            return render_template("modificar_nombre.html", sucursal=sucursal)

        sucursal.nombre_sucursal = nuevo_nombre.strip()

        try:
            db.session.commit()
            flash("Nombre de la sucursal actualizado correctamente.", "success")
            return redirect(url_for("main_bp.listar_sucursales"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al actualizar el nombre: {e}", "danger")
            return render_template("modificar_nombre.html", sucursal=sucursal)

    return render_template("modificar_nombre.html", sucursal=sucursal)


#Buscar herramienta
@main_bp.route("/buscar_herramienta", methods=["GET"])
@login_required
def buscar_herramienta():
    # Obtener el término de búsqueda desde los parámetros
    search_query = request.args.get("search", "").strip().upper()
    page = request.args.get("page", 1, type=int)

    # Inicializar herramientas como None si no hay búsqueda activa
    herramientas = None

    # Solo realizar la búsqueda si se proporciona un término
    if search_query:
        # Dividir el término de búsqueda en palabras clave
        keywords = search_query.split()

        # Consulta base para herramientas disponibles
        query = (
            db.session.query(Herramienta, HerramientaSucursal, Sucursal)
            .join(HerramientaSucursal, Herramienta.id_herramienta == HerramientaSucursal.herramienta_id)
            .join(Sucursal, Sucursal.id_sucursal == HerramientaSucursal.sucursal_id)
            .filter(HerramientaSucursal.estado == "Disponible")  # Solo herramientas disponibles
        )

        # Agregar filtros combinados para nombre y marca
        if keywords:
            query = query.filter(
                db.and_(
                    *(db.or_(
                        Herramienta.nombre.ilike(f"%{keyword}%"),
                        Herramienta.marca.ilike(f"%{keyword}%")
                    ) for keyword in keywords)
                )
            )

        # Paginación
        herramientas = query.paginate(page=page, per_page=10)

    return render_template(
        "buscar_herramienta.html",
        herramientas=herramientas,
        search_query=search_query
    )


