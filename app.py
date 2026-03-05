from utils.database import *
from flask import Flask, render_template, request, redirect, url_for, send_file, session
import sqlite3
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

app = Flask(__name__)

app.secret_key = "g7@9d#s1!Sistema_cotización"

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cotizaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT,
        cliente TEXT,
        fecha TEXT,
        subtotal REAL,
        itbis REAL,
        total REAL,
        estado TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cotizacion_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cotizacion_id INTEGER,
        descripcion TEXT,
        cantidad REAL,
        precio REAL,
        total REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ncf TEXT,
        rnc TEXT,
        cliente TEXT,
        fecha TEXT,
        subtotal REAL,
        itbis REAL,
        total REAL,
        cotizacion_id INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS factura_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        factura_id INTEGER,
        descripcion TEXT,
        cantidad REAL,
        precio REAL,
        total REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion_ncf (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT,
        desde INTEGER,
        hasta INTEGER,
        actual INTEGER
    )
    """)

    cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE,
    password TEXT
)
""")

    cursor.execute("""
INSERT OR IGNORE INTO usuarios (usuario, password)
VALUES ('admin', '1234')
""")

    user = cursor.execute("SELECT * FROM usuarios").fetchone()

    if not user:
        cursor.execute("""
    INSERT INTO usuarios (usuario, password)
    VALUES (?, ?)
    """, ("admin", "1234"))
        
    cursor.execute("""
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    rnc TEXT,
    telefono TEXT,
    direccion TEXT
)
""")

    conn.commit()
    conn.close()


@app.route("/")
def index():

    if "usuario" not in session:
        return redirect(url_for("login"))

    buscar = request.args.get("buscar")

    conn = get_db()

    if buscar:
        cotizaciones = conn.execute("""
        SELECT * FROM cotizaciones
        WHERE estado != 'Eliminada'
        AND cliente LIKE ?
        ORDER BY id DESC
        """, ("%" + buscar + "%",)).fetchall()
    else:
        cotizaciones = conn.execute("""
        SELECT * FROM cotizaciones
        WHERE estado != 'Eliminada'
        ORDER BY id DESC
        """).fetchall()

    pendientes = conn.execute("""
    SELECT COUNT(*) FROM cotizaciones
    WHERE estado='Pendiente'
    """).fetchone()[0]

    aprobadas = conn.execute("""
    SELECT COUNT(*) FROM cotizaciones
    WHERE estado='Aprobada'
    """).fetchone()[0]

    facturadas = conn.execute("""
    SELECT COUNT(*) FROM cotizaciones
    WHERE estado='Facturada'
    """).fetchone()[0]

    total_facturado = conn.execute("""
    SELECT SUM(total) FROM facturas
    """).fetchone()[0]

    if total_facturado is None:
        total_facturado = 0

    conn.close()

    return render_template(
        "index.html",
        cotizaciones=cotizaciones,
        pendientes=pendientes,
        aprobadas=aprobadas,
        facturadas=facturadas,
        total_facturado=total_facturado
    )

@app.route("/historial")
def historial():

    conn = get_db()

    cotizaciones = conn.execute("""
    SELECT * FROM cotizaciones
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "historial.html",
        cotizaciones=cotizaciones
    )

@app.route("/facturas")
def facturas():

    conn = get_db()

    facturas = conn.execute("""
    SELECT * FROM facturas
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "facturas.html",
        facturas=facturas
    )

@app.route("/nueva", methods=["GET", "POST"])
def nueva_cotizacion():

    if request.method == "POST":

        cliente = request.form["cliente"]
        subtotal = float(request.form["subtotal"])
        itbis = float(request.form["itbis"])
        total = float(request.form["total"])

        codigo = "COT-" + datetime.now().strftime("%Y%m%d%H%M%S")
        fecha = datetime.now().strftime("%d/%m/%Y")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO cotizaciones (codigo, cliente, fecha, subtotal, itbis, total, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (codigo, cliente, fecha, subtotal, itbis, total, "Pendiente"))

        cotizacion_id = cursor.lastrowid

        descripciones = request.form.getlist("descripcion[]")
        cantidades = request.form.getlist("cantidad[]")
        precios = request.form.getlist("precio[]")
        totales = request.form.getlist("total_linea[]")

        for i in range(len(descripciones)):

            cursor.execute("""
            INSERT INTO cotizacion_items (cotizacion_id, descripcion, cantidad, precio, total)
            VALUES (?, ?, ?, ?, ?)
            """, (
                cotizacion_id,
                descripciones[i],
                cantidades[i],
                precios[i],
                totales[i]
            ))

        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    return render_template("nueva_cotizacion.html")


@app.route("/aprobar/<int:id>")
def aprobar(id):

    conn = get_db()

    conn.execute(
        "UPDATE cotizaciones SET estado='Aprobada' WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("index"))


@app.route("/eliminar/<int:id>")
def eliminar_cotizacion(id):

    conn = get_db()

    conn.execute(
        "UPDATE cotizaciones SET estado='Eliminada' WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("index"))


@app.route("/facturar/<int:id>", methods=["GET", "POST"])
def facturar(id):

    conn = get_db()

    cotizacion = conn.execute(
        "SELECT * FROM cotizaciones WHERE id=?",
        (id,)
    ).fetchone()

    items = conn.execute(
        "SELECT * FROM cotizacion_items WHERE cotizacion_id=?",
        (id,)
    ).fetchall()

    config = conn.execute(
        "SELECT * FROM configuracion_ncf LIMIT 1"
    ).fetchone()

    if config is None:
        conn.close()
        return "Debes configurar el NCF primero"

    if request.method == "POST":

        rnc = request.form["rnc"]

        siguiente = config["actual"] + 1

        if siguiente > config["hasta"]:
            return "Rango NCF agotado"

        numero_formateado = str(siguiente).zfill(8)
        ncf = config["tipo"] + numero_formateado

        fecha = datetime.now().strftime("%d/%m/%Y")

        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO facturas (ncf, rnc, cliente, fecha, subtotal, itbis, total, cotizacion_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ncf,
            rnc,
            cotizacion["cliente"],
            fecha,
            cotizacion["subtotal"],
            cotizacion["itbis"],
            cotizacion["total"],
            id
        ))

        factura_id = cursor.lastrowid

        for item in items:

            cursor.execute("""
            INSERT INTO factura_items (factura_id, descripcion, cantidad, precio, total)
            VALUES (?, ?, ?, ?, ?)
            """, (
                factura_id,
                item["descripcion"],
                item["cantidad"],
                item["precio"],
                item["total"]
            ))

        cursor.execute(
            "UPDATE configuracion_ncf SET actual=?",
            (siguiente,)
        )

        cursor.execute(
            "UPDATE cotizaciones SET estado='Facturada' WHERE id=?",
            (id,)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    conn.close()

    return render_template(
        "factura.html",
        cotizacion=cotizacion,
        items=items
    )


@app.route("/configurar_ncf", methods=["GET", "POST"])
def configurar_ncf():

    conn = get_db()

    if request.method == "POST":

        tipo = request.form["tipo"]
        desde = int(request.form["desde"])
        hasta = int(request.form["hasta"])

        conn.execute("DELETE FROM configuracion_ncf")

        conn.execute("""
        INSERT INTO configuracion_ncf (tipo, desde, hasta, actual)
        VALUES (?, ?, ?, ?)
        """, (
            tipo,
            desde,
            hasta,
            desde - 1
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    config = conn.execute(
        "SELECT * FROM configuracion_ncf LIMIT 1"
    ).fetchone()

    conn.close()

    return render_template(
        "configurar_ncf.html",
        config=config
    )


@app.route("/factura_pdf/<int:id>")
def factura_pdf(id):

    conn = get_db()

    factura = conn.execute(
        "SELECT * FROM facturas WHERE cotizacion_id=?",
        (id,)
    ).fetchone()

    items = conn.execute(
        "SELECT * FROM factura_items WHERE factura_id=?",
        (factura["id"],)
    ).fetchall()

    conn.close()

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    y = 750

    # TITULO
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, y, "FACTURA")

    y -= 40

    # INFO EMPRESA
    p.setFont("Helvetica", 12)
    p.drawString(50, y, "Empresa: Mi Empresa SRL")
    y -= 20
    p.drawString(50, y, "RNC: 130000000")

    y -= 30

    # INFO CLIENTE
    p.drawString(50, y, f"NCF: {factura['ncf']}")
    y -= 20
    p.drawString(50, y, f"Cliente: {factura['cliente']}")
    y -= 20
    p.drawString(50, y, f"RNC Cliente: {factura['rnc']}")
    y -= 20
    p.drawString(50, y, f"Fecha: {factura['fecha']}")

    y -= 40

    # ENCABEZADO TABLA
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y, "Descripción")
    p.drawString(300, y, "Cantidad")
    p.drawString(380, y, "Precio")
    p.drawString(460, y, "Total")

    y -= 10
    p.line(50, y, 550, y)

    y -= 20

    # ITEMS
    p.setFont("Helvetica", 11)

    for item in items:

        p.drawString(50, y, item["descripcion"])
        p.drawString(300, y, str(item["cantidad"]))
        p.drawString(380, y, str(item["precio"]))
        p.drawString(460, y, str(item["total"]))

        y -= 20

    y -= 20

    # TOTALES
    p.setFont("Helvetica-Bold", 12)

    p.drawString(380, y, f"Subtotal: RD$ {factura['subtotal']}")
    y -= 20
    p.drawString(380, y, f"ITBIS: RD$ {factura['itbis']}")
    y -= 20
    p.drawString(380, y, f"TOTAL: RD$ {factura['total']}")

    p.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="factura.pdf",
        mimetype="application/pdf"
    )

@app.route("/eliminar_factura/<int:id>")
def eliminar_factura(id):

    conn = get_db()

    # buscar la factura
    factura = conn.execute(
        "SELECT * FROM facturas WHERE id=?",
        (id,)
    ).fetchone()

    if factura:

        # devolver cotización a aprobada
        conn.execute(
            "UPDATE cotizaciones SET estado='Aprobada' WHERE id=?",
            (factura["cotizacion_id"],)
        )

        # borrar items
        conn.execute(
            "DELETE FROM factura_items WHERE factura_id=?",
            (id,)
        )

        # borrar factura
        conn.execute(
            "DELETE FROM facturas WHERE id=?",
            (id,)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("index"))

@app.route("/reset_facturas")
def reset_facturas():

    conn = get_db()

    conn.execute("DELETE FROM factura_items")
    conn.execute("DELETE FROM facturas")

    conn.commit()
    conn.close()

    return redirect(url_for("index"))

@app.route("/cotizacion_pdf/<int:id>")
def cotizacion_pdf(id):

    conn = get_db()

    cotizacion = conn.execute(
        "SELECT * FROM cotizaciones WHERE id=?",
        (id,)
    ).fetchone()

    items = conn.execute(
        "SELECT * FROM cotizacion_items WHERE cotizacion_id=?",
        (id,)
    ).fetchall()

    conn.close()

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)

    y = 750

    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y, "COTIZACIÓN")

    y -= 40

    p.drawString(50, y, f"Código: {cotizacion['codigo']}")
    y -= 20
    p.drawString(50, y, f"Cliente: {cotizacion['cliente']}")
    y -= 20
    p.drawString(50, y, f"Fecha: {cotizacion['fecha']}")

    y -= 40

    for item in items:
        p.drawString(50, y, item["descripcion"])
        p.drawString(300, y, str(item["cantidad"]))
        p.drawString(380, y, str(item["precio"]))
        p.drawString(460, y, str(item["total"]))
        y -= 20

    y -= 20

    p.drawString(380, y, f"Subtotal: {cotizacion['subtotal']}")
    y -= 20
    p.drawString(380, y, f"ITBIS: {cotizacion['itbis']}")
    y -= 20
    p.drawString(380, y, f"Total: {cotizacion['total']}")

    p.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="cotizacion.pdf",
        mimetype="application/pdf"
    )


@app.route("/detalle/<int:id>")
def detalle(id):

    conn = get_db()

    cotizacion = conn.execute(
        "SELECT * FROM cotizaciones WHERE id=?",
        (id,)
    ).fetchone()

    items = conn.execute(
        "SELECT * FROM cotizacion_items WHERE cotizacion_id=?",
        (id,)
    ).fetchall()

    conn.close()

    return render_template(
        "detalle.html",
        cotizacion=cotizacion,
        items=items
    )

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        usuario = request.form["usuario"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM usuarios WHERE usuario=? AND password=?",
            (usuario, password)
        ).fetchone()

        conn.close()

        if user:
            session ["usuario"] = usuario
            return redirect(url_for("index"))
        else:
            return "Usuario o contraseña incorrectos"

    return render_template("login.html")

from flask import session, redirect, url_for

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/usuarios", methods=["GET","POST"])
def usuarios():

    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":

        nuevo_usuario = request.form["usuario"]
        nueva_password = request.form["password"]

        conn.execute("""
        UPDATE usuarios
        SET usuario=?, password=?
        WHERE id=1
        """, (nuevo_usuario, nueva_password))

        conn.commit()

    user = conn.execute("SELECT * FROM usuarios LIMIT 1").fetchone()

    conn.close()

    return render_template("usuarios.html", user=user)

@app.route("/clientes", methods=["GET","POST"])
def clientes():

    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":

        nombre = request.form["nombre"]
        rnc = request.form["rnc"]
        telefono = request.form["telefono"]
        direccion = request.form["direccion"]

        conn.execute("""
        INSERT INTO clientes (nombre, rnc, telefono, direccion)
        VALUES (?, ?, ?, ?)
        """, (nombre, rnc, telefono, direccion))

        conn.commit()

    buscar = request.args.get("buscar")

    if buscar:
        clientes = conn.execute("""
        SELECT * FROM clientes
        WHERE nombre LIKE ?
        ORDER BY id DESC
        """, ("%" + buscar + "%",)).fetchall()
    else:
        clientes = conn.execute("SELECT * FROM clientes ORDER BY id DESC").fetchall()

    conn.close()

    return render_template("clientes.html", clientes=clientes)

@app.route("/eliminar_cliente/<int:id>")
def eliminar_cliente(id):

    conn = get_db()

    conn.execute(
        "DELETE FROM clientes WHERE id=?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("clientes"))

@app.route("/editar_cliente/<int:id>", methods=["GET","POST"])
def editar_cliente(id):

    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    cliente = conn.execute(
        "SELECT * FROM clientes WHERE id=?",
        (id,)
    ).fetchone()

    if request.method == "POST":

        nombre = request.form["nombre"]
        rnc = request.form["rnc"]
        telefono = request.form["telefono"]
        direccion = request.form["direccion"]

        conn.execute("""
        UPDATE clientes
        SET nombre=?, rnc=?, telefono=?, direccion=?
        WHERE id=?
        """, (nombre, rnc, telefono, direccion, id))

        conn.commit()
        conn.close()

        return redirect(url_for("clientes"))

    conn.close()

    return render_template(
        "editar_cliente.html",
        cliente=cliente
    )

if __name__ == "__main__":

    init_db()

    app.run(debug=True)