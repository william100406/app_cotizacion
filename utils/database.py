import sqlite3

def conectar():
    conn = sqlite3.connect("sistema.db")
    conn.row_factory = sqlite3.Row
    return conn


def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cotizaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT,
        subtotal REAL,
        itbis REAL,
        total REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cotizacion_id INTEGER,
        descripcion TEXT,
        cantidad REAL,
        precio REAL,
        total REAL
    )
    """)

    conn.commit()
    conn.close()


def guardar_cotizacion(cliente, subtotal, itbis, total):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO cotizaciones (cliente, subtotal, itbis, total)
    VALUES (?, ?, ?, ?)
    """, (cliente, subtotal, itbis, total))

    cotizacion_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return cotizacion_id


def guardar_producto(cotizacion_id, descripcion, cantidad, precio, total):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO productos (cotizacion_id, descripcion, cantidad, precio, total)
    VALUES (?, ?, ?, ?, ?)
    """, (cotizacion_id, descripcion, cantidad, precio, total))

    conn.commit()
    conn.close()


def obtener_cotizaciones():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM cotizaciones ORDER BY id DESC")

    datos = cursor.fetchall()

    conn.close()

    return datos


def eliminar_cotizacion_db(cotizacion_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE cotizaciones SET estado='Eliminada' WHERE id=?",
        (cotizacion_id,)
    )

    conn.commit()
    conn.close()

    cursor.execute("""
CREATE TABLE IF NOT EXISTS cotizaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT,
    subtotal REAL,
    itbis REAL,
    total REAL,
    estado TEXT
)
""")
    
def arreglar_tabla():
    conn = conectar()
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE cotizaciones ADD COLUMN estado TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()