import requests
import os
import pandas as pd
from flask import Flask, jsonify, request, render_template_string, session, redirect, url_for
import re 
import logging

# Configuración de Logging
logging.basicConfig(level=logging.INFO)

# --- CONFIGURACIÓN GLOBAL ---
app = Flask(__name__)
# ¡IMPORTANTE! Clave secreta OBLIGATORIA para usar 'session'.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "una_clave_secreta_fuerte_aqui_para_testing")

# Se asume que el archivo Excel debe estar en el mismo directorio.
EXCEL_PATH = "Formulario Catalogo.xlsm" 
FACTOR_KILATES = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}
DEFAULT_GOLD_PRICE = 2000.00 # USD por Onza

# --------------------- FUNCIONES DE UTILIDAD ---------------------

def obtener_precio_oro():
    """
    Obtiene el precio actual del oro (XAU/USD) por onza desde la API.
    Retorna (precio, estado) donde estado es "live" o "fallback".
    """
    API_KEY = "goldapi-4g9e8p719mgvhodho-io" 
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": API_KEY, "Content-Type": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status() 
        data = response.json()
        price = data.get("price")
        
        if price is not None:
            logging.info(f"Precio del Oro: ${price:,.2f} (LIVE)")
            return price, "live"
        
        logging.warning("API respondió OK (200), pero faltaba el precio. Usando fallback.")
        return DEFAULT_GOLD_PRICE, "fallback"

    except requests.exceptions.HTTPError as e:
        logging.error(f"ERROR HTTP ({e.response.status_code}) al obtener precio del oro: {e}. Usando fallback.")
        return DEFAULT_GOLD_PRICE, "fallback"
        
    except requests.RequestException as e:
        logging.error(f"Error de conexión al obtener precio del oro: {e}. Usando fallback.")
        return DEFAULT_GOLD_PRICE, "fallback"
    except Exception as e:
        logging.error(f"Error inesperado en obtener_precio_oro: {e}. Usando fallback.")
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
        # Se asume que las columnas relevantes tienen los nombres esperados.
        df = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=1)
        df_size = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl")
        
        # Limpieza de encabezados de columnas
        df.columns = df.columns.str.strip()
        df_size.columns = df_size.columns.str.strip()
        
        # Convierte las columnas de clave a string y elimina espacios en blanco para asegurar coincidencias
        for col in ["NAME", "METAL", "CARAT", "Ruta Foto"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
            else:
                 logging.warning(f"Columna '{col}' falta en WEDDING BANDS.")

        for col in ["NAME", "ANCHO", "SIZE", "PESO", "PESO_AJUSTADO"]:
            if col in df_size.columns:
                # Sólo 'PESO' y 'PESO_AJUSTADO' necesitan ser numéricos al final, pero se limpian primero
                df_size[col] = df_size[col].astype(str).str.strip()
            else:
                logging.warning(f"Columna '{col}' falta en SIZE.")
        
        return df, df_size
    except FileNotFoundError:
        logging.error(f"ERROR: Archivo '{EXCEL_PATH}' no encontrado.")
        return pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        logging.error(f"Error al leer el archivo Excel: {e}")
        return pd.DataFrame(), pd.DataFrame()

def obtener_nombre_archivo_imagen(ruta_completa):
    """
    Extrae el nombre del archivo del path.
    Ahora solo debería ser necesario para limpiar por si el Excel aún tiene paths.
    """
    if pd.isna(ruta_completa) or ruta_completa is None:
        return None
    ruta_str = str(ruta_completa).strip()
    if not ruta_str:
        return None
        
    # Obtiene el nombre del archivo y lo pone en minúsculas para evitar problemas
    nombre_archivo = os.path.basename(ruta_str).lower()
    
    # Limpieza adicional
    return nombre_archivo.replace('%20', ' ')

# --------------------- RUTAS FLASK CORREGIDAS ---------------------

@app.route("/", methods=["GET", "POST"])
def formulario():
    """Ruta principal del formulario: maneja la visualización y el cálculo final."""
    
    # Cargar los dos DataFrames
    df, df_size = cargar_datos() 
    precio_onza, status = obtener_precio_oro()

    idioma = request.form.get("idioma", session.get("idioma", "Español"))
    session["idioma"] = idioma
    es = idioma == "Español"

    t = {
        "titulo": "Formulario de Presupuesto u Orden" if es else "Estimate or Work Order Form",
        "seleccionar": "Seleccione una opción de catálogo" if es else "Select a catalog option",
        # ... (otras traducciones) ...
    }
    
    # Obtener detalles de la sesión (vienen de /seleccionar_detalles)
    modelo_dama = session.get("modelo_dama", t['seleccionar'])
    metal_dama = session.get("metal_dama", "")
    kilates_dama = session.get("kilates_dama", "") 
    ancho_dama = session.get("ancho_dama", "")     
    talla_dama = session.get("talla_dama", "")     
    
    modelo_cab = session.get("modelo_cab", t['seleccionar'])
    metal_cab = session.get("metal_cab", "")
    kilates_cab = session.get("kilates_cab", "") 
    ancho_cab = session.get("ancho_cab", "")       
    talla_cab = session.get("talla_cab", "")       
    
    # ... (Manejo de POST para datos de cliente y idioma) ...
    cliente = request.form.get("cliente", "")
    telefono = request.form.get("telefono", "")
    correo = request.form.get("correo", "")
    direccion = request.form.get("direccion", "")

    if request.method == "POST" and "idioma" in request.form:
         return redirect(url_for("formulario")) 

    monto_total = 0.0

    # --- Función de Búsqueda de Peso y Costo ---
    def obtener_peso_y_costo(modelo, metal, kilates, ancho, talla):
        if not all([modelo, metal, kilates, ancho, talla]) or modelo == t['seleccionar']:
            return 0, 0
            
        # 1. Buscar el PESO en df_size (por Modelo, Ancho, y Talla)
        filtro_peso = (df_size["NAME"] == modelo) & \
                      (df_size["ANCHO"] == ancho) & \
                      (df_size["SIZE"] == talla)
        
        peso = 0
        if not df_size.loc[filtro_peso].empty:
            peso_fila = df_size.loc[filtro_peso].iloc[0]
            # Prioriza 'PESO_AJUSTADO' si existe, sino usa 'PESO'
            peso = peso_fila.get("PESO_AJUSTADO", peso_fila.get("PESO", 0)) 
            # Convierte a float, manejando posibles strings "N/A" o None
            try:
                peso = float(peso)
            except (ValueError, TypeError):
                peso = 0
        
        # 2. Buscar el COSTO FIJO en df (por Modelo, Metal, y Kilate)
        filtro_costo = (df["NAME"] == modelo) & \
                       (df["METAL"] == metal) & \
                       (df["CARAT"] == kilates)
        
        price_cost = 0
        if not df.loc[filtro_costo].empty:
            costo_fila = df.loc[filtro_costo].iloc[0]
            price_cost = costo_fila.get("PRICE COST", 0)
            try:
                price_cost = float(price_cost)
            except (ValueError, TypeError):
                price_cost = 0

        return peso, price_cost

    # --- Cálculo dama ---
    peso_dama, cost_dama = obtener_peso_y_costo(modelo_dama, metal_dama, kilates_dama, ancho_dama, talla_dama)
    monto_dama = 0.0
    if peso_dama > 0 and precio_onza is not None and kilates_dama in FACTOR_KILATES:
        _, monto_oro_dama = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_dama, 0), peso_dama)
        monto_dama = monto_oro_dama + cost_dama
        monto_total += monto_dama

    # --- Cálculo caballero ---
    peso_cab, cost_cab = obtener_peso_y_costo(modelo_cab, metal_cab, kilates_cab, ancho_cab, talla_cab)
    monto_cab = 0.0
    if peso_cab > 0 and precio_onza is not None and kilates_cab in FACTOR_KILATES:
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_cab, 0), peso_cab)
        monto_cab = monto_oro_cab + cost_cab
        monto_total += monto_cab

    # --------------------- HTML/JINJA2 para el Formulario ---------------------
    # ... (HTML del formulario, asegúrate de actualizar el display de la selección)
    
    precio_oro_status = f"Precio Oro Onza: ${precio_onza:,.2f} USD ({status.upper()})"
    precio_oro_color = "text-green-600 font-medium" if status == "live" else "text-yellow-700 font-bold bg-yellow-100 p-2 rounded"
    
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
        </style>
    </head>
    <body class="p-4 md:p-8 flex justify-center items-start min-h-screen">
        <div class="w-full max-w-2xl card p-6 md:p-10 mt-6">
            <h1 class="text-3xl font-extrabold mb-4 text-gray-800 text-center">{t['titulo']}</h1>
            <p class="text-center text-sm mb-6 {precio_oro_color}">{precio_oro_status}</p>

            <form method="POST" action="/" class="space-y-4">
                <h2 class="text-xl font-semibold pt-4 text-indigo-700">Modelos de Anillos</h2>
                <div class="bg-indigo-50 p-4 rounded-lg space-y-3">
                    <p class="text-sm font-medium text-gray-700">
                        Modelo Dama: 
                        <span class="font-bold text-gray-900">
                            {modelo_dama} 
                            {' (' + metal_dama + ' ' + kilates_dama + 'K - ' + ancho_dama + 'mm, Talla ' + talla_dama + ')' if all([metal_dama, kilates_dama, ancho_dama, talla_dama]) else ''}
                        </span>
                        <span class="text-xs text-gray-500">
                            {' - Monto Oro y Costo: $' + f'{monto_dama:,.2f}' + ' USD (Peso: ' + f'{peso_dama:,.2f}' + 'g)' if monto_dama > 0 else ''}
                        </span>
                    </p>
                    <p class="text-sm font-medium text-gray-700">
                        Modelo Caballero: 
                        <span class="font-bold text-gray-900">
                            {modelo_cab} 
                            {' (' + metal_cab + ' ' + kilates_cab + 'K - ' + ancho_cab + 'mm, Talla ' + talla_cab + ')' if all([metal_cab, kilates_cab, ancho_cab, talla_cab]) else ''}
                        </span>
                        <span class="text-xs text-gray-500">
                             {' - Monto Oro y Costo: $' + f'{monto_cab:,.2f}' + ' USD (Peso: ' + f'{peso_cab:,.2f}' + 'g)' if monto_cab > 0 else ''}
                        </span>
                    </p>
                    
                    <a href="{url_for('catalogo')}" class="inline-block px-4 py-2 text-white bg-indigo-600 rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 text-sm font-semibold">
                        Abrir Catálogo
                    </a>
                </div>

                <div class="pt-6">
                    <label class="block text-lg font-bold text-gray-800 mb-2">Monto total del presupuesto</label>
                    <p class="text-4xl font-extrabold text-indigo-600">${monto_total:,.2f} USD</p>
                    <p class="text-sm text-gray-500 mt-2">Este monto se calcula en base al precio actual del oro, el kilate, el ancho y la talla.</p>
                </div>
                
                <div class="pt-6">
                    <button type="submit" class="w-full px-6 py-3 bg-green-600 text-white font-bold rounded-lg shadow-lg hover:bg-green-700 transition duration-150 focus:outline-none focus:ring-4 focus:ring-green-500 focus:ring-opacity-50">
                        Guardar (Añadir a la base de datos)
                    </button>
                </div>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_form)

@app.route("/catalogo", methods=["GET"])
def catalogo():
    """
    Ruta para ver y seleccionar anillos del catálogo.
    Redirige a /seleccionar_detalles/ después de elegir el metal/kilate.
    """
    df, _ = cargar_datos()
    
    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    
    t = {
        "titulo": "Catálogo de Anillos de Boda" if es else "Wedding Ring Catalog",
        "volver": "Volver al Formulario" if es else "Back to Form",
        "dama": "Dama" if es else "Lady",
        "caballero": "Caballero" if es else "Gentleman",
        "seleccion_actual": "Selección actual" if es else "Current selection",
        "metal": "Metal" if es else "Metal",
        "kilates": "Kilates" if es else "Carat"
    }
    
    # Preparar el catálogo (limpiar N/A)
    df_catalogo = df[["NAME", "METAL", "Ruta Foto", "CARAT"]].dropna(subset=["NAME", "METAL", "Ruta Foto", "CARAT"])
    df_catalogo["NOMBRE_FOTO"] = df_catalogo["Ruta Foto"].apply(obtener_nombre_archivo_imagen)

    # 1. Agrupar el catálogo por el nombre del modelo (NAME)
    catalogo_agrupado = {}
    
    for _, fila in df_catalogo.iterrows():
        modelo = str(fila["NAME"]).strip()
        metal = str(fila["METAL"]).strip()
        carat = str(fila["CARAT"]).strip()
        nombre_foto = fila["NOMBRE_FOTO"]
        
        if modelo not in catalogo_agrupado:
            catalogo_agrupado[modelo] = {
                "NOMBRE_FOTO": nombre_foto,
                "COMBINACIONES": set() # Usar set para evitar duplicados de combinación
            }
            
        # Añadir la combinación específica (Modelo;Metal;Carat)
        catalogo_agrupado[modelo]["COMBINACIONES"].add((metal, carat))

    # Ordenar las combinaciones para consistencia
    for modelo in catalogo_agrupado:
        catalogo_agrupado[modelo]["COMBINACIONES"] = sorted(list(catalogo_agrupado[modelo]["COMBINACIONES"]))
    
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
        </style>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            <h1 class="text-3xl font-extrabold mb-8 text-gray-800 text-center">{t['titulo']}</h1>
            
            <div class="mb-8 text-center">
                <a href="{url_for('formulario')}" class="inline-block px-6 py-3 bg-indigo-600 text-white font-bold rounded-lg shadow-md hover:bg-indigo-700 transition duration-150">
                    {t['volver']}
                </a>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                """
    
    for modelo, data in catalogo_agrupado.items():
        nombre_foto = data['NOMBRE_FOTO']
        ruta_web_foto = url_for('static', filename=nombre_foto)

        html_catalogo += f"""
                    <div class="card p-4 flex flex-col items-center text-center">
                        <img src="{ruta_web_foto}" alt="{modelo}" class="w-full h-auto max-h-48 object-contain rounded-lg mb-3" onerror="this.onerror=null;this.src='{url_for('static', filename='placeholder.png')}';">

                        <p class="text-xl font-bold text-gray-900 mb-4">{modelo}</p>

                        <div class="mt-2 space-y-3 w-full border-t pt-3">
                            <p class="text-sm font-semibold text-indigo-700">Seleccione {t['metal']} / {t['kilates']}:</p>
                    """
        
        for metal, carat in data['COMBINACIONES']:
            
            html_catalogo += f"""
                            <div class="bg-gray-50 p-3 rounded-lg border">
                                <p class="text-sm font-medium text-gray-800 mb-2">{metal} {carat}K</p>
                                
                                <a href="{url_for('seleccionar_detalles', tipo='dama', modelo=modelo, metal=metal, kilates=carat)}" 
                                   class="inline-block w-full px-3 py-1.5 text-white bg-pink-500 rounded text-xs font-semibold hover:bg-pink-600 transition duration-150 text-center mb-1">
                                    {t['dama']} ({t['kilates']}, Ancho, Talla)
                                </a>
                                
                                <a href="{url_for('seleccionar_detalles', tipo='cab', modelo=modelo, metal=metal, kilates=carat)}" 
                                   class="inline-block w-full px-3 py-1.5 text-white bg-blue-500 rounded text-xs font-semibold hover:bg-blue-600 transition duration-150 text-center">
                                    {t['caballero']} ({t['kilates']}, Ancho, Talla)
                                </a>
                            </div>
                            """
        
        html_catalogo += """
                        </div>
                    </div>
                    """

    html_catalogo += """
                </div>
            </div>
        </body>
        </html>
        """
    return render_template_string(html_catalogo)

@app.route("/seleccionar_detalles/<tipo>/<modelo>/<metal>/<kilates>", methods=["GET", "POST"])
def seleccionar_detalles(tipo, modelo, metal, kilates):
    """
    Ruta intermedia para seleccionar ANCHO y SIZE después de elegir un producto.
    """
    df, df_size = cargar_datos()
    
    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    
    t = {
        "ancho": "Ancho (mm)" if es else "Width (mm)",
        "talla": "Talla (Size)",
        "guardar": "Confirmar y Volver al Formulario" if es else "Confirm and Return to Form"
    }
    
    # 1. Filtrar opciones de ANCHO y SIZE basadas en el modelo
    filtro_size = (df_size["NAME"].astype(str).str.strip() == modelo)
    
    # Obtener valores únicos y ordenados
    anchos_disponibles = sorted(df_size.loc[filtro_size, "ANCHO"].astype(str).str.strip().unique().tolist())
    tallas_disponibles = sorted(df_size.loc[filtro_size, "SIZE"].astype(str).str.strip().unique().tolist(), key=lambda x: (re.sub(r'\D', '', x), x)) # Ordena números primero

    # Valores preseleccionados desde la sesión
    ancho_actual = session.get(f"ancho_{tipo}", anchos_disponibles[0] if anchos_disponibles else "")
    talla_actual = session.get(f"talla_{tipo}", tallas_disponibles[0] if tallas_disponibles else "")
    
    # Manejar el caso de que el valor guardado no esté en las opciones disponibles
    if ancho_actual not in anchos_disponibles: ancho_actual = anchos_disponibles[0] if anchos_disponibles else ""
    if talla_actual not in tallas_disponibles: talla_actual = tallas_disponibles[0] if tallas_disponibles else ""
    
    if request.method == "POST":
        # Guardar las selecciones finales en la sesión
        session[f"modelo_{tipo}"] = modelo
        session[f"metal_{tipo}"] = metal
        session[f"kilates_{tipo}"] = kilates
        session[f"ancho_{tipo}"] = request.form.get("ancho")
        session[f"talla_{tipo}"] = request.form.get("talla")
        
        # Redirigir al formulario principal
        return redirect(url_for("formulario"))
    
    # --- HTML para la selección de detalles ---
    
    html_detalles = f"""
    <!DOCTYPE html>
    <html lang="{idioma.lower()}">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Seleccionar Detalles</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; }}
            .card {{ background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }}
        </style>
    </head>
    <body class="p-4 md:p-8 flex justify-center items-start min-h-screen">
        <div class="w-full max-w-lg card p-6 md:p-10 mt-6">
            <h1 class="text-2xl font-extrabold mb-4 text-gray-800 text-center">Seleccionar Detalles para {tipo.capitalize()}</h1>
            <p class="text-center text-lg text-indigo-600 mb-6 font-bold">{modelo} | {metal} {kilates}K</p>

            <form method="POST" action="">
                <div class="space-y-6">
                    <div>
                        <label for="ancho" class="block text-sm font-medium text-gray-700 mb-1">{t['ancho']}</label>
                        <select id="ancho" name="ancho" class="w-full p-2 border border-gray-300 rounded-lg">
                            {''.join([f'<option value="{a}" {"selected" if a == ancho_actual else ""}>{a} mm</option>' for a in anchos_disponibles])}
                        </select>
                    </div>

                    <div>
                        <label for="talla" class="block text-sm font-medium text-gray-700 mb-1">{t['talla']}</label>
                        <select id="talla" name="talla" class="w-full p-2 border border-gray-300 rounded-lg">
                            {''.join([f'<option value="{s}" {"selected" if s == talla_actual else ""}>{s}</option>' for s in tallas_disponibles])}
                        </select>
                    </div>
                    
                    <a href="{url_for('catalogo')}" class="inline-block px-4 py-2 text-indigo-600 font-semibold hover:text-indigo-800 transition duration-150">
                        Cambiar Modelo/Metal
                    </a>

                    <button type="submit" class="w-full px-6 py-3 bg-indigo-600 text-white font-bold rounded-lg shadow-lg hover:bg-indigo-700 transition duration-150">
                        {t['guardar']}
                    </button>
                </div>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_detalles)

if __name__ == '__main__':
    logging.info("\n--- INICIANDO SERVIDOR FLASK EN MODO DESARROLLO ---")
    app.run(debug=True)