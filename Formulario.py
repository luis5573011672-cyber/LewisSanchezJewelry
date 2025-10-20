import requests
import os
import pandas as pd
from flask import Flask, request, render_template_string, session, redirect, url_for
import logging
import re
import math # Para la función obtener_precio_oro

# Configuración de Logging
logging.basicConfig(level=logging.INFO)

# --- CONFIGURACIÓN GLOBAL ---
app = Flask(__name__)
# ¡IMPORTANTE! Clave secreta OBLIGATORIA para usar 'session'.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "una_clave_secreta_fuerte_aqui_para_testing")

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
        # Intento de conexión
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        price = data.get("price")
        
        if price is not None and not math.isnan(price):
            logging.info(f"Precio del Oro: ${price:,.2f} (LIVE)")
            return price, "live"
            
        logging.warning("API respondió OK (200), pero faltaba o era inválido el precio. Usando fallback.")
        return DEFAULT_GOLD_PRICE, "fallback"
        
    except (requests.exceptions.RequestException, Exception) as e:
        # Esto captura el error 429 (Too Many Requests) o errores de conexión.
        logging.error(f"Error al obtener precio del oro: {e}. Usando fallback.")
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
        df = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=1)
        df_size = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl")
        
        # Limpieza de encabezados de columnas
        df.columns = df.columns.str.strip()
        df_size.columns = df_size.columns.str.strip()
        
        # Limpieza de valores clave
        for col in ["NAME", "METAL", "Ruta Foto"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
            
        for col in ["NAME", "ANCHO", "SIZE"]:
            if col in df_size.columns:
                df_size[col] = df_size[col].astype(str).str.strip()
            
        return df, df_size
    except Exception as e:
        logging.error(f"Error al leer el archivo Excel: {e}")
        return pd.DataFrame(), pd.DataFrame()

def obtener_nombre_archivo_imagen(ruta_completa):
    """Extrae solo el nombre del archivo del path, lo limpia y lo pone en minúsculas."""
    if pd.isna(ruta_completa) or not str(ruta_completa).strip():
        return None
    nombre_archivo = os.path.basename(str(ruta_completa)).lower()
    return nombre_archivo.replace('%20', ' ')

# --------------------- RUTAS FLASK CORREGIDAS ---------------------

@app.route("/", methods=["GET", "POST"])
def formulario():
    """Ruta principal: maneja datos de cliente, selección de Kilates, Ancho, Talla y cálculo."""
    
    df, df_size = cargar_datos()
    precio_onza, status = obtener_precio_oro()

    # CORRECCIÓN CLAVE: Inicializar monto_total a 0.0 para evitar UnboundLocalError
    monto_total = 0.0

    idioma = request.form.get("idioma", session.get("idioma", "Español"))
    session["idioma"] = idioma
    es = idioma == "Español"

    t = {
        "titulo": "Formulario de Presupuesto u Orden" if es else "Estimate or Work Order Form",
        "seleccionar": "Seleccione una opción de catálogo" if es else "Select a catalog option",
        "kilates": "Kilates (Carat)",
        "ancho": "Ancho (mm)" if es else "Width (mm)",
        "talla": "Talla (Size)",
        "guardar": "Guardar" if es else "Save",
        "monto": "Monto total del presupuesto" if es else "Total estimate amount",
        "dama": "Dama" if es else "Lady",
        "cab": "Caballero" if es else "Gentleman",
        "catalogo_btn": "Abrir Catálogo" if es else "Open Catalog"
    }
    
    # 1. Obtener selecciones del Catálogo (Modelo y Metal)
    modelo_dama = session.get("modelo_dama", t['seleccionar'])
    metal_dama = session.get("metal_dama", "")
    
    modelo_cab = session.get("modelo_cab", t['seleccionar'])
    metal_cab = session.get("metal_cab", "")
    
    # 2. Obtener Kilates, Ancho y Talla del formulario POST o de la sesión
    kilates_dama = request.form.get("kilates_dama", session.get("kilates_dama", "14")) # Valor por defecto
    ancho_dama = request.form.get("ancho_dama", session.get("ancho_dama", ""))
    talla_dama = request.form.get("talla_dama", session.get("talla_dama", ""))
    
    kilates_cab = request.form.get("kilates_cab", session.get("kilates_cab", "14")) # Valor por defecto
    ancho_cab = request.form.get("ancho_cab", session.get("ancho_cab", ""))
    talla_cab = request.form.get("talla_cab", session.get("talla_cab", ""))

    if request.method == "POST":
        # Guardar todas las selecciones de variables de cálculo
        session["kilates_dama"] = kilates_dama
        session["ancho_dama"] = ancho_dama
        session["talla_dama"] = talla_dama
        
        session["kilates_cab"] = kilates_cab
        session["ancho_cab"] = ancho_cab
        session["talla_cab"] = talla_cab
        
        if "idioma" in request.form:
            return redirect(url_for("formulario"))

    # --- Opciones disponibles (se basan en los modelos seleccionados) ---
    def get_options(modelo):
        if modelo == t['seleccionar']:
            return [], []
        filtro_size = (df_size["NAME"] == modelo)
        anchos = sorted(df_size.loc[filtro_size, "ANCHO"].astype(str).str.strip().unique().tolist())
        # Ordena las tallas numéricamente
        tallas = sorted(df_size.loc[filtro_size, "SIZE"].astype(str).str.strip().unique().tolist(), 
                         key=lambda x: (re.sub(r'\D', '', x), x)) 
        return anchos, tallas

    anchos_d, tallas_d = get_options(modelo_dama)
    anchos_c, tallas_c = get_options(modelo_cab)

    # --- Función de Búsqueda de Peso y Costo ---
    def obtener_peso_y_costo(modelo, metal, ancho, talla):
        if not all([modelo, metal, ancho, talla]) or modelo == t['seleccionar']:
            return 0, 0
            
        # 1. Buscar el PESO en df_size (por Modelo, Ancho, y Talla)
        filtro_peso = (df_size["NAME"] == modelo) & \
                      (df_size["ANCHO"] == ancho) & \
                      (df_size["SIZE"] == talla)
        
        peso = 0
        if not df_size.loc[filtro_peso].empty:
            peso_fila = df_size.loc[filtro_peso].iloc[0]
            peso = peso_fila.get("PESO_AJUSTADO", peso_fila.get("PESO", 0))
            try: peso = float(peso)
            except: peso = 0

        # 2. Buscar el COSTO FIJO en df (solo por Modelo y Metal)
        filtro_costo = (df["NAME"] == modelo) & \
                       (df["METAL"] == metal)
        
        price_cost = 0
        if not df.loc[filtro_costo].empty:
            # Tomamos la primera coincidencia
            costo_fila = df.loc[filtro_costo].iloc[0]
            price_cost = costo_fila.get("PRICE COST", 0)
            try: price_cost = float(price_cost)
            except: price_cost = 0

        return peso, price_cost

    # --- Cálculo dama ---
    peso_dama, cost_dama = obtener_peso_y_costo(modelo_dama, metal_dama, ancho_dama, talla_dama)
    monto_dama = 0.0
    if peso_dama > 0 and precio_onza is not None and kilates_dama in FACTOR_KILATES:
        # Se calcula el valor del oro usando el KILATE seleccionado en el formulario.
        _, monto_oro_dama = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_dama, 0), peso_dama)
        monto_dama = monto_oro_dama + cost_dama
        monto_total += monto_dama

    # --- Cálculo caballero ---
    peso_cab, cost_cab = obtener_peso_y_costo(modelo_cab, metal_cab, ancho_cab, talla_cab)
    monto_cab = 0.0
    if peso_cab > 0 and precio_onza is not None and kilates_cab in FACTOR_KILATES:
        # Se calcula el valor del oro usando el KILATE seleccionado en el formulario.
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_cab, 0), peso_cab)
        monto_cab = monto_oro_cab + cost_cab
        monto_total += monto_cab

    # --------------------- Generación del HTML para el Formulario ---------------------
    
    def generate_selectors(tipo, modelo, metal, kilates_actual, anchos, tallas, ancho_actual, talla_actual):
        kilates_opciones = sorted(FACTOR_KILATES.keys(), key=int, reverse=True)
        
        # Asegurar que el ancho y talla actuales estén en las opciones disponibles o usar el primero
        if anchos and ancho_actual not in anchos: ancho_actual = anchos[0]
        if tallas and talla_actual not in tallas: talla_actual = tallas[0]

        kilates_selector = f"""
            <div class="w-full md:w-1/3">
                <label for="kilates_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['kilates']}</label>
                <select id="kilates_{tipo}" name="kilates_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg">
                    {''.join([f'<option value="{k}" {"selected" if k == kilates_actual else ""}>{k}K</option>' for k in kilates_opciones])}
                </select>
            </div>
        """

        if modelo == t['seleccionar'] or not anchos or not tallas:
            warning_msg = f'<p class="text-red-500 pt-3">Seleccione un modelo/metal para habilitar Ancho y Talla.</p>'
            if modelo != t['seleccionar'] and (not anchos or not tallas):
                warning_msg = f'<p class="text-red-500 pt-3">No hay datos de Ancho/Talla en Excel para este modelo.</p>'
            
            # Devolvemos solo el selector de kilates y la advertencia
            return f'<div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">{kilates_selector}</div>{warning_msg}'
        
        html = f"""
        <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
            {kilates_selector}
            <div class="w-full md:w-1/3">
                <label for="ancho_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['ancho']}</label>
                <select id="ancho_{tipo}" name="ancho_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg">
                    {''.join([f'<option value="{a}" {"selected" if a == ancho_actual else ""}>{a} mm</option>' for a in anchos])}
                </select>
            </div>
            <div class="w-full md:w-1/3">
                <label for="talla_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['talla']}</label>
                <select id="talla_{tipo}" name="talla_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg">
                    {''.join([f'<option value="{s}" {"selected" if s == talla_actual else ""}>{s}</option>' for s in tallas])}
                </select>
            </div>
        </div>
        """
        return html

    selectores_dama = generate_selectors("dama", modelo_dama, metal_dama, kilates_dama, anchos_d, tallas_d, ancho_dama, talla_dama)
    selectores_cab = generate_selectors("cab", modelo_cab, metal_cab, kilates_cab, anchos_c, tallas_c, ancho_cab, talla_cab)
    
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
                <h2 class="text-xl font-semibold pt-4 text-pink-700">Modelo {t['dama']}</h2>
                <div class="bg-pink-50 p-4 rounded-lg space-y-3">
                    <p class="text-sm font-medium text-gray-700">
                        Modelo: <span class="font-bold text-gray-900">{modelo_dama}</span>
                        {' (' + metal_dama + ')' if metal_dama else ''}
                    </p>
                    {selectores_dama}
                    <span class="text-xs text-gray-500 block pt-2">
                        {'Monto Estimado: $' + f'{monto_dama:,.2f}' + ' USD (Peso: ' + f'{peso_dama:,.2f}' + 'g)' if monto_dama > 0 else 'Seleccione todos los detalles para calcular.'}
                    </span>
                </div>

                <h2 class="text-xl font-semibold pt-4 text-blue-700">Modelo {t['cab']}</h2>
                <div class="bg-blue-50 p-4 rounded-lg space-y-3">
                    <p class="text-sm font-medium text-gray-700">
                        Modelo: <span class="font-bold text-gray-900">{modelo_cab}</span>
                        {' (' + metal_cab + ')' if metal_cab else ''}
                    </p>
                    {selectores_cab}
                    <span class="text-xs text-gray-500 block pt-2">
                        {'Monto Estimado: $' + f'{monto_cab:,.2f}' + ' USD (Peso: ' + f'{peso_cab:,.2f}' + 'g)' if monto_cab > 0 else 'Seleccione todos los detalles para calcular.'}
                    </span>
                </div>

                <a href="{url_for('catalogo')}" class="inline-block px-4 py-2 text-white bg-indigo-600 rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 text-sm font-semibold">
                    {t['catalogo_btn']} (Cambiar Modelo/Metal)
                </a>

                <div class="pt-6">
                    <label class="block text-lg font-bold text-gray-800 mb-2">{t['monto']}</label>
                    <p class="text-4xl font-extrabold text-indigo-600">${monto_total:,.2f} USD</p>
                </div>
                
                <div class="pt-6">
                    <button type="submit" class="w-full px-6 py-3 bg-green-600 text-white font-bold rounded-lg shadow-lg hover:bg-green-700 transition duration-150 focus:outline-none focus:ring-4 focus:ring-green-500 focus:ring-opacity-50">
                        {t['guardar']} (Aplicar Cambios y Guardar)
                    </button>
                </div>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_form)

# ------------------------------------------------------------------------------------------------

@app.route("/catalogo", methods=["GET", "POST"])
def catalogo():
    """Ruta del catálogo: selecciona solo Modelo y Metal y vuelve al formulario."""
    df, _ = cargar_datos()
    
    # 1. Manejo del POST: Si se selecciona un producto, guardamos y volvemos.
    if request.method == "POST":
        seleccion = request.form.get("seleccion")
        tipo = request.form.get("tipo")
        
        if seleccion and tipo:
            try:
                # El valor del botón ahora es: 'MODELO;METAL'
                modelo, metal = seleccion.split(";")
                session[f"modelo_{tipo}"] = modelo
                session[f"metal_{tipo}"] = metal
                
                return redirect(url_for("formulario"))
            except ValueError:
                logging.error("Error en el formato de selección del catálogo.")
        
        return redirect(url_for("formulario"))

    # 2. Generación del catálogo (Agrupado por Modelo, opciones por Metal)
    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    
    # Traducciones para el catálogo
    t = {
        "titulo": "Catálogo de Anillos de Boda" if es else "Wedding Ring Catalog",
        "volver": "Volver al Formulario" if es else "Back to Form",
        "dama": "Dama" if es else "Lady",
        "caballero": "Caballero" if es else "Gentleman",
        "metal": "Metal" if es else "Metal",
    }

    # Preparar el catálogo (limpiar N/A)
    df_catalogo = df[["NAME", "METAL", "Ruta Foto"]].dropna(subset=["NAME", "METAL", "Ruta Foto"])
    df_catalogo["NOMBRE_FOTO"] = df_catalogo["Ruta Foto"].apply(obtener_nombre_archivo_imagen)

    catalogo_agrupado = {}
    for _, fila in df_catalogo.iterrows():
        modelo = str(fila["NAME"]).strip()
        metal = str(fila["METAL"]).strip()
        nombre_foto = fila["NOMBRE_FOTO"]
        
        if modelo not in catalogo_agrupado:
            catalogo_agrupado[modelo] = {"NOMBRE_FOTO": nombre_foto, "METALES": set()}
            
        catalogo_agrupado[modelo]["METALES"].add(metal)

    for modelo in catalogo_agrupado:
        catalogo_agrupado[modelo]["METALES"] = sorted(list(catalogo_agrupado[modelo]["METALES"]))
    
    # --------------------- HTML/JINJA2 para el Catálogo (Corregido) ---------------------
    
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
            
            <form method="POST" action="{url_for('catalogo')}">
                <div class="mb-8 text-center">
                    <button type="submit" class="px-6 py-3 bg-indigo-600 text-white font-bold rounded-lg shadow-md hover:bg-indigo-700 transition duration-150">
                        {t['volver']}
                    </button>
                </div>
            
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
    """
    
    for modelo, data in catalogo_agrupado.items():
        nombre_foto = data['NOMBRE_FOTO']
        # ESTA LÍNEA ASEGURA LA RUTA CORRECTA A LA CARPETA 'STATIC'
        # Nota: Asume que tienes una carpeta 'static' en tu directorio de Flask con las imágenes.
        ruta_web_foto = url_for('static', filename=nombre_foto)

        html_catalogo += f"""
                    <div class="card p-4 flex flex-col items-center text-center">
                        <img src="{ruta_web_foto}" alt="{modelo}" class="w-full h-auto max-h-48 object-contain rounded-lg mb-3" onerror="this.onerror=null;this.src='{url_for('static', filename='placeholder.png')}';">
                        <p class="text-xl font-bold text-gray-900 mb-4">{modelo}</p>

                        <div class="mt-2 space-y-3 w-full border-t pt-3">
                            <p class="text-sm font-semibold text-indigo-700">Seleccione {t['metal']}:</p>
                    """
        
        for metal in data['METALES']:
            valor_seleccion = f"{modelo};{metal}" # SOLO MODELO Y METAL
            
            html_catalogo += f"""
                            <div class="bg-gray-50 p-3 rounded-lg border">
                                <p class="text-sm font-medium text-gray-800 mb-2">{metal}</p>
                                
                                <button type="submit" name="seleccion" value="{valor_seleccion}" 
                                        class="inline-block w-full px-3 py-1.5 text-white bg-pink-500 rounded text-xs font-semibold hover:bg-pink-600 transition duration-150 text-center mb-1" 
                                        onclick="document.getElementById('tipo_input').value='dama';">
                                    {t['dama']} (Seleccionar)
                                </button>
                                
                                <button type="submit" name="seleccion" value="{valor_seleccion}" 
                                        class="inline-block w-full px-3 py-1.5 text-white bg-blue-500 rounded text-xs font-semibold hover:bg-blue-600 transition duration-150 text-center"
                                        onclick="document.getElementById('tipo_input').value='cab';">
                                    {t['caballero']} (Seleccionar)
                                </button>
                            </div>
                            """
        
        html_catalogo += """
                        </div>
                    </div>
                    """

    html_catalogo += """
                </div>
                <input type="hidden" id="tipo_input" name="tipo" value="">
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_catalogo)

if __name__ == '__main__':
    logging.info("\n--- INICIANDO SERVIDOR FLASK EN MODO DESARROLLO ---")
    app.run(debug=True)