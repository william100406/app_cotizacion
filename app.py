import utils.database as db
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from datetime import datetime, timedelta
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
import io
import os
import re

app = Flask(__name__)

load_dotenv()

app.secret_key = os.environ.get("SECRET_KEY", "g7@9d#s1!Sistema_cotización")
app.permanent_session_lifetime = timedelta(days=7)

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no está configurada")


class CursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = None

    def execute(self, sql, params=None):
        sql = sql.replace("?", "%s")

        try:
            if sql.strip().lower().startswith("insert") and "returning" not in sql.lower():
                sql = sql.rstrip(";") + " RETURNING id"
                self.cursor.execute(sql, params)
                row = self.cursor.fetchone()

                if row and "id" in row:
                    self.lastrowid = row["id"]
            else:
                self.cursor.execute(sql, params)

        except Exception as e:
            self.cursor.connection.rollback()
            raise e

        return self

    def executemany(self, sql, params):
        sql = sql.replace("?", "%s")
        self.cursor.executemany(sql, params)
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        return self.cursor.close()

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class DBWrapper:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL, sslmode="require")

    def cursor(self):
        return CursorWrapper(
            self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        )

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def get_db():
    return DBWrapper()


def money(value):
    try:
        return f"$ {float(value):,.2f}"
    except Exception:
        return "$ 0.00"


def validar_telefono(telefono):
    telefono = telefono or ""

   
    if not re.match(r"^[0-9+\-\s()]+$", telefono):
        return False

    numeros = re.sub(r"\D", "", telefono)

    return 7 <= len(numeros) <= 15


def generar_codigo_cotizacion(conn):
    year = datetime.now().year

    ultimo = conn.execute(
        """
        SELECT codigo FROM cotizaciones
        WHERE codigo LIKE %s
        ORDER BY id DESC LIMIT 1
        """,
        (f"COT-{year}-%",),
    ).fetchone()

    if ultimo and ultimo.get("codigo"):
        try:
            ultimo_num = int(str(ultimo["codigo"]).split("-")[-1])
        except Exception:
            ultimo_num = 0
        nuevo_num = ultimo_num + 1
    else:
        nuevo_num = 1

    return f"COT-{year}-{nuevo_num:06d}"


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id SERIAL PRIMARY KEY,
            codigo TEXT,
            cliente TEXT,
            rnc TEXT,
            telefono TEXT,
            correo TEXT,
            fecha TEXT,
            subtotal REAL,
            itbis REAL,
            total REAL,
            estado TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cotizacion_items (
            id SERIAL PRIMARY KEY,
            cotizacion_id INTEGER,
            descripcion TEXT,
            cantidad REAL,
            precio REAL,
            total REAL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS servicios (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            precio_a REAL,
            precio_b REAL,
            precio_c REAL
        )
        """
    )

    servicios = [
        ("Hora de Trabajo", 24, 24, 24),
        ("Nueva Identidad Corporativa", 1480, 890, 520),
        ("Nuevo logotipo / isotipo / imagotipo / isologo", 0, 0, 300),
        ("Rediseño Identidad Corporativa", 1480, 890, 520),
        ("Rediseño logotipo / isotipo / imagotipo / isologo", 0, 0, 360),
        ("Restyling Identidad Corporativa", 1030, 660, 370),
        ("Restyling logotipo / isotipo / imagotipo / isologo", 0, 0, 210),
        ("Manual de normas / uso", 320, 220, 150),
        ("Identidad efímera", 540, 410, 270),
        ("Identidad de un producto", 1030, 810, 520),
        ("Naming corporativo / institucional", 370, 260, 150),
        ("Naming producto / evento", 370, 260, 150),
        ("Slogan / Lema", 240, 180, 120),
        ("Claim", 240, 180, 120),
        ("Prenda única", 160, 120, 80),
        ("Sistema de uniformes / vestuario", 890, 660, 450),
        ("Papelería básica", 450, 290, 190),
        ("Papelería comercial", 120, 90, 60),
        ("Tarjetas personales", 80, 60, 40),
        ("Hojas membretadas", 80, 60, 40),
        ("Sobres", 80, 60, 40),
        ("Firma o encabezado de e-mail", 80, 60, 40),
        ("Carpeta empresarial / institucional", 140, 110, 80),
        ("Tarjetas para eventos", 120, 90, 60),
        ("Invitaciones empresariales", 150, 120, 90),
        ("Postal", 130, 80, 50),
        ("Volante / Flyer solo frente", 140, 100, 60),
        ("Volante / Flyer frente y dorso", 210, 150, 110),
        ("Folleto díptico", 270, 210, 150),
        ("Folleto tríptico", 320, 250, 190),
        ("Brochure", 690, 480, 240),
        ("Aviso institucional diario / revista", 130, 70, 50),
        ("Aviso institucional doble página", 160, 110, 70),
        ("Aviso publicitario diario / revista", 180, 120, 70),
        ("Aviso publicitario doble página", 210, 150, 110),
        ("Key Visual", 240, 150, 100),
        ("Redes sociales avatar + portada", 130, 100, 60),
        ("Redes sociales placa posteo", 100, 70, 50),
        ("Redes sociales gif animado", 140, 100, 70),
        ("Concurso en muro", 280, 240, 190),
        ("Social Media Plan", 260, 220, 190),
        ("Creación perfil o fanpage", 170, 130, 90),
        ("Creación de álbum", 40, 30, 20),
        ("Posteo publicación de enlace", 20, 15, 10),
        ("Gestión de Comunidad 1", 180, 160, 130),
        ("Gestión de Comunidad 2", 280, 240, 200),
        ("Monitoreo de redes", 90, 60, 40),
        ("Creatividad aviso institucional", 110, 70, 50),
        ("Creatividad folleto díptico", 130, 90, 60),
        ("Creatividad flyer frente/dorso", 110, 70, 50),
        ("Redacción gacetilla de prensa", 90, 70, 60),
        ("Nota para redes sociales corta", 30, 25, 20),
        ("Nota para redes sociales larga", 50, 40, 30),
        ("Merchandising", 350, 270, 210),
        ("Remeras", 90, 70, 50),
        ("Calcos", 70, 50, 30),
        ("Lapicera / pin / llavero", 70, 50, 30),
        ("Pad / funda celulares / taza", 70, 50, 30),
        ("Bandera", 70, 50, 30),
        ("Bolsas / Envoltorios", 90, 70, 50),
        ("Almanaque pared poster", 190, 140, 80),
        ("Almanaque pared revista", 430, 240, 140),
        ("Almanaque escritorio simple", 140, 90, 60),
        ("Almanaque escritorio móvil", 150, 100, 80),
        ("Arte de tapa", 280, 210, 140),
        ("Armado página simple", 20, 15, 10),
        ("Armado página compuesta", 30, 20, 13),
        ("Libro cuerpo y puesta en página", 1220, 910, 610),
        ("Revista", 550, 460, 360),
        ("Catálogo de productos", 810, 590, 370),
        ("Menú / carta restaurante", 310, 240, 180),
        ("Manual de instrucciones", 60, 55, 50),
        ("Folleto instructivo", 330, 280, 240),
        ("Ploteado vehicular", 280, 210, 160),
        ("Ploteado vidriera simple", 140, 100, 70),
        ("Ploteado vidriera complejo", 340, 250, 160),
        ("Cenefa / saltarín / llamador", 170, 140, 100),
        ("Afiche", 170, 140, 100),
        ("Banner", 170, 140, 100),
        ("Cartel de fachada", 250, 190, 150),
        ("Cartel para exteriores", 270, 210, 160),
        ("Sistema señalético y soporte", 1030, 770, 520),
        ("Aplicación señalética simple", 290, 220, 150),
        ("Aplicación señalética compleja", 520, 370, 260),
        ("Señalética efímera", 740, 510, 360),
        ("Stand gráfico", 520, 370, 220),
        ("Stand diseño completo", 890, 660, 450),
        ("Modelado 3D stand baja", 120, 90, 60),
        ("Modelado 3D stand alta", 290, 220, 150),
        ("Digitalización", 50, 30, 20),
        ("Ilustración mano alzada", 340, 220, 150),
        ("Ilustración vectorial", 340, 220, 150),
        ("Ilustración modelado 3D", 590, 450, 290),
        ("Animación personaje", 680, 510, 350),
        ("Sistema de signos", 890, 520, 290),
        ("Infografía", 1030, 660, 370),
        ("CD Pack", 770, 560, 390),
        ("Etiqueta simple", 260, 150, 90),
        ("Etiqueta compuesta", 850, 660, 510),
        ("Envase", 1000, 820, 0),
        ("Modelado 3D envase", 70, 60, 50),
        ("Renderizado modelo 3D", 20, 15, 10),
        ("Animación modelo 3D", 450, 290, 150),
        ("Modificaciones sitio HTML/CSS", 220, 170, 120),
        ("Diseño landing page", 200, 140, 100),
        ("Maquetación landing page", 200, 140, 100),
        ("Implementación Wordpress", 550, 400, 280),
        ("Diseño sitio HTML5 CSS3", 710, 610, 510),
        ("Maquetación sitio HTML5 CSS3", 710, 610, 510),
        ("Diseño sitio responsive", 1030, 880, 740),
        ("Maquetación sitio responsive", 1030, 880, 740),
        ("Programación PHP autogestión", 480, 410, 340),
        ("Diseño sitio móvil", 480, 410, 340),
        ("Maquetación sitio móvil", 480, 410, 340),
        ("Diseño APP UX", 680, 510, 340),
        ("Diseño APP UI", 680, 510, 340),
        ("Maquetación APP híbrida", 680, 510, 340),
        ("Maquetación APP nativa", 1020, 760, 510),
        ("SEO básico", 120, 90, 50),
        ("SEO avanzado", 240, 180, 120),
        ("Banner publicitario animado", 160, 120, 100),
        ("Mailing / Newsletter", 150, 130, 90),
        ("Presentación digital / CD interactivo", 820, 580, 400),
        ("Presentaciones dinámicas", 150, 100, 70),
        ("Placa animada 2D", 240, 210, 170),
        ("Spot publicitario baja", 550, 460, 390),
        ("Spot publicitario media", 860, 740, 620),
        ("Spot publicitario alta", 1490, 1280, 1070),
        ("Títulos apertura", 240, 210, 170),
        ("Zócalo TV", 150, 120, 90),
        ("Spot radial", 130, 90, 50),
        ("Composición música original", 340, 290, 240),
        ("Locución", 120, 80, 30),
        ("Armado de set estudio", 60, 50, 30),
        ("Sesión fotográfica estudio", 13, 10, 7),
        ("Sesión fotográfica locación", 450, 290, 220),
        ("Escaneo digital", 8, 5, 3),
        ("Filmación", 210, 180, 150),
        ("Supervisión tomas", 40, 30, 20),
        ("Retoque digital", 50, 40, 30),
    ]

    cursor.execute("SELECT COUNT(*) FROM servicios")
    count = cursor.fetchone()["count"]

    if count == 0:
        for servicio in servicios:
            cursor.execute(
                """
                INSERT INTO servicios (nombre, precio_a, precio_b, precio_c)
                VALUES (%s, %s, %s, %s)
                """,
                servicio,
            )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS facturas (
            id SERIAL PRIMARY KEY,
            ncf TEXT,
            rnc TEXT,
            cliente TEXT,
            fecha TEXT,
            subtotal REAL,
            itbis REAL,
            total REAL,
            cotizacion_id INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS factura_items (
            id SERIAL PRIMARY KEY,
            factura_id INTEGER,
            descripcion TEXT,
            cantidad REAL,
            precio REAL,
            total REAL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracion_ncf (
            id SERIAL PRIMARY KEY,
            tipo TEXT,
            desde INTEGER,
            hasta INTEGER,
            actual INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            usuario TEXT,
            password TEXT
        )
        """
    )

    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN foto TEXT")
    except Exception:
        conn.rollback()

    cursor.execute("SELECT * FROM usuarios LIMIT 1")
    if not cursor.fetchone():
        password_hash = generate_password_hash("1234")
        cursor.execute(
            "INSERT INTO usuarios (usuario, password) VALUES (%s, %s)",
            ("admin", password_hash),
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            rnc TEXT,
            telefono TEXT,
            direccion TEXT
        )
        """
    )

    try:
        cursor.execute("ALTER TABLE clientes ADD COLUMN correo TEXT")
    except Exception:
        conn.rollback()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS empresa (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            rnc TEXT,
            telefono TEXT,
            correo TEXT,
            direccion TEXT
        )
        """
    )

    cursor.execute("SELECT * FROM empresa LIMIT 1")
    if not cursor.fetchone():
        cursor.execute(
            """
            INSERT INTO empresa (nombre, rnc, telefono, correo, direccion)
            VALUES (%s, %s, %s, %s, %s)
            """,
            ("Mi Empresa SRL", "", "", "", ""),
        )

    conn.commit()
    conn.close()


@app.route("/")
def index():
    if "usuario" not in session:
        return redirect(url_for("login"))

    buscar = request.args.get("buscar")
    conn = get_db()

    if buscar:
        cotizaciones = conn.execute(
            """
            SELECT * FROM cotizaciones
            WHERE estado != 'Eliminada'
            AND cliente LIKE %s
            ORDER BY id DESC
            """,
            ("%" + buscar + "%",),
        ).fetchall()
    else:
        cotizaciones = conn.execute(
            """
            SELECT * FROM cotizaciones
            WHERE estado != 'Eliminada'
            ORDER BY id DESC
            """
        ).fetchall()

    pendientes = conn.execute(
        "SELECT COUNT(*) FROM cotizaciones WHERE estado='Pendiente'"
    ).fetchone()["count"]

    aprobadas = conn.execute(
        "SELECT COUNT(*) FROM cotizaciones WHERE estado='Aprobada'"
    ).fetchone()["count"]

    facturadas = conn.execute(
        "SELECT COUNT(*) FROM cotizaciones WHERE estado='Facturada'"
    ).fetchone()["count"]

    total_facturado = conn.execute("SELECT SUM(total) AS total FROM facturas").fetchone()["total"]
    if total_facturado is None:
        total_facturado = 0

    conn.close()

    return render_template(
        "index.html",
        cotizaciones=cotizaciones,
        pendientes=pendientes,
        aprobadas=aprobadas,
        facturadas=facturadas,
        total_facturado=total_facturado,
    )


@app.route("/historial")
def historial():
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cotizaciones = conn.execute("SELECT * FROM cotizaciones ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("historial.html", cotizaciones=cotizaciones)


@app.route("/facturas")
def facturas():
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    facturas_list = conn.execute("SELECT * FROM facturas ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("facturas.html", facturas=facturas_list)


@app.route("/nueva", methods=["GET", "POST"])
def nueva_cotizacion():
    conn = get_db()
    cursor = conn.cursor()

    clientes = conn.execute("SELECT nombre FROM clientes").fetchall()
    servicios_db = conn.execute("SELECT nombre, precio_a, precio_b, precio_c FROM servicios").fetchall()

    servicios = []
    for s in servicios_db:
        servicios.append({
            "nombre": s["nombre"],
            "precio_a": s["precio_a"],
            "precio_b": s["precio_b"],
            "precio_c": s["precio_c"],
        })

    if request.method == "POST":
        cliente = request.form["cliente"]
        rnc = request.form["rnc"]
        telefono = request.form["telefono"]

        if not validar_telefono(telefono):
            flash("Teléfono inválido. Ejemplo válido: +1 (829) 123-4567", "danger")
            conn.close()
            return render_template(
                "nueva_cotizacion.html",
                data=request.form.to_dict(),
                clientes=clientes,
                servicios=servicios,
            )

        correo = request.form["correo"]
        subtotal = float(request.form["subtotal"])
        itbis = float(request.form["itbis"])
        total = float(request.form["total"])

        codigo = generar_codigo_cotizacion(conn)
        fecha = datetime.now().strftime("%d/%m/%Y")

        cursor.execute(
            """
            INSERT INTO cotizaciones (codigo, cliente, rnc, telefono, correo, fecha, subtotal, itbis, total, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (codigo, cliente, rnc, telefono, correo, fecha, subtotal, itbis, total, "Pendiente"),
        )

        cotizacion_id = cursor.lastrowid

        descripciones = request.form.getlist("descripcion[]")
        cantidades = request.form.getlist("cantidad[]")
        precios = request.form.getlist("precio[]")
        totales = request.form.getlist("total_linea[]")

        for i in range(len(descripciones)):
            cursor.execute(
                """
                INSERT INTO cotizacion_items (cotizacion_id, descripcion, cantidad, precio, total)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    cotizacion_id,
                    descripciones[i],
                    cantidades[i],
                    precios[i],
                    totales[i],
                ),
            )

        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    conn.close()
    return render_template("nueva_cotizacion.html", clientes=clientes, servicios=servicios)


@app.route("/editar_cotizacion/<int:id>", methods=["GET", "POST"])
def editar_cotizacion(id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        cliente = request.form["cliente"]
        rnc = request.form["rnc"]
        telefono = request.form["telefono"]
        correo = request.form["correo"]

        cursor.execute(
            """
            UPDATE cotizaciones
            SET cliente=%s, rnc=%s, telefono=%s, correo=%s
            WHERE id=%s
            """,
            (cliente, rnc, telefono, correo, id),
        )

        conn.commit()
        conn.close()
        return redirect("/")

    cursor.execute("SELECT * FROM cotizaciones WHERE id=%s", (id,))
    cotizacion = cursor.fetchone()
    conn.close()
    return render_template("editar_cotizacion.html", cotizacion=cotizacion)


@app.route("/aprobar/<int:id>")
def aprobar(id):
    conn = get_db()
    conn.execute("UPDATE cotizaciones SET estado='Aprobada' WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/facturar/<int:id>", methods=["GET", "POST"])
def facturar(id):
    conn = get_db()

    cotizacion = conn.execute("SELECT * FROM cotizaciones WHERE id=%s", (id,)).fetchone()
    items = conn.execute("SELECT * FROM cotizacion_items WHERE cotizacion_id=%s", (id,)).fetchall()
    config = conn.execute("SELECT * FROM configuracion_ncf LIMIT 1").fetchone()

    if config is None:
        conn.close()
        return "Debes configurar el NCF primero"

    if request.method == "POST":
        rnc = request.form["rnc"]

        siguiente = config["actual"] + 1
        if siguiente > config["hasta"]:
            conn.close()
            return "Rango NCF agotado"

        numero_formateado = str(siguiente).zfill(8)
        ncf = config["tipo"] + numero_formateado
        fecha = datetime.now().strftime("%d/%m/%Y")

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO facturas (ncf, rnc, cliente, fecha, subtotal, itbis, total, cotizacion_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                ncf,
                rnc,
                cotizacion["cliente"],
                fecha,
                cotizacion["subtotal"],
                cotizacion["itbis"],
                cotizacion["total"],
                id,
            ),
        )

        factura_id = cursor.lastrowid

        for item in items:
            cursor.execute(
                """
                INSERT INTO factura_items (factura_id, descripcion, cantidad, precio, total)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    factura_id,
                    item["descripcion"],
                    item["cantidad"],
                    item["precio"],
                    item["total"],
                ),
            )

        cursor.execute(
            "UPDATE configuracion_ncf SET actual=%s WHERE id=%s",
            (siguiente, config["id"]),
        )
        cursor.execute(
            "UPDATE cotizaciones SET estado='Facturada' WHERE id=%s",
            (id,),
        )

        conn.commit()
        conn.close()
        return redirect(url_for("factura_pdf", id=factura_id))

    conn.close()
    return render_template("facturar.html", cotizacion=cotizacion, items=items)


@app.route("/configurar_ncf", methods=["GET", "POST"])
def configurar_ncf():
    conn = get_db()

    if request.method == "POST":
        tipo = request.form["tipo"]
        desde = int(request.form["desde"])
        hasta = int(request.form["hasta"])

        conn.execute("DELETE FROM configuracion_ncf")
        conn.execute(
            """
            INSERT INTO configuracion_ncf (tipo, desde, hasta, actual)
            VALUES (%s, %s, %s, %s)
            """,
            (tipo, desde, hasta, desde - 1),
        )

        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    config = conn.execute("SELECT * FROM configuracion_ncf LIMIT 1").fetchone()
    conn.close()
    return render_template("configurar_ncf.html", config=config)


@app.route("/factura_pdf/<int:id>")
def factura_pdf(id):
    conn = get_db()

    factura = conn.execute("SELECT * FROM facturas WHERE id=%s", (id,)).fetchone()
    if not factura:
        conn.close()
        return "Factura no encontrada"

    items = conn.execute("SELECT * FROM factura_items WHERE factura_id=%s", (factura["id"],)).fetchall()
    empresa = conn.execute("SELECT * FROM empresa LIMIT 1").fetchone()
    conn.close()

    buffer = io.BytesIO()
    page_width, page_height = letter
    left_margin = 36
    right_margin = 36
    top_margin = 120
    bottom_margin = 60

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "normal_small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
    )
    bold = ParagraphStyle(
        "bold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
    )

    right_price = ParagraphStyle("right_price", parent=normal, alignment=2)
    right_total = ParagraphStyle("right_total", parent=normal, alignment=2)
    right_money = ParagraphStyle("right_money", parent=normal, alignment=2)
    small = ParagraphStyle(
        "small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
    )

    logo_path = os.path.join(app.root_path, "static", "logo.png")

    def draw_header_footer(canvas, doc):
        canvas.saveState()

        if os.path.exists(logo_path):
            try:
                canvas.drawImage(
                    logo_path,
                    doc.leftMargin,
                    page_height - 78,
                    width=200,
                    height=80,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

        canvas.setFont("Helvetica", 9)
        y = page_height - 28
        canvas.drawRightString(page_width - doc.rightMargin, y, f"Fecha: {factura['fecha']}")
        y -= 12
        canvas.drawRightString(page_width - doc.rightMargin, y, "Santo Domingo D.N.")
        y -= 12
        canvas.drawRightString(page_width - doc.rightMargin, y, empresa["telefono"] or "")
        y -= 12
        canvas.drawRightString(page_width - doc.rightMargin, y, empresa["correo"] or "")
        y -= 12
        canvas.drawRightString(page_width - doc.rightMargin, y, f"RNC: {empresa['rnc']}")

        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawCentredString(page_width / 2, page_height - 104, "FACTURA")
        canvas.line(doc.leftMargin, page_height - 112, page_width - doc.rightMargin, page_height - 112)
        canvas.restoreState()

    story = []

    cliente_data = [
        [
            Paragraph("<b>Cliente:</b> " + str(factura["cliente"]), normal),
            Paragraph("<b>NCF:</b> " + str(factura["ncf"]), normal),
        ],
        [
            Paragraph("<b>RNC:</b> " + str(factura["rnc"] or "-"), normal),
            Paragraph("<b>Fecha:</b> " + str(factura["fecha"]), normal),
        ],
        [
            Paragraph("<b>Dirección:</b> -", normal),
            Paragraph("<b>Atendido por:</b> Radhames Del Valle", normal),
        ],
    ]

    cliente_table = Table(cliente_data, colWidths=[260, 250])
    cliente_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    story.append(Spacer(1, 20))
    story.append(cliente_table)
    story.append(Spacer(1, 14))

    items_data = [[
        Paragraph("<b>Cant.</b>", bold),
        Paragraph("<b>Descripción</b>", bold),
        Paragraph("<b align='right'>Precio</b>", bold),
        Paragraph("<b align='right'>Valor</b>", bold),
    ]]

    for item in items:
        items_data.append(
            [
                Paragraph(str(item["cantidad"]), normal),
                Paragraph(str(item["descripcion"]), normal),
                Paragraph(f"{float(item['precio']):,.2f}", right_price),
                Paragraph(f"{float(item['total']):,.2f}", right_total),
            ]
        )

    items_table = Table(items_data, colWidths=[50, 290, 95, 95], repeatRows=1)
    items_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9d9d9")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (2, 1), (3, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(items_table)
    story.append(Spacer(1, 16))

    totals_data = [
        [Paragraph("Sub-total:", normal), Paragraph(money(factura["subtotal"]), right_money)],
        [Paragraph("ITBIS:", normal), Paragraph(money(factura["itbis"]), right_money)],
        [Paragraph("<b>Total:</b>", bold), Paragraph(f"<b>{money(factura['total'])}</b>", ParagraphStyle("r3", parent=bold, alignment=2))],
    ]

    totals_table = Table(totals_data, colWidths=[100, 110], hAlign="RIGHT")
    story.append(totals_table)
    story.append(Spacer(1, 40))

    firma_table = Table([[""], ["Firma y sello"]], colWidths=[200], hAlign="CENTER")
    firma_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (0, 0), 1.2, colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )

    story.append(firma_table)

    fecha = datetime.now().strftime("%d-%m-%Y")
    nombre_cliente = factura["cliente"] or "Cliente"
    nombre_limpio = re.sub(r"[^A-Za-z0-9]", "_", nombre_cliente)
    nombre_archivo = f"FACT-{nombre_limpio}-{fecha}.pdf"

    doc.build(story, onFirstPage=draw_header_footer)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/pdf",
    )


@app.route("/eliminar_factura/<int:id>", methods=["POST"])
def eliminar_factura(id):
    conn = get_db()

    factura = conn.execute("SELECT * FROM facturas WHERE id=%s", (id,)).fetchone()
    if factura:
        conn.execute(
            "UPDATE cotizaciones SET estado='Aprobada' WHERE id=%s",
            (factura["cotizacion_id"],),
        )
        conn.execute("DELETE FROM factura_items WHERE factura_id=%s", (id,))
        conn.execute("DELETE FROM facturas WHERE id=%s", (id,))

    conn.commit()
    conn.close()
    return redirect(url_for("facturas"))


@app.route("/reset_facturas")
def reset_facturas():
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("DELETE FROM factura_items")
    conn.execute("DELETE FROM facturas")
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.route("/cotizacion_pdf/<int:id>")
def cotizacion_pdf(id):
    conn = get_db()

    cotizacion = conn.execute("SELECT * FROM cotizaciones WHERE id=%s", (id,)).fetchone()
    items = conn.execute("SELECT * FROM cotizacion_items WHERE cotizacion_id=%s", (id,)).fetchall()
    empresa = conn.execute("SELECT * FROM empresa LIMIT 1").fetchone()
    conn.close()

    if not cotizacion:
        return "Cotización no encontrada"

    buffer = io.BytesIO()
    page_width, page_height = letter
    left_margin = 36
    right_margin = 36
    top_margin = 120
    bottom_margin = 60

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "normal_small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
    )
    small = ParagraphStyle(
        "small",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
    )
    bold = ParagraphStyle(
        "bold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
    )

    logo_path = os.path.join(app.root_path, "static", "logo.png")

    def draw_header_footer(canvas, doc):
        canvas.saveState()

        if os.path.exists(logo_path):
            try:
                canvas.saveState()
                try:
                    canvas.setFillAlpha(0.06)
                except Exception:
                    pass
                canvas.drawImage(
                    logo_path,
                    x=(page_width - 320) / 2,
                    y=220,
                    width=420,
                    height=520,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                try:
                    canvas.setFillAlpha(1)
                except Exception:
                    pass
                canvas.restoreState()
            except Exception:
                pass

        if os.path.exists(logo_path):
            try:
                canvas.drawImage(
                    logo_path,
                    doc.leftMargin,
                    page_height - 78,
                    width=200,
                    height=80,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

        canvas.setFont("Helvetica", 9)
        y = page_height - 28
        canvas.drawRightString(page_width - doc.rightMargin, y, f"Fecha: {cotizacion['fecha']}")
        y -= 12
        canvas.drawRightString(page_width - doc.rightMargin, y, "Santo Domingo D.N.")
        y -= 12
        canvas.drawRightString(page_width - doc.rightMargin, y, "Tel: 829-874-1003")
        y -= 12
        canvas.drawRightString(page_width - doc.rightMargin, y, "Email: delvallepublicity@gmail.com")
        y -= 12
        canvas.drawRightString(page_width - doc.rightMargin, y, "RNC: 132357604")

        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawCentredString(page_width / 2, page_height - 104, "COTIZACIÓN")
        canvas.line(doc.leftMargin, page_height - 112, page_width - doc.rightMargin, page_height - 112)
        canvas.restoreState()

    story = []

    cliente_data = [
        [
            Paragraph("<b>Cliente:</b> " + str(cotizacion["cliente"]), normal),
            Paragraph("<b>No:</b> " + str(cotizacion["codigo"]), normal),
        ],
        [
            Paragraph("<b>RNC:</b> " + str(cotizacion["rnc"] or "-"), normal),
            Paragraph("<b>Fecha:</b> " + str(cotizacion["fecha"]), normal),
        ],
        [
            Paragraph("<b>Dirección:</b> " + str("-"), normal),
            Paragraph("<b>Atendido por:</b> Radhames Del Valle", normal),
        ],
    ]

    cliente_table = Table(cliente_data, colWidths=[260, 250])
    cliente_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    story.append(Spacer(1, 20))
    story.append(cliente_table)
    story.append(Spacer(1, 14))

    items_data = [[
        Paragraph("<b>Cant.</b>", bold),
        Paragraph("<b>Descripción</b>", bold),
        Paragraph("<b align='right'>Precio</b>", bold),
        Paragraph("<b align='right'>Valor</b>", bold),
    ]]

    for item in items:
        items_data.append(
            [
                Paragraph(str(item["cantidad"]), normal),
                Paragraph(str(item["descripcion"]), normal),
                Paragraph(f"{float(item['precio']):,.2f}", ParagraphStyle("right_price", parent=normal, alignment=2)),
                Paragraph(f"{float(item['total']):,.2f}", ParagraphStyle("right_total", parent=normal, alignment=2)),
            ]
        )

    items_table = Table(items_data, colWidths=[50, 290, 95, 95], repeatRows=1)
    items_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9d9d9")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (2, 1), (3, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(items_table)
    story.append(Spacer(1, 16))

    totals_data = [
        [Paragraph("Sub-total:", normal), Paragraph(money(cotizacion["subtotal"]), ParagraphStyle("r1", parent=normal, alignment=2))],
        [Paragraph("ITBIS:", normal), Paragraph(money(cotizacion["itbis"]), ParagraphStyle("r2", parent=normal, alignment=2))],
        [Paragraph("<b>Total:</b>", bold), Paragraph(f"<b>{money(cotizacion['total'])}</b>", ParagraphStyle("r3", parent=bold, alignment=2))],
    ]

    totals_table = Table(totals_data, colWidths=[100, 110], hAlign="RIGHT")
    totals_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 2), (-1, 2), 1.2, colors.black),
                ("TOPPADDING", (0, 2), (-1, 2), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#f2f2f2")),
            ]
        )
    )

    story.append(totals_table)
    story.append(Spacer(1, 26))
    story.append(Spacer(1, 80))

    condiciones = Paragraph(
        "*Válida por 15 días.<br/>"
        "*50% anticipo / 50% contra entrega.<br/>"
        "*Tiempo de entrega: 2 semanas.",
        ParagraphStyle("condiciones", parent=small, alignment=0),
    )

    story.append(Spacer(1, 20))
    story.append(condiciones)
    story.append(Spacer(1, 30))

    firma_table = Table([[""], ["Firma y sello"]], colWidths=[200], hAlign="CENTER")
    firma_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (0, 0), 1.2, colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(firma_table)

    fecha = datetime.now().strftime("%d-%m-%Y")
    nombre_cliente = cotizacion["cliente"] or "Cliente"
    nombre_limpio = re.sub(r"[^A-Za-z0-9]", "_", nombre_cliente)
    nombre_archivo = f"COT-{nombre_limpio}-{fecha}.pdf"

    doc.title = nombre_archivo
    doc.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/pdf",
    )


@app.route("/detalle/<int:id>")
def detalle(id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM cotizaciones WHERE id=%s", (id,))
    cotizacion = cursor.fetchone()

    cursor.execute("SELECT * FROM cotizacion_items WHERE cotizacion_id=%s", (id,))
    servicios = cursor.fetchall()

    conn.close()

    return render_template("detalle.html", cotizacion=cotizacion, servicios=servicios)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]
        recordar = request.form.get("recordar")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE usuario=%s",
            (usuario,),
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["usuario"] = usuario
            if recordar:
                session.permanent = True
            return redirect(url_for("index"))
        else:
            return "Usuario o contraseña incorrectos"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        nuevo_usuario = request.form["usuario"]
        nueva_password = request.form["password"]
        conn.execute(
            """
            UPDATE usuarios
            SET usuario=%s, password=%s
            WHERE id=1
            """,
            (nuevo_usuario, generate_password_hash(nueva_password)),
        )
        conn.commit()

    user = conn.execute("SELECT * FROM usuarios LIMIT 1").fetchone()
    conn.close()

    return render_template("usuarios.html", user=user)


@app.route("/clientes", methods=["GET", "POST"])
def clientes():
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":
        nombre = request.form["nombre"]
        rnc = request.form["rnc"]
        telefono = request.form["telefono"]
        direccion = request.form["direccion"]

        conn.execute(
            """
            INSERT INTO clientes (nombre, rnc, telefono, direccion)
            VALUES (%s, %s, %s, %s)
            """,
            (nombre, rnc, telefono, direccion),
        )
        conn.commit()

    buscar = request.args.get("buscar")

    if buscar:
        clientes = conn.execute(
            """
            SELECT * FROM clientes
            WHERE nombre LIKE %s
            ORDER BY id DESC
            """,
            ("%" + buscar + "%",),
        ).fetchall()
    else:
        clientes = conn.execute("SELECT * FROM clientes ORDER BY id DESC").fetchall()

    conn.close()
    return render_template("clientes.html", clientes=clientes)


@app.route("/buscar_clientes")
def buscar_clientes():
    termino = request.args.get("q", "")
    conn = get_db()

    clientes = conn.execute(
        """
        SELECT nombre FROM clientes
        WHERE nombre LIKE %s
        LIMIT 10
        """,
        ("%" + termino + "%",),
    ).fetchall()

    conn.close()
    resultados = [cliente["nombre"] for cliente in clientes]
    return {"clientes": resultados}


@app.route("/eliminar_cliente/<int:id>", methods=["POST"])
def eliminar_cliente(id):
    conn = get_db()
    conn.execute("DELETE FROM clientes WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("clientes"))


@app.route("/editar_cliente/<int:id>", methods=["GET", "POST"])
def editar_cliente(id):
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    cliente = conn.execute("SELECT * FROM clientes WHERE id=%s", (id,)).fetchone()

    if request.method == "POST":
        nombre = request.form["nombre"]
        rnc = request.form["rnc"]
        telefono = request.form["telefono"]
        correo = request.form["correo"]
        direccion = request.form["direccion"]

        try:
            conn.execute("ALTER TABLE clientes ADD COLUMN correo TEXT")
        except Exception:
            pass

        conn.execute(
            """
            UPDATE clientes
            SET nombre=%s, rnc=%s, telefono=%s, correo=%s, direccion=%s
            WHERE id=%s
            """,
            (nombre, rnc, telefono, correo, direccion, id),
        )

        conn.commit()
        conn.close()
        return redirect(url_for("clientes"))

    conn.close()
    return render_template("editar_cliente.html", cliente=cliente)


@app.route("/arreglar_db")
def arreglar_db():
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE cotizaciones ADD COLUMN rnc TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE cotizaciones ADD COLUMN telefono TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE cotizaciones ADD COLUMN correo TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()
    return "Base de datos actualizada correctamente"


@app.route("/eliminar_cotizacion/<int:id>", methods=["POST"])
def eliminar_cotizacion(id):
    conn = get_db()
    conn.execute("DELETE FROM cotizacion_items WHERE cotizacion_id=%s", (id,))
    conn.execute("DELETE FROM cotizaciones WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))


@app.context_processor
def inject_user():
    return dict(usuario=session.get("usuario"))


@app.route("/perfil", methods=["GET", "POST"])
def perfil():
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios LIMIT 1").fetchone()
    empresa = conn.execute("SELECT * FROM empresa LIMIT 1").fetchone()

    if request.method == "POST":
        archivo = request.files.get("foto")

        if archivo and archivo.filename != "":
            from werkzeug.utils import secure_filename

            nombre = secure_filename(archivo.filename)
            os.makedirs("static/uploads", exist_ok=True)
            ruta = os.path.join("static/uploads", nombre)
            archivo.save(ruta)

            conn.execute(
                """
                UPDATE usuarios
                SET foto=%s
                WHERE id=%s
                """,
                (nombre, user["id"]),
            )

        usuario = request.form["usuario"]
        password = request.form["password"]
        confirmar = request.form["confirmar"]

        nombre_empresa = request.form["empresa"]
        rnc = request.form["rnc"]
        telefono = request.form["telefono"]
        correo = request.form["correo"]
        direccion = request.form["direccion"]

        if password:
            if password != confirmar:
                conn.close()
                return "Las contraseñas no coinciden"

            if len(password) < 4:
                conn.close()
                return "La contraseña es muy corta"

            password_hash = generate_password_hash(password)
            conn.execute(
                """
                UPDATE usuarios
                SET usuario=%s, password=%s
                WHERE id=%s
                """,
                (usuario, password_hash, user["id"]),
            )
        else:
            conn.execute(
                """
                UPDATE usuarios
                SET usuario=%s
                WHERE id=%s
                """,
                (usuario, user["id"]),
            )

        conn.execute(
            """
            UPDATE empresa
            SET nombre=%s, rnc=%s, telefono=%s, correo=%s, direccion=%s
            WHERE id=%s
            """,
            (nombre_empresa, rnc, telefono, correo, direccion, empresa["id"]),
        )

        conn.commit()
        conn.close()
        session["usuario"] = usuario
        return redirect(url_for("index"))

    conn.close()
    return render_template("perfil.html", user=user, empresa=empresa)


if __name__ == "__main__":
    init_db()
    try:
        db.arreglar_tabla()
    except Exception as e:
        print("Error arreglando tabla:", e)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)