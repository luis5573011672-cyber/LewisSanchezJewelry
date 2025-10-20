import requests
import os
import pandas as pd
from flask import Flask, jsonify, request, render_template_string, session, redirect, url_for

# --- CONFIGURACIÓN GLOBAL ---
app = Flask(__name__)
# ¡IMPORTANTE! Esta clave secreta es OBLIGATORIA para usar `session`. 
# En producción (Render), se recomienda usar una variable de entorno.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "una_clave_secreta_fuerte_aqui_para_testing")

# Se asume que el archivo Excel debe estar en el mismo directorio para Render.
EXCEL_PATH = "Formulario Catalogo.xlsm" 
FACTOR_KILATES = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}

# Precio de respaldo (fallback) en caso de que la API de Oro falle o exceda límites.
DEFAULT_GOLD_PRICE = 2000.00 # USD por Onza

# --------------------- FUNCIONES DE UTILIDAD ---------------------

def obtener_precio_oro():
    """
    Obtiene el precio actual del oro (XAU/USD) por onza desde la API.
    Retorna (precio, estado) donde estado es "live" o "fallback".
    """
    # CLAVE API PROPORCIONADA POR EL USUARIO (la que está dando 403 Forbidden):
    API_KEY = "goldapi-4g9e8p719mgvhodho-io" 
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": API_KEY, "Content-Type": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        
        # Si hay un error 4xx o 5xx, se lanza una excepción aquí.
        # Esto captura tu error 403 Forbidden.
        response.raise_for_status() 
        
        data = response.json()
        price = data.get("price")
        
        if price is not None:
            return price, "live"
        
        print("ADVERTENCIA: API respondió OK (200), pero faltaba el precio en el cuerpo de la respuesta. Usando fallback.")
        return DEFAULT_GOLD_PRICE, "fallback"

    except requests.exceptions.HTTPError as e:
        # Manejo específico para 403, 429, etc.
        error_code = e.response.status_code
        error_text = e.response.text
        
        print(f"ERROR HTTP ({error_code}) al obtener precio del oro: {e}.")
        print(f"Respuesta de la API para depuración: {error_text}")
        print(f"Usando precio de respaldo: ${DEFAULT_GOLD_PRICE:,.2f}")
        return DEFAULT_GOLD_PRICE, "fallback"
        
    except requests.RequestException as e:
        # Captura errores de conexión o timeout
        print(f"Error de conexión al obtener precio del oro: {e}. Usando precio de respaldo: ${DEFAULT_GOLD_PRICE:,.2f}")
        return DEFAULT_GOLD_PRICE, "fallback"
    except Exception as e:
        print(f"Error inesperado en obtener_precio_oro: {e}. Usando precio de respaldo: ${DEFAULT_GOLD_PRICE:,.2f}")
        return DEFAULT_GOLD_PRICE, "fallback"


def calcular_valor_gramo(valor_onza, pureza_factor, peso_gramos):
    """Calcula el valor del oro y el monto total de la joya."""
    if valor_onza is None or valor_onza == 0 or peso_gramos is None or peso_gramos == 0:
        return 0, 0
    
    # Conversión: Onza a Gramo (1 onza = 31.1035 gramos)
    valor_gramo = (valor_onza / 31.1035) * pureza_factor
    monto_total = valor_gramo * peso_gramos
    return valor_gramo, monto_total

def cargar_datos():
    """Carga los DataFrames desde el archivo Excel."""
    try:
        # Se asume que el archivo 'Formulario Catalogo.xlsm' está en la raíz del proyecto.
        df = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=1)
        df_size = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl")
        
        # Limpieza de encabezados de columnas
        df.columns = df.columns.str.strip()
        df_size.columns = df_size.columns.str.strip()
        
        # Inicializa columnas clave si no existen para evitar errores (aunque deberían existir)
        for col in ["NAME", "METAL", "CARAT", "PESO"]:
            if col not in df.columns:
                 # Si faltan columnas, lo imprimimos y la inicializamos como NaN
                print(f"ADVERTENCIA: Columna '{col}' falta en WEDDING BANDS.")
        
        return df, df_size
    except FileNotFoundError:
        print(f"ERROR: Archivo '{EXCEL_PATH}' no encontrado. Asegúrate de que esté en la raíz del proyecto.")
        return pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        print(f"Error al leer el archivo Excel: {e}")
        return pd.DataFrame(), pd.DataFrame()


# --------------------- RUTAS FLASK ---------------------

@app.route("/", methods=["GET", "POST"])
def formulario():
    """
    Ruta principal del formulario de presupuesto. 
    Maneja la lógica de cálculo y la presentación del formulario.
    """
    df, _ = cargar_datos()
    # Ahora, obtener_precio_oro devuelve el precio y el estado
    precio_onza, status = obtener_precio_oro()

    # Manejar el idioma desde la sesión
    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    session["idioma"] = idioma # Asegura que la sesión se actualice

    t = {
        "titulo": "Formulario de Presupuesto u Orden" if es else "Estimate or Work Order Form",
        "cliente": "Nombre del cliente" if es else "Client name",
        "telefono": "Teléfono" if es else "Phone",
        "correo": "Correo electrónico" if es else "Email",
        "direccion": "Dirección" if es else "Address",
        "modelo_dama": "Modelo dama" if es else "Lady model",
        "modelo_cab": "Modelo caballero" if es else "Gentleman model",
        "catalogo_btn": "Abrir Catálogo" if es else "Open Catalog",
        "guardar": "Guardar" if es else "Save",
        "monto": "Monto total del presupuesto" if es else "Total estimate amount",
    }
    
    # Inicializar/Obtener datos de la sesión (selecciones del catálogo)
    cliente = request.form.get("cliente", "")
    telefono = request.form.get("telefono", "")
    correo = request.form.get("correo", "")
    direccion = request.form.get("direccion", "")
    
    # Obtener modelos de la sesión (vienen de /catalogo)
    modelo_dama = session.get("modelo_dama", "")
    metal_dama = session.get("metal_dama", "")
    
    modelo_cab = session.get("modelo_cab", "")
    metal_cab = session.get("metal_cab", "")
    
    # Si el método es POST (envío del formulario), guardamos los datos del cliente
    if request.method == "POST":
        # Lógica para guardar los datos del cliente, si es necesario.
        # Por ahora, solo actualiza las variables para la recarga del formulario.
        idioma = request.form.get("idioma", "Español")
        session["idioma"] = idioma
        return redirect(url_for("formulario")) # Redirigir para limpiar el POST y actualizar idioma/cálculos

    monto_total = 0.0

    # --- Cálculo dama ---
    if modelo_dama:
        # Filtra por el modelo seleccionado en el catálogo
        filtro = (df["NAME"].astype(str).str.strip() == modelo_dama) & \
                 (df["METAL"].astype(str).str.strip() == metal_dama)
        
        if not df.loc[filtro].empty:
            fila = df.loc[filtro].iloc[0]
            peso = fila.get("PESO", 0)
            kilates = str(fila.get("CARAT", 0))
            price_cost = fila.get("PRICE COST", 0) # Costo de fabricación/diamantes, etc.
            
            _, monto_dama = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates, 0), peso)
            monto_total += monto_dama + price_cost

    # --- Cálculo caballero ---
    if modelo_cab:
        # Filtra por el modelo seleccionado en el catálogo
        filtro = (df["NAME"].astype(str).str.strip() == modelo_cab) & \
                 (df["METAL"].astype(str).str.strip() == metal_cab)
                 
        if not df.loc[filtro].empty:
            fila = df.loc[filtro].iloc[0]
            peso = fila.get("PESO", 0)
            kilates = str(fila.get("CARAT", 0))
            price_cost = fila.get("PRICE COST", 0)
            
            _, monto_cab = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates, 0), peso)
            monto_total += monto_cab + price_cost

    # --------------------- HTML/JINJA2 para el Formulario ---------------------
    # Uso de Tailwind CSS para un diseño limpio y responsive
    
    # Mensaje de estado del oro (Actualizado para mostrar el estado)
    if status == "live" and precio_onza is not None:
        precio_oro_status = f"Precio Oro Onza: ${precio_onza:,.2f} USD (LIVE)"
        precio_oro_color = "text-green-600 font-medium"
    elif status == "fallback":
        # Mensaje claro cuando usa el fallback debido al 403
        precio_oro_status = f"No se pudo obtener el precio del oro (Error 403/429). Usando precio de respaldo: ${precio_onza:,.2f} USD."
        precio_oro_color = "text-yellow-700 font-bold bg-yellow-100 p-2 rounded"
    else:
        precio_oro_status = "No se pudo obtener el precio del oro. Cálculos no disponibles."
        precio_oro_color = "text-red-600 font-bold"
    
    html_form = f"""
    <!DOCTYPE html>
    <html lang="{idioma.lower()}">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{t['titulo']}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; }}
            .card {{ background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); }}
            input[type="text"], input[type="email"], select {{ 
                border: 1px solid #d1d5db; padding: 10px; border-radius: 8px; width: 100%; box-sizing: border-box; 
                transition: border-color 0.2s;
            }}
            input:focus, select:focus {{ border-color: #4f46e5; outline: none; }}
        </style>
    </head>
    <body class="p-4 md:p-8 flex justify-center items-start min-h-screen">
        <div class="w-full max-w-2xl card p-6 md:p-10 mt-6">
            <h1 class="text-3xl font-extrabold mb-4 text-gray-800 text-center">{t['titulo']}</h1>
            <p class="text-center text-sm mb-6 {precio_oro_color}">{precio_oro_status}</p>

            <form method="POST" action="/" class="space-y-4">
                <!-- Selectores de Idioma y Cliente -->
                <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0">
                    <div class="w-full md:w-1/3">
                        <label for="idioma" class="block text-sm font-medium text-gray-700 mb-1">Idioma / Language</label>
                        <select id="idioma" name="idioma" onchange="this.form.submit()">
                            <option value="Español" {'selected' if es else ''}>Español</option>
                            <option value="English" {'selected' if not es else ''}>English</option>
                        </select>
                    </div>
                    <div class="w-full md:w-2/3">
                        <label for="cliente" class="block text-sm font-medium text-gray-700 mb-1">{t['cliente']}</label>
                        <input type="text" id="cliente" name="cliente" value="{cliente}" required>
                    </div>
                </div>

                <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0">
                    <div class="w-full md:w-1/2">
                        <label for="telefono" class="block text-sm font-medium text-gray-700 mb-1">{t['telefono']}</label>
                        <input type="text" id="telefono" name="telefono" value="{telefono}">
                    </div>
                    <div class="w-full md:w-1/2">
                        <label for="correo" class="block text-sm font-medium text-gray-700 mb-1">{t['correo']}</label>
                        <input type="email" id="correo" name="correo" value="{correo}" required>
                    </div>
                </div>
                
                <div>
                    <label for="direccion" class="block text-sm font-medium text-gray-700 mb-1">{t['direccion']}</label>
                    <input type="text" id="direccion" name="direccion" value="{direccion}">
                </div>
                
                <!-- Sección de Modelos Seleccionados -->
                <h2 class="text-xl font-semibold pt-4 text-indigo-700">Modelos de Anillos</h2>
                <div class="bg-indigo-50 p-4 rounded-lg space-y-3">
                    <p class="text-sm font-medium text-gray-700">
                        {t['modelo_dama']}: 
                        <span class="font-bold text-gray-900">{modelo_dama} ({metal_dama})</span>
                    </p>
                    <p class="text-sm font-medium text-gray-700">
                        {t['modelo_cab']}: 
                        <span class="font-bold text-gray-900">{modelo_cab} ({metal_cab})</span>
                    </p>
                    
                    <a href="{url_for('catalogo')}" class="inline-block px-4 py-2 text-white bg-indigo-600 rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 text-sm font-semibold">
                        {t['catalogo_btn']}
                    </a>
                </div>

                <!-- Resultado del Cálculo -->
                <div class="pt-6">
                    <label class="block text-lg font-bold text-gray-800 mb-2">{t['monto']}</label>
                    <p class="text-4xl font-extrabold text-indigo-600">${monto_total:,.2f} USD</p>
                    <p class="text-sm text-gray-500 mt-2">Este monto se calcula en base al precio actual del oro (Spot Price) y el costo del producto.</p>
                </div>
                
                <div class="pt-6">
                    <button type="submit" class="w-full px-6 py-3 bg-green-600 text-white font-bold rounded-lg shadow-lg hover:bg-green-700 transition duration-150 focus:outline-none focus:ring-4 focus:ring-green-500 focus:ring-opacity-50">
                        {t['guardar']} (Añadir a la base de datos)
                    </button>
                </div>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_form)

@app.route("/catalogo", methods=["GET", "POST"])
def catalogo():
    """
    Ruta para ver y seleccionar anillos del catálogo.
    """
    df, _ = cargar_datos()
    
    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    
    t = {
        "titulo": "Catálogo de Anillos de Boda" if es else "Wedding Ring Catalog",
        "volver": "Volver al Formulario" if es else "Back to Form",
        "dama": "Dama" if es else "Lady",
        "caballero": "Caballero" if es else "Gentleman",
        "seleccion_actual": "Selección actual" if es else "Current selection"
    }
    
    # Manejar el POST (cuando el usuario selecciona un anillo y pulsa guardar/volver)
    if request.method == "POST":
        # Las selecciones se guardan en la sesión para que las use la ruta '/'
        if "seleccion_dama" in request.form:
            modelo, metal = request.form["seleccion_dama"].split(";")
            session["modelo_dama"] = modelo
            session["metal_dama"] = metal
        else: # Si el radio button no fue seleccionado (e.g. si no se tocó)
            session["modelo_dama"] = session.get("modelo_dama", "")
            session["metal_dama"] = session.get("metal_dama", "")
            
        if "seleccion_cab" in request.form:
            modelo, metal = request.form["seleccion_cab"].split(";")
            session["modelo_cab"] = modelo
            session["metal_cab"] = metal
        else:
            session["modelo_cab"] = session.get("modelo_cab", "")
            session["metal_cab"] = session.get("metal_cab", "")
            
        # Redirigir al formulario principal después de guardar
        return redirect(url_for("formulario"))

    # Preparar el catálogo (limpiar N/A)
    catalogo = df[["NAME", "METAL", "Ruta Foto", "CARAT"]].dropna(subset=["NAME", "METAL", "Ruta Foto"]).to_dict(orient="records")

    # Obtener la selección actual para marcar los radio buttons
    modelo_dama_actual = session.get("modelo_dama", "")
    metal_dama_actual = session.get("metal_dama", "")
    
    modelo_cab_actual = session.get("modelo_cab", "")
    metal_cab_actual = session.get("metal_cab", "")

    # --------------------- HTML/JINJA2 para el Catálogo ---------------------
    html_catalogo = f"""
    <!DOCTYPE html>
    <html lang="{idioma.lower()}">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{t['titulo']}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; }}
            .card {{ background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }}
            .ring-card {{ transition: transform 0.2s; }}
            .ring-card:hover {{ transform: translateY(-5px); }}
        </style>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            <h1 class="text-3xl font-extrabold mb-8 text-gray-800 text-center">{t['titulo']}</h1>

            <form method="POST" action="{url_for('catalogo')}">

                <!-- Botones de Acción -->
                <div class="mb-8 flex justify-between items-center bg-white p-4 card sticky top-0 z-10">
                    <div>
                        <h2 class="text-xl font-semibold text-indigo-700">{t['seleccion_actual']}:</h2>
                        <p class="text-sm">
                            <span class="font-bold">Dama:</span> {modelo_dama_actual} ({metal_dama_actual}) | 
                            <span class="font-bold">Caballero:</span> {modelo_cab_actual} ({metal_cab_actual})
                        </p>
                    </div>
                    <button type="submit" class="px-6 py-3 bg-indigo-600 text-white font-bold rounded-lg shadow-md hover:bg-indigo-700 transition duration-150">
                        {t['volver']}
                    </button>
                </div>
            
                <!-- Cuadrícula del Catálogo -->
                <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-6">
                    """
    
    for item in catalogo:
        modelo = str(item['NAME']).strip()
        metal = str(item['METAL']).strip()
        carat = str(item.get('CARAT', '')).strip()
        ruta_foto = item['Ruta Foto']
        
        # El valor de la selección será 'MODELO;METAL'
        valor_seleccion = f"{modelo};{metal}"
        
        # Verificar si está actualmente seleccionado
        is_dama_selected = (modelo == modelo_dama_actual and metal == metal_dama_actual)
        is_cab_selected = (modelo == modelo_cab_actual and metal == metal_cab_actual)
        
        html_catalogo += f"""
                    <div class="ring-card card p-4 flex flex-col items-center text-center">
                        <!-- Imagen (Nota: Esto asume que la ruta funciona en el servidor) -->
                        <img src="{ruta_foto}" alt="{modelo} {metal}" class="w-full h-auto rounded-lg mb-3 object-cover" onerror="this.onerror=null;this.src='https://placehold.co/200x200/cccccc/333333?text=No+Image'">

                        <p class="text-lg font-semibold text-gray-900">{modelo}</p>
                        <p class="text-sm text-gray-600">{metal} {carat}K</p>

                        <div class="mt-4 space-y-2 w-full">
                            <!-- Radio Button Dama -->
                            <label class="flex items-center space-x-2 p-2 bg-pink-100 rounded-lg cursor-pointer hover:bg-pink-200">
                                <input type="radio" name="seleccion_dama" value="{valor_seleccion}" 
                                       {'checked' if is_dama_selected else ''}
                                       class="form-radio text-pink-500 h-4 w-4">
                                <span class="text-sm font-medium text-pink-700">{t['dama']}</span>
                            </label>
                            
                            <!-- Radio Button Caballero -->
                            <label class="flex items-center space-x-2 p-2 bg-blue-100 rounded-lg cursor-pointer hover:bg-blue-200">
                                <input type="radio" name="seleccion_cab" value="{valor_seleccion}" 
                                       {'checked' if is_cab_selected else ''}
                                       class="form-radio text-blue-500 h-4 w-4">
                                <span class="text-sm font-medium text-blue-700">{t['caballero']}</span>
                            </label>
                        </div>
                    </div>
                    """

    html_catalogo += """
                </div>
                
                <!-- Botón final de Volver (por si el usuario está al final de la página) -->
                <div class="mt-8 text-center">
                    <button type="submit" class="px-8 py-3 bg-indigo-600 text-white font-bold rounded-lg shadow-xl hover:bg-indigo-700 transition duration-150">
                        Volver y Aplicar Selección
                    </button>
                </div>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_catalogo)

if __name__ == '__main__':
    print("\n--- INICIANDO SERVIDOR FLASK EN MODO DESARROLLO ---")
    print(f"URL del Formulario: http://127.0.0.1:5000/")
    print(f"URL del Catálogo: http://127.0.0.1:5000/catalogo")
    app.run(debug=True)
