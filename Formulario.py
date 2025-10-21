from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "mi_clave_segura"

# =====================================================
# CARGA DE DATOS DEL CATÁLOGO
# =====================================================
# Se carga la hoja WEDDING BANDS
df = pd.read_excel("WEDDING BANDS.xlsx", sheet_name="WEDDING BANDS")

# Asegurar columnas necesarias
for col in ["D", "AF", "AG", "F"]:
    if col not in df.columns:
        raise ValueError(f"Falta la columna {col} en el archivo Excel.")

# =====================================================
# FUNCIÓN PARA CALCULAR PRECIO
# =====================================================
def calcular_precio(base, kilates, ancho, talla):
    """
    Calcula el precio dinámico con factores ajustables.
    """
    factor_kilates = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}
    try:
        factor_ancho = float(ancho.replace("mm", "").strip()) / 2
        factor_talla = 1 + (int(talla) - 6) * 0.02
    except:
        factor_ancho = 1
        factor_talla = 1
    return round(base * factor_kilates.get(str(kilates), 1) * factor_ancho * factor_talla, 2)

# =====================================================
# RUTA PRINCIPAL - FORMULARIO DE COTIZACIÓN
# =====================================================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Guardar los datos en la sesión
        campos = [
            "cliente_nombre", "cliente_telefono",
            "kilates_dama", "kilates_caballero",
            "ancho_dama", "ancho_caballero",
            "talla_dama", "talla_caballero"
        ]
        for campo in campos:
            session[campo] = request.form.get(campo, "")

        # Acción del formulario
        if request.form.get("accion") == "catalogo":
            return redirect(url_for("catalogo"))

    # Recuperar datos previos (o valores por defecto)
    datos = {
        "cliente_nombre": session.get("cliente_nombre", ""),
        "cliente_telefono": session.get("cliente_telefono", ""),
        "kilates_dama": session.get("kilates_dama", "14"),
        "kilates_caballero": session.get("kilates_caballero", "14"),
        "ancho_dama": session.get("ancho_dama", "2 mm"),
        "ancho_caballero": session.get("ancho_caballero", "2 mm"),
        "talla_dama": session.get("talla_dama", "6"),
        "talla_caballero": session.get("talla_caballero", "8"),
        "modelo_dama": session.get("modelo_dama", "No seleccionado"),
        "modelo_caballero": session.get("modelo_caballero", "No seleccionado"),
    }

    # Simular precios base
    base_dama, base_caballero = 100, 120
    precio_dama = calcular_precio(base_dama, datos["kilates_dama"], datos["ancho_dama"], datos["talla_dama"])
    precio_caballero = calcular_precio(base_caballero, datos["kilates_caballero"], datos["ancho_caballero"], datos["talla_caballero"])

    return render_template("index.html", datos=datos, precio_dama=precio_dama, precio_caballero=precio_caballero)

# =====================================================
# RUTA DEL CATÁLOGO
# =====================================================
@app.route("/catalogo", methods=["GET", "POST"])
def catalogo():
    """
    Muestra el catálogo de anillos (con imágenes desde Excel).
    Permite seleccionar modelo Dama y Caballero.
    """
    if request.method == "POST":
        # Registrar las selecciones
        session["modelo_dama"] = request.form.get("modelo_dama", session.get("modelo_dama", ""))
        session["modelo_caballero"] = request.form.get("modelo_caballero", session.get("modelo_caballero", ""))
        return redirect(url_for("index"))

    # Generar lista de modelos únicos con imagen y enlace
    modelos = []
    for _, row in df.iterrows():
        modelo = str(row["D"])
        ruta_img = str(row["AF"])
        enlace = str(row["AG"])
        metal = str(row["F"])

        if os.path.exists(ruta_img):
            modelos.append({
                "nombre": modelo,
                "imagen": ruta_img.replace("\\", "/"),
                "enlace": enlace,
                "metal": metal
            })

    return render_template("catalogo.html", modelos=modelos)

# =====================================================
# INICIO DEL SERVIDOR
# =====================================================
if __name__ == "__main__":
    app.run(debug=True)


<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Formulario Cotización</title>
  <script>
    function recalcular() {
      document.getElementById('formMain').submit();
    }
  </script>
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100 p-6">
  <div class="max-w-4xl mx-auto bg-white rounded-xl shadow-lg p-6">
    <h1 class="text-2xl font-bold mb-4 text-center">Formulario de Cotización</h1>

    <form id="formMain" method="POST" action="/" class="space-y-4">

      <!-- DATOS DEL CLIENTE -->
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="font-semibold">Nombre del Cliente:</label>
          <input type="text" name="cliente_nombre" value="{{ datos.cliente_nombre }}" class="border p-2 w-full rounded">
        </div>
        <div>
          <label class="font-semibold">Teléfono:</label>
          <input type="text" name="cliente_telefono" value="{{ datos.cliente_telefono }}" class="border p-2 w-full rounded">
        </div>
      </div>

      <!-- MODELOS SELECCIONADOS -->
      <div class="grid grid-cols-2 gap-6 mt-4">
        <div>
          <p class="font-semibold text-indigo-700">Modelo Dama:</p>
          <p>{{ datos.modelo_dama }}</p>
        </div>
        <div>
          <p class="font-semibold text-indigo-700">Modelo Caballero:</p>
          <p>{{ datos.modelo_caballero }}</p>
        </div>
      </div>

      <!-- CONFIGURACIÓN DE ANILLOS -->
      <div class="grid grid-cols-2 gap-6 mt-4">
        <div>
          <h2 class="text-lg font-bold mb-2 text-indigo-600">Dama</h2>
          <label>Kilates:</label>
          <select name="kilates_dama" onchange="recalcular()" class="border p-2 rounded w-full">
            {% for k in ['10','14','18','22'] %}
              <option value="{{k}}" {% if k==datos.kilates_dama %}selected{% endif %}>{{k}}K</option>
            {% endfor %}
          </select>

          <label>Ancho:</label>
          <select name="ancho_dama" onchange="recalcular()" class="border p-2 rounded w-full">
            {% for a in ['2 mm','3 mm','4 mm'] %}
              <option value="{{a}}" {% if a==datos.ancho_dama %}selected{% endif %}>{{a}}</option>
            {% endfor %}
          </select>

          <label>Talla:</label>
          <select name="talla_dama" onchange="recalcular()" class="border p-2 rounded w-full">
            {% for t in range(4,10) %}
              <option value="{{t}}" {% if t|string==datos.talla_dama %}selected{% endif %}>{{t}}</option>
            {% endfor %}
          </select>

          <p class="mt-2 font-bold text-green-700">Precio: ${{ precio_dama }}</p>
        </div>

        <div>
          <h2 class="text-lg font-bold mb-2 text-indigo-600">Caballero</h2>
          <label>Kilates:</label>
          <select name="kilates_caballero" onchange="recalcular()" class="border p-2 rounded w-full">
            {% for k in ['10','14','18','22'] %}
              <option value="{{k}}" {% if k==datos.kilates_caballero %}selected{% endif %}>{{k}}K</option>
            {% endfor %}
          </select>

          <label>Ancho:</label>
          <select name="ancho_caballero" onchange="recalcular()" class="border p-2 rounded w-full">
            {% for a in ['2 mm','3 mm','4 mm'] %}
              <option value="{{a}}" {% if a==datos.ancho_caballero %}selected{% endif %}>{{a}}</option>
            {% endfor %}
          </select>

          <label>Talla:</label>
          <select name="talla_caballero" onchange="recalcular()" class="border p-2 rounded w-full">
            {% for t in range(6,13) %}
              <option value="{{t}}" {% if t|string==datos.talla_caballero %}selected{% endif %}>{{t}}</option>
            {% endfor %}
          </select>

          <p class="mt-2 font-bold text-green-700">Precio: ${{ precio_caballero }}</p>
        </div>
      </div>

      <!-- BOTONES -->
      <div class="flex justify-between mt-6">
        <button type="submit" name="accion" value="catalogo"
                class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition">
          Ir a Catálogo
        </button>

        <button type="submit"
                class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition">
          Guardar Cotización
        </button>
      </div>

    </form>
  </div>
</body>
</html>


<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Catálogo de Anillos</title>
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100 p-6">
  <div class="max-w-6xl mx-auto bg-white rounded-xl shadow-lg p-6">
    <h1 class="text-2xl font-bold mb-4 text-center text-indigo-700">Catálogo de Anillos</h1>

    <form method="POST" class="grid grid-cols-3 gap-6">
      {% for item in modelos %}
        <div class="border rounded-lg shadow p-3 text-center hover:shadow-lg transition">
          <img src="{{ item.imagen }}" alt="{{ item.nombre }}" class="w-full h-48 object-contain mx-auto mb-2">
          <p class="font-bold text-gray-800">{{ item.nombre }}</p>
          <p class="text-sm text-gray-500">{{ item.metal }}</p>
          <div class="flex justify-center mt-2 gap-2">
            <button type="submit" name="modelo_dama" value="{{ item.nombre }}"
                    class="px-3 py-1 bg-pink-500 text-white text-sm rounded hover:bg-pink-600">Seleccionar Dama</button>
            <button type="submit" name="modelo_caballero" value="{{ item.nombre }}"
                    class="px-3 py-1 bg-blue-500 text-white text-sm rounded hover:bg-blue-600">Seleccionar Caballero</button>
          </div>
          {% if item.enlace and item.enlace != 'nan' %}
            <a href="{{ item.enlace }}" target="_blank" class="text-indigo-600 text-xs hover:underline mt-2 block">Ver en línea</a>
          {% endif %}
        </div>
      {% endfor %}
    </form>

    <div class="text-center mt-6">
      <a href="{{ url_for('index') }}" class="text-indigo-700 font-semibold hover:underline">← Regresar al formulario</a>
    </div>
  </div>
</body>
</html>
