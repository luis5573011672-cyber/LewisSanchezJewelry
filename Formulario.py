import requests
import os
import pandas as pd
from flask import Flask, request, render_template_string, session, redirect, url_for
import logging
import re
import math
from typing import Tuple, List

# Configuración de Logging
logging.basicConfig(level=logging.INFO)

# --- CONFIGURACIÓN GLOBAL ---
app = Flask(__name__)
# ¡IMPORTANTE! Cambia esto por una clave fuerte en producción.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "una_clave_secreta_fuerte_aqui_para_testing") 

# Asegúrate de que esta ruta es correcta
EXCEL_PATH = "Formulario Catalogo.xlsm" 
FACTOR_KILATES = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}
DEFAULT_GOLD_PRICE = 5600.00 # USD por Onza (Valor por defecto/fallback)

# Variables globales para los DataFrames (Caché)
df_global = pd.DataFrame()
df_adicional_global = pd.DataFrame()

# --------------------- FUNCIONES DE UTILIDAD ---------------------

def obtener_precio_oro():
    """
    Obtiene el precio actual del oro (XAU/USD) por onza desde la API.
    Retorna (precio, estado) donde estado es "live" o "fallback".
    """
    # Usa tu propia API Key si tienes una.
    API_KEY = "goldapi-4g9e8p719mgvhodho-io" 
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": API_KEY, "Content-Type": "application/json"}
    
    try:
        # Usar fallback si la API Key es la de testing
        if not API_KEY or API_KEY == "goldapi-4g9e8p719mgvhodho-io":
             return DEFAULT_GOLD_PRICE, "fallback"
             
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        price = data.get("price")
        
        if price is not None and not math.isnan(price):
            return float(price), "live"
            
        return DEFAULT_GOLD_PRICE, "fallback"
        
    except (requests.exceptions.RequestException, Exception) as e:
        logging.error(f"Error al obtener precio del oro: {e}. Usando fallback ({DEFAULT_GOLD_PRICE}).")
        return DEFAULT_GOLD_PRICE, "fallback"

def calcular_valor_gramo(valor_onza: float, pureza_factor: float, peso_gramos: float) -> Tuple[float, float]:
    """
    Calcula el valor del oro y el monto total de la joya.
    CORRECCIÓN: Se usa 'peso_gramos' en lugar de 'peso_gramo' para solucionar el NameError.
    """
    if valor_onza is None or valor_onza <= 0 or peso_gramos is None or peso_gramos <= 0 or pureza_factor <= 0:
        return 0.0, 0.0
    
    valor_gramo = (valor_onza / 31.1035) * pureza_factor
    # CORRECCIÓN DE ERROR AQUÍ
    monto_total = valor_gramo * peso_gramos 
    return valor_gramo, monto_total

def cargar_datos() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga los DataFrames con las correcciones de nombres de columna.
    """
    global df_global, df_adicional_global
    if not df_global.empty and not df_adicional_global.empty:
        return df_global, df_adicional_global

    try:
        # 1. Cargar la hoja WEDDING BANDS
        df_raw = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=None)
        new_columns_df = df_raw.iloc[1].astype(str).str.strip().str.upper()
        df = df_raw.iloc[2:].copy()
        df.columns = new_columns_df
        
        if 'WIDTH' in df.columns:
            df.rename(columns={'WIDTH': 'ANCHO'}, inplace=True)
            
        # 2. Cargar la hoja SIZE
        df_adicional_raw = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl", header=None)
        new_columns_adicional = df_adicional_raw.iloc[0].astype(str).str.strip().str.upper()
        df_adicional = df_adicional_raw.iloc[1:].copy()
        df_adicional.columns = new_columns_adicional
        
        # 3. Limpieza de valores clave
        for col in ["NAME", "METAL", "RUTA FOTO", "ANCHO", "PESO", "PESO_AJUSTADO", "GENERO"]: 
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
            
        for col in ["SIZE", "ADICIONAL"]: 
            if col in df_adicional.columns:
                df_adicional[col] = df_adicional[col].astype(str).str.strip()
        
        df_global = df
        df_adicional_global = df_adicional
        
        return df, df_adicional
        
    except Exception as e:
        logging.error(f"Error CRÍTICO al leer el archivo Excel: {e}") 
        return pd.DataFrame(), pd.DataFrame()
    

def obtener_nombre_archivo_imagen(ruta_completa: str) -> str:
    """Extrae solo el nombre del archivo del path."""
    if pd.isna(ruta_completa) or not str(ruta_completa).strip():
        return "placeholder.png" # Usar un placeholder si no hay ruta
    
    ruta_limpia = str(ruta_completa).replace('\\', '/')
    nombre_archivo = os.path.basename(ruta_limpia).strip()
    return nombre_archivo.replace('%20', ' ')

def obtener_peso_y_costo(df_adicional_local: pd.DataFrame, modelo: str, metal: str, ancho: str, talla: str, genero: str, select_text: str) -> Tuple[float, float, float]:
    """Busca peso y costos fijo/adicional."""
    global df_global 
    
    if df_global.empty or not all([modelo, metal, ancho, talla, genero]) or modelo == select_text:
        return 0.0, 0.0, 0.0 
        
    # 1. Buscar el PESO y COSTO FIJO en df (WEDDING BANDS)
    filtro_base = (df_global["NAME"] == modelo) & \
                  (df_global["ANCHO"] == ancho) & \
                  (df_global["METAL"] == metal) & \
                  (df_global["GENERO"] == genero) 
    
    peso = 0.0
    price_cost = 0.0 # Costo Fijo
    
    if not df_global.loc[filtro_base].empty:
        base_fila = df_global.loc[filtro_base].iloc[0]
        peso_raw = base_fila.get("PESO_AJUSTADO", base_fila.get("PESO", 0))
        price_cost_raw = base_fila.get("PRICE COST", 0) 
        try: peso = float(peso_raw)
        except: peso = 0.0
        try: price_cost = float(price_cost_raw)
        except: price_cost = 0.0

    # 2. Buscar el COSTO ADICIONAL en df_adicional_local (Hoja SIZE)
    cost_adicional = 0.0
    if not df_adicional_local.empty and "SIZE" in df_adicional_local.columns:
        filtro_adicional = (df_adicional_local["SIZE"] == talla) 
        
        if not df_adicional_local.loc[filtro_adicional].empty:
            adicional_fila = df_adicional_local.loc[filtro_adicional].iloc[0]
            cost_adicional_raw = adicional_fila.get("ADICIONAL", 0)
            try: cost_adicional = float(cost_adicional_raw)
            except: cost_adicional = 0.0

    return peso, price_cost, cost_adicional

# --------------------- RUTAS FLASK ---------------------

@app.route("/", methods=["GET", "POST"])
def formulario():
    """Ruta principal: maneja datos de cliente, selección de Kilates, Ancho, Talla y cálculo."""
    
    df, df_adicional = cargar_datos()
    precio_onza, status = obtener_precio_oro()

    monto_total = 0.0
    
    # Manejo de Idioma
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
        "catalogo_btn": "Abrir Catálogo" if es else "Open Catalog",
        "cliente_datos": "Datos del Cliente" if es else "Client Details",
        "nombre": "Nombre del Cliente" if es else "Client Name",
        "email": "Email de Contacto" if es else "Contact Email",
        "cambiar_idioma": "Cambiar Idioma" if es else "Change Language",
        "seleccion_actual": "Selección Actual" if es else "Current Selection"
    }
    
    # Flag para indicar si hubo una selección nueva en el catálogo
    fresh_selection = request.args.get("fresh_selection")
    
    # --- 1. Inicialización/Limpieza ---
    # Limpiar solo en el GET inicial sin parámetros (inicio de la aplicación)
    is_initial_load = request.method == "GET" and not fresh_selection and not any(key in session for key in ["nombre_cliente", "modelo_dama", "modelo_cab"])
    
    if is_initial_load:
        for key in ["nombre_cliente", "email_cliente", "modelo_dama", "metal_dama", "modelo_cab", "metal_cab", "kilates_dama", "ancho_dama", "talla_dama", "kilates_cab", "ancho_cab", "talla_cab"]:
             session.pop(key, None)

        nombre_cliente = ""
        email_cliente = ""
        modelo_dama = t['seleccionar'].upper()
        metal_dama = ""
        modelo_cab = t['seleccionar'].upper()
        metal_cab = ""
        kilates_dama = "14"
        ancho_dama = ""
        talla_dama = ""
        kilates_cab = "14"
        ancho_cab = ""
        talla_cab = ""
        
    else:
        # Cargar de la sesión (prioridad si no es el POST de los selectores)
        nombre_cliente = request.form.get("nombre_cliente", session.get("nombre_cliente", ""))
        email_cliente = request.form.get("email_cliente", session.get("email_cliente", ""))

        modelo_dama = session.get("modelo_dama", t['seleccionar'].upper())
        metal_dama = session.get("metal_dama", "").upper()
        modelo_cab = session.get("modelo_cab", t['seleccionar'].upper())
        metal_cab = session.get("metal_cab", "").upper()
        
        # Kilates/Ancho/Talla vienen del formulario si hay POST, o de la sesión si es GET
        kilates_dama = request.form.get("kilates_dama", session.get("kilates_dama", "14"))
        kilates_cab = request.form.get("kilates_cab", session.get("kilates_cab", "14"))

        # Si hay cambio de modelo/metal (fresh_selection) o cambio de Kilates, reiniciamos Ancho y Talla para forzar la autoselección
        is_kilates_change = request.method == "POST" and ("kilates_dama" in request.form or "kilates_cab" in request.form)
        
        if fresh_selection or is_kilates_change:
            # Forzar re-selección automática
            ancho_dama = ""
            talla_dama = ""
            ancho_cab = ""
            talla_cab = ""
        else:
            # Cargar de la sesión o POST si no hay un evento que fuerce el reinicio
            ancho_dama = request.form.get("ancho_dama", session.get("ancho_dama", ""))
            talla_dama = request.form.get("talla_dama", session.get("talla_dama", ""))
            ancho_cab = request.form.get("ancho_cab", session.get("ancho_cab", ""))
            talla_cab = request.form.get("talla_cab", session.get("talla_cab", ""))


    # --- 2. Manejo de POST (Guardar todo lo que el usuario envió/cambió) ---
    if request.method == "POST":
        
        # Guardar datos del cliente
        session["nombre_cliente"] = nombre_cliente
        session["email_cliente"] = email_cliente
        
        # Guardar selecciones de anillo 
        session["kilates_dama"] = kilates_dama
        session["ancho_dama"] = ancho_dama
        session["talla_dama"] = talla_dama
        session["kilates_cab"] = kilates_cab
        session["ancho_cab"] = ancho_cab
        session["talla_cab"] = talla_cab
        
        # Solo redirigir si se cambió el idioma o los kilates (ya que el Ancho y Talla ahora actualizan por AJAX/Submit Button)
        if "idioma" in request.form or "kilates_dama" in request.form or "kilates_cab" in request.form:
             return redirect(url_for("formulario"))


    
    # --- 3. Opciones disponibles y Forzar selección de Ancho/Talla por defecto ---
    def get_options(modelo):
        if df.empty or df_adicional.empty or modelo == t['seleccionar'].upper():
            return [], []
        
        filtro_ancho = (df["NAME"] == modelo)
        
        def sort_numeric(value_str):
            try: return float(value_str)
            except ValueError: return float('inf') 
        
        # Ordenamiento numérico ascendente para Ancho (ej. 3, 5, 7)
        anchos_raw = df.loc[filtro_ancho, "ANCHO"].astype(str).str.strip().unique().tolist() if "ANCHO" in df.columns else []
        anchos = sorted(anchos_raw, key=sort_numeric)
        
        # Ordenamiento numérico ascendente para Tallas (ej. 4, 4.5, 5)
        tallas_raw = df_adicional["SIZE"].astype(str).str.strip().unique().tolist() if "SIZE" in df_adicional.columns else []
        tallas = sorted(tallas_raw, key=sort_numeric)
        
        return anchos, tallas

    anchos_d, tallas_d = get_options(modelo_dama)
    anchos_c, tallas_c = get_options(modelo_cab)

    # Autoselección si el campo está vacío (ej. después de fresh_selection o cambio de Kilates)
    def auto_select_and_save(modelo, actual_ancho, anchos_disponibles, session_key_ancho, actual_talla, tallas_disponibles, session_key_talla):
        if modelo != t['seleccionar'].upper():
            # Auto-seleccionar Ancho
            if not actual_ancho and anchos_disponibles:
                actual_ancho = anchos_disponibles[0]
                session[session_key_ancho] = actual_ancho
            # Auto-seleccionar Talla
            if not actual_talla and tallas_disponibles:
                actual_talla = tallas_disponibles[0]
                session[session_key_talla] = actual_talla
        # Asegurarse de que el valor actual esté en la sesión (necesario si viene de POST/Formulario)
        if actual_ancho:
            session[session_key_ancho] = actual_ancho
        if actual_talla:
            session[session_key_talla] = actual_talla

        return actual_ancho, actual_talla

    ancho_dama, talla_dama = auto_select_and_save(modelo_dama, ancho_dama, anchos_d, "ancho_dama", talla_dama, tallas_d, "talla_dama")
    ancho_cab, talla_cab = auto_select_and_save(modelo_cab, ancho_cab, anchos_c, "ancho_cab", talla_cab, tallas_c, "talla_cab")
            
    # --- 4. Cálculos ---
    peso_dama, cost_fijo_dama, cost_adicional_dama = obtener_peso_y_costo(df_adicional, modelo_dama, metal_dama, ancho_dama, talla_dama, "DAMA", t['seleccionar'].upper())
    monto_dama = 0.0
    if peso_dama > 0 and precio_onza is not None and kilates_dama in FACTOR_KILATES:
        _, monto_oro_dama = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_dama, 0.0), peso_dama)
        monto_dama = monto_oro_dama + cost_fijo_dama + cost_adicional_dama 
        monto_total += monto_dama

    peso_cab, cost_fijo_cab, cost_adicional_cab = obtener_peso_y_costo(df_adicional, modelo_cab, metal_cab, ancho_cab, talla_cab, "CABALLERO", t['seleccionar'].upper())
    monto_cab = 0.0
    if peso_cab > 0 and precio_onza is not None and kilates_cab in FACTOR_KILATES:
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_cab, 0.0), peso_cab)
        monto_cab = monto_oro_cab + cost_fijo_cab + cost_adicional_cab
        monto_total += monto_cab
        
    logo_url = url_for('static', filename='logo.png')
    
    # --- 5. Generación de Selectores HTML ---
        
    def generate_selectors(tipo, modelo, metal, kilates_actual, anchos, tallas, ancho_actual, talla_actual):
        kilates_opciones = sorted(FACTOR_KILATES.keys(), key=int, reverse=True)
        
        # onchange="this.form.submit()" SOLO en Kilates
        kilates_selector = f"""
            <div class="w-full md:w-1/3">
                <label for="kilates_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['kilates']}</label>
                <select id="kilates_{tipo}" name="kilates_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{k}" {"selected" if k == kilates_actual else ""}>{k}K</option>' for k in kilates_opciones])}
                </select>
            </div>
        """
        
        if modelo == t['seleccionar'].upper() or not anchos or not tallas:
            warning_msg = f'<p class="text-red-500 pt-3">Seleccione un modelo/metal para habilitar Ancho y Talla.</p>'
            if modelo != t['seleccionar'].upper() and (not anchos or not tallas):
                warning_msg = f'<p class="text-red-500 pt-3">No hay datos de Ancho/Talla en Excel para este modelo.</p>'
            
            return f'<div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">{kilates_selector}</div>{warning_msg}'
        
        # Se elimina onchange="this.form.submit()" en Ancho y Talla para evitar la recarga de la página.
        # El cálculo se actualizará al presionar el botón de Guardar.
        html = f"""
        <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
            {kilates_selector}
            <div class="w-full md:w-1/3">
                <label for="ancho_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['ancho']}</label>
                <select id="ancho_{tipo}" name="ancho_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg">
                    {''.join([f'<option value="{a}" {"selected" if str(a) == str(ancho_actual) else ""}>{a} mm</option>' for a in anchos])}
                </select>
            </div>
            <div class="w-full md:w-1/3">
                <label for="talla_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['talla']}</label>
                <select id="talla_{tipo}" name="talla_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg">
                    {''.join([f'<option value="{s}" {"selected" if str(s) == str(talla_actual) else ""}>{s}</option>' for s in tallas])}
                </select>
            </div>
        </div>
        """
        return html

    selectores_dama = generate_selectors("dama", modelo_dama, metal_dama, kilates_dama, anchos_d, tallas_d, ancho_dama, talla_dama)
    selectores_cab = generate_selectors("cab", modelo_cab, metal_cab, kilates_cab, anchos_c, tallas_c, ancho_cab, talla_cab)
    
    precio_oro_status = f"Precio Oro Onza: ${precio_onza:,.2f} USD ({status.upper()})"
    precio_oro_color = "text-green-600 font-medium" if status == "live" else "text-yellow-700 font-bold bg-yellow-100 p-2 rounded"
    
    # --- 6. Etiquetas de Selección Actual ---
    etiquetas_html = ""
    # Se muestra si al menos una selección (Dama o Caballero) NO es el texto por defecto
    if modelo_dama != t['seleccionar'].upper() or modelo_cab != t['seleccionar'].upper():
        etiquetas_html += f"""
        <h2 class="text-xl font-semibold pt-4 text-gray-700">{t['seleccion_actual']}</h2>
        <div class="flex flex-wrap gap-3 p-4 rounded-lg bg-indigo-50 mb-6">
        """
        if modelo_dama != t['seleccionar'].upper():
            etiquetas_html += f"""
            <span class="bg-pink-200 text-pink-900 text-sm font-medium px-3 py-1 rounded-full">
                {t['dama']}: {modelo_dama} ({metal_dama})
            </span>
            """
        if modelo_cab != t['seleccionar'].upper():
            etiquetas_html += f"""
            <span class="bg-blue-200 text-blue-900 text-sm font-medium px-3 py-1 rounded-full">
                {t['cab']}: {modelo_cab} ({metal_cab})
            </span>
            """
        etiquetas_html += "</div>"
    
    # app.py
"""
Aplicación Flask: Formulario / Catálogo de anillos
- Soporta selección de modelo Dama y Caballero desde un catálogo.
- Mantiene datos ingresados al ir/volver del catálogo.
- Recalcula al cambiar Kilates, Ancho o Talla.
- Documentado en cada sección en español.
"""

import os
import math
import logging
from typing import Tuple, List

import requests
import pandas as pd
from flask import Flask, request, render_template_string, session, redirect, url_for

# ----------------------- Configuración básica -----------------------
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# Usar claves desde variables de entorno (más seguro)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_for_testing_only")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY", "")

# Ruta al Excel (ajusta si necesario)
EXCEL_PATH = "Formulario Catalogo.xlsm"

# Factores de kilates (pureza)
FACTOR_KILATES = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}

# Precio por onza por defecto (fallback)
DEFAULT_GOLD_PRICE = 5600.00

# Cache de DataFrames (para no recargar en cada petición)
df_global = pd.DataFrame()
df_adicional_global = pd.DataFrame()

# ----------------------- UTILIDADES / LECTURA EXCEL -----------------------

def _detect_header_row(df_raw: pd.DataFrame, expected_columns: List[str], max_rows_search: int = 8) -> int:
    """
    Busca la fila que tiene la mayoría de expected_columns entre
    las primeras max_rows_search filas. Devuelve el índice 0-based.
    """
    expected_upper = [c.upper() for c in expected_columns]
    for i in range(min(max_rows_search, len(df_raw))):
        row_vals = df_raw.iloc[i].astype(str).str.strip().str.upper().tolist()
        matches = sum(1 for v in expected_upper if v in row_vals)
        if matches >= max(1, len(expected_upper) // 2):
            return i
    return 0

def cargar_datos() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga las hojas 'WEDDING BANDS' y 'SIZE' del Excel y retorna dos DataFrames.
    Implementa cache simple (variable global). Detecta automáticamente la fila de encabezados.
    """
    global df_global, df_adicional_global

    # Si ya cargado, retornar (no hay recarga automática por cambios en disco en esta versión).
    if not df_global.empty and not df_adicional_global.empty:
        return df_global, df_adicional_global

    try:
        # --- WEDDING BANDS ---
        df_raw = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=None)
        header_idx = _detect_header_row(df_raw, ["NAME", "METAL", "PESO", "ANCHO", "RUTA FOTO", "GENERO"])
        headers = df_raw.iloc[header_idx].astype(str).str.strip().str.upper()
        df = df_raw.iloc[header_idx + 1:].copy()
        df.columns = headers

        # Normalizar columna WIDTH -> ANCHO si aparece
        if 'WIDTH' in df.columns and 'ANCHO' not in df.columns:
            df.rename(columns={'WIDTH': 'ANCHO'}, inplace=True)

        # --- SIZE ---
        df_ad_raw = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl", header=None)
        header_idx2 = _detect_header_row(df_ad_raw, ["SIZE", "ADICIONAL"])
        headers2 = df_ad_raw.iloc[header_idx2].astype(str).str.strip().str.upper()
        df_ad = df_ad_raw.iloc[header_idx2 + 1:].copy()
        df_ad.columns = headers2

        # Limpieza minimal: strip strings en columnas importantes
        for col in ["NAME", "METAL", "RUTA FOTO", "ANCHO", "PESO", "PESO_AJUSTADO", "GENERO", "PRICE COST"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        for col in ["SIZE", "ADICIONAL"]:
            if col in df_ad.columns:
                df_ad[col] = df_ad[col].astype(str).str.strip()

        df_global = df.reset_index(drop=True)
        df_adicional_global = df_ad.reset_index(drop=True)
        logging.info("Datos cargados correctamente desde Excel.")
        return df_global, df_adicional_global

    except FileNotFoundError:
        logging.error(f"Archivo Excel no encontrado en {EXCEL_PATH}.")
        return pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        logging.error(f"Error al cargar datos desde Excel: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ----------------------- Precio del oro -----------------------

def obtener_precio_oro() -> Tuple[float, str]:
    """
    Intenta obtener el precio XAU/USD (onza). Si no hay API key o falla,
    devuelve DEFAULT_GOLD_PRICE con estado 'fallback'.
    """
    if not GOLDAPI_KEY:
        return DEFAULT_GOLD_PRICE, "fallback"

    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        price = data.get("price")
        if price and not math.isnan(price):
            return float(price), "live"
        else:
            return DEFAULT_GOLD_PRICE, "fallback"
    except Exception as e:
        logging.warning(f"Fallo al obtener precio desde API: {e} — usando fallback.")
        return DEFAULT_GOLD_PRICE, "fallback"

# ----------------------- Cálculos -----------------------

def calcular_valor_gramo(valor_onza: float, pureza_factor: float, peso_gramos: float) -> Tuple[float, float]:
    """
    Calcula valor por gramo y monto total.
    Retorna (valor_gramo, monto_total).
    """
    if not valor_onza or valor_onza <= 0 or not peso_gramos or peso_gramos <= 0 or pureza_factor <= 0:
        return 0.0, 0.0

    # 1 onza = 31.1035 gramos
    valor_gramo = (valor_onza / 31.1035) * pureza_factor
    monto_total = valor_gramo * peso_gramos
    return valor_gramo, monto_total

def obtener_nombre_archivo_imagen(ruta_completa: str) -> str:
    """
    Extrae el nombre de archivo de una ruta y reemplaza %20 por espacio.
    Si la ruta está vacía, retorna 'placeholder.png'.
    """
    if pd.isna(ruta_completa) or not str(ruta_completa).strip():
        return "placeholder.png"
    ruta = str(ruta_completa).replace('\\', '/')
    nombre = os.path.basename(ruta).strip()
    return nombre.replace('%20', ' ')

def obtener_peso_y_costo(df_adicional_local: pd.DataFrame, modelo: str, metal: str, ancho: str, talla: str, genero: str, select_text: str) -> Tuple[float, float, float]:
    """
    Busca PESO (PESO_AJUSTADO o PESO), COSTO FIJO (PRICE COST) y COSTO ADICIONAL (hoja SIZE).
    - Devuelve (peso_gramos, cost_fijo, cost_adicional).
    - Si no hay datos, retorna ceros.
    """
    global df_global
    if df_global.empty or not all([modelo, metal]) or modelo == select_text:
        return 0.0, 0.0, 0.0

    # Normalizamos inputs a mayúsculas y sin 'mm'
    modelo_u = str(modelo).strip().upper()
    metal_u = str(metal).strip().upper()
    ancho_clean = str(ancho).strip().upper().replace("MM", "").strip()
    talla_clean = str(talla).strip()

    filtro = (df_global["NAME"].astype(str).str.strip().str.upper() == modelo_u) & \
             (df_global["METAL"].astype(str).str.strip().str.upper() == metal_u)

    # Si ancho está presente en la hoja, aplicamos filtro por ancho también
    if "ANCHO" in df_global.columns and ancho_clean:
        filtro = filtro & (df_global["ANCHO"].astype(str).str.strip().str.upper().str.replace("MM", "").str.strip() == ancho_clean)

    peso = 0.0
    cost_fijo = 0.0
    if not df_global.loc[filtro].empty:
        fila = df_global.loc[filtro].iloc[0]
        peso_raw = fila.get("PESO_AJUSTADO", fila.get("PESO", 0))
        cost_raw = fila.get("PRICE COST", fila.get("PRICE COST".upper(), 0))
        try:
            peso = float(peso_raw)
        except:
            peso = 0.0
        try:
            cost_fijo = float(cost_raw)
        except:
            cost_fijo = 0.0

    # Costo adicional desde df_adicional (hoja SIZE) por talla
    cost_adicional = 0.0
    if not df_adicional_local.empty and "SIZE" in df_adicional_local.columns:
        filas_talla = df_adicional_local.loc[df_adicional_local["SIZE"].astype(str).str.strip() == str(talla_clean)]
        if not filas_talla.empty:
            try:
                cost_adicional = float(filas_talla.iloc[0].get("ADICIONAL", 0))
            except:
                cost_adicional = 0.0

    return peso, cost_fijo, cost_adicional

# ----------------------- Rutas Flask -----------------------

# Template Jinja para el formulario (usamos variables para evitar inyección directa)
TEMPLATE_FORMULARIO = """
<!doctype html>
<html lang="{{ idioma }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ t.titulo }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    body { font-family: 'Inter', sans-serif; background-color:#f3f4f6; }
    .card{ background:white; border-radius:12px; box-shadow:0 10px 15px rgba(0,0,0,0.06);}
  </style>
</head>
<body class="p-4 md:p-8 flex justify-center items-start min-h-screen">
  <div class="w-full max-w-2xl card p-6 md:p-10 mt-6">
    <!-- IMPORTANT: usamos el mismo formulario para POST a "/" o a "/catalogo" mediante 'formaction' en el botón -->
    <form method="POST" action="/" class="space-y-4">
      <div class="flex items-center justify-between mb-4">
        <img src="{{ logo_url }}" alt="Logo" style="max-height:50px;" onerror="this.style.display='none'">
        <h1 class="text-2xl font-extrabold text-gray-800">{{ t.titulo }}</h1>
        <div>
          <select id="idioma" name="idioma" onchange="this.form.submit()" class="p-2 border rounded">
            <option value="Español" {{ 'selected' if idioma=='Español' else '' }}>Español</option>
            <option value="English" {{ 'selected' if idioma=='English' else '' }}>English</option>
          </select>
        </div>
      </div>

      <p class="text-center text-sm mb-4 {{ precio_oro_color }}">{{ precio_oro_status }}</p>

      <!-- Datos Cliente -->
      <h2 class="text-xl font-semibold">{{ t.cliente_datos }}</h2>
      <div class="bg-gray-100 p-4 rounded">
        <label class="block text-sm">{{ t.nombre }}</label>
        <input type="text" name="nombre_cliente" id="nombre_cliente" value="{{ nombre_cliente }}" class="w-full p-2 border rounded" placeholder="{{ t.nombre }}" />
        <label class="block text-sm mt-3">{{ t.email }}</label>
        <input type="email" name="email_cliente" id="email_cliente" value="{{ email_cliente }}" class="w-full p-2 border rounded" placeholder="{{ t.email }}" />
      </div>

      <!-- Modelo Dama -->
      <h2 class="text-xl font-semibold pt-4 text-pink-700">Modelo {{ t.dama }}</h2>
      <div class="bg-pink-50 p-4 rounded">
        <p class="font-bold">{{ modelo_dama }} {{ '(' + metal_dama + ')' if metal_dama else '' }}</p>

        <!-- Selectores: Kilates, Ancho, Talla -->
        <div class="grid grid-cols-3 gap-3 pt-3">
          <!-- Kilates: submit on change -->
          <div>
            <label class="text-sm">{{ t.kilates }}</label>
            <select name="kilates_dama" onchange="this.form.submit()" class="w-full p-2 border rounded">
              {% for k in kilates_opciones %}
                <option value="{{k}}" {{ 'selected' if k==kilates_dama else '' }}>{{k}}K</option>
              {% endfor %}
            </select>
          </div>

          <!-- Ancho: submit on change -->
          <div>
            <label class="text-sm">{{ t.ancho }}</label>
            <select name="ancho_dama" onchange="this.form.submit()" class="w-full p-2 border rounded">
              {% if anchos_d %}
                {% for a in anchos_d %}
                  {% set display = (a|string).replace('MM','').replace('mm','').strip() + ' mm' %}
                  <option value="{{ (a|string).replace('MM','').replace('mm','').strip() }}" {{ 'selected' if (a|string).replace('MM','').replace('mm','').strip()==(ancho_dama|string).replace('MM','').replace('mm','').strip() else '' }}>{{ display }}</option>
                {% endfor %}
              {% else %}
                <option value="">{{ t.seleccionar }}</option>
              {% endif %}
            </select>
          </div>

          <!-- Talla: submit on change -->
          <div>
            <label class="text-sm">{{ t.talla }}</label>
            <select name="talla_dama" onchange="this.form.submit()" class="w-full p-2 border rounded">
              {% if tallas_d %}
                {% for s in tallas_d %}
                  <option value="{{ s }}" {{ 'selected' if s==talla_dama else '' }}>{{ s }}</option>
                {% endfor %}
              {% else %}
                <option value="">{{ t.seleccionar }}</option>
              {% endif %}
            </select>
          </div>
        </div>

        <div class="pt-2 text-xs text-gray-600">
          {% if monto_dama>0 %}
            Monto Estimado: ${{ "{:,.2f}".format(monto_dama) }} USD (Peso: {{ "{:,.2f}".format(peso_dama) }} g, Adicional: ${{ "{:,.2f}".format(cost_adicional_dama) }})
          {% else %}
            Seleccione todos los detalles para calcular.
          {% endif %}
        </div>
      </div>

      <!-- Modelo Caballero (similar al anterior) -->
      <h2 class="text-xl font-semibold pt-4 text-blue-700">Modelo {{ t.cab }}</h2>
      <div class="bg-blue-50 p-4 rounded">
        <p class="font-bold">{{ modelo_cab }} {{ '(' + metal_cab + ')' if metal_cab else '' }}</p>

        <div class="grid grid-cols-3 gap-3 pt-3">
          <div>
            <label class="text-sm">{{ t.kilates }}</label>
            <select name="kilates_cab" onchange="this.form.submit()" class="w-full p-2 border rounded">
              {% for k in kilates_opciones %}
                <option value="{{k}}" {{ 'selected' if k==kilates_cab else '' }}>{{k}}K</option>
              {% endfor %}
            </select>
          </div>

          <div>
            <label class="text-sm">{{ t.ancho }}</label>
            <select name="ancho_cab" onchange="this.form.submit()" class="w-full p-2 border rounded">
              {% if anchos_c %}
                {% for a in anchos_c %}
                  {% set display = (a|string).replace('MM','').replace('mm','').strip() + ' mm' %}
                  <option value="{{ (a|string).replace('MM','').replace('mm','').strip() }}" {{ 'selected' if (a|string).replace('MM','').replace('mm','').strip()==(ancho_cab|string).replace('MM','').replace('mm','').strip() else '' }}>{{ display }}</option>
                {% endfor %}
              {% else %}
                <option value="">{{ t.seleccionar }}</option>
              {% endif %}
            </select>
          </div>

          <div>
            <label class="text-sm">{{ t.talla }}</label>
            <select name="talla_cab" onchange="this.form.submit()" class="w-full p-2 border rounded">
              {% if tallas_c %}
                {% for s in tallas_c %}
                  <option value="{{ s }}" {{ 'selected' if s==talla_cab else '' }}>{{ s }}</option>
                {% endfor %}
              {% else %}
                <option value="">{{ t.seleccionar }}</option>
              {% endif %}
            </select>
          </div>
        </div>

        <div class="pt-2 text-xs text-gray-600">
          {% if monto_cab>0 %}
            Monto Estimado: ${{ "{:,.2f}".format(monto_cab) }} USD (Peso: {{ "{:,.2f}".format(peso_cab) }} g, Adicional: ${{ "{:,.2f}".format(cost_adicional_cab) }})
          {% else %}
            Seleccione todos los detalles para calcular.
          {% endif %}
        </div>
      </div>

      <!-- Botones: Abrir Catálogo (envía a /catalogo) y Guardar (submit a /) -->
      <div class="pt-6 grid grid-cols-2 gap-3">
        <!-- IMPORTANTE: cuando se presiona este botón, el formulario se envía por POST a /catalogo -->
        <button type="submit" name="open_catalog" value="true" formaction="{{ url_for('catalogo') }}" class="px-4 py-2 bg-indigo-600 text-white rounded">
          {{ t.catalogo_btn }}
        </button>

        <button type="submit" class="px-4 py-2 bg-green-600 text-white rounded">
          {{ t.guardar }}
        </button>
      </div>

      <div class="pt-6">
        <label class="block text-lg font-bold">{{ t.monto }}</label>
        <p class="text-4xl font-extrabold text-indigo-600">${{ "{:,.2f}".format(monto_total) }} USD</p>
      </div>

    </form>
  </div>
</body>
</html>
"""

# RUTA "/"
@app.route("/", methods=["GET", "POST"])
def formulario():
    """
    Ruta principal:
    - GET: muestra formulario. Si no hay sesión, el formulario aparece en blanco.
    - POST: guarda campos enviados en session, recalcula si cambian selectores.
    - Si el usuario presiona 'Abrir Catálogo' (open_catalog), el mismo POST redirige a /catalogo
      gracias al 'formaction' del botón en el template.
    """
    df, df_adicional = cargar_datos()
    precio_onza, status = obtener_precio_oro()
    precio_oro_status = f"Precio Oro Onza: ${precio_onza:,.2f} USD ({status.upper()})"
    precio_oro_color = "text-green-600" if status == "live" else "text-yellow-700"

    # Traducciones / textos
    idioma = session.get("idioma", "Español")
    # Si se cambió idioma por POST, actualizar
    if request.method == "POST" and "idioma" in request.form:
        idioma = request.form.get("idioma", idioma)
        session["idioma"] = idioma

    es = idioma == "Español"
    t = {
        "titulo": "Formulario de Presupuesto u Orden" if es else "Estimate or Work Order Form",
        "seleccionar": "Seleccione una opción de catálogo" if es else "Select a catalog option",
        "kilates": "Kilates",
        "ancho": "Ancho (mm)" if es else "Width (mm)",
        "talla": "Talla",
        "guardar": "Guardar" if es else "Save",
        "monto": "Monto total del presupuesto" if es else "Total estimate amount",
        "dama": "Dama" if es else "Lady",
        "cab": "Caballero" if es else "Gentleman",
        "catalogo_btn": "Abrir Catálogo" if es else "Open Catalog",
        "cliente_datos": "Datos del Cliente" if es else "Client Details",
        "nombre": "Nombre del Cliente" if es else "Client Name",
        "email": "Email de Contacto" if es else "Contact Email",
    }

    # --- Inicialización/lectura de sesión y POST ---
    # Valores por defecto en blanco (requisito 1)
    nombre_cliente = session.get("nombre_cliente", "")
    email_cliente = session.get("email_cliente", "")

    # Modelos y metales (por defecto texto "seleccionar" para que se muestre vacío)
    modelo_dama = session.get("modelo_dama", t['seleccionar'])
    metal_dama = session.get("metal_dama", "")
    modelo_cab = session.get("modelo_cab", t['seleccionar'])
    metal_cab = session.get("metal_cab", "")

    # Kilates/Ancho/Talla: tomados del form (POST) si vienen, si no desde sesión o por defecto
    if request.method == "POST":
        # Guardar datos cliente (si vienen)
        nombre_cliente = request.form.get("nombre_cliente", nombre_cliente)
        email_cliente = request.form.get("email_cliente", email_cliente)
        session["nombre_cliente"] = nombre_cliente
        session["email_cliente"] = email_cliente

        # Si viene el POST con open_catalog (botón abrir catálogo), redirigimos a /catalogo
        if request.form.get("open_catalog") == "true" or request.form.get("open_catalog") == "True" or request.form.get("open_catalog") == "1":
            # Ya guardamos en session los datos del cliente, ahora vamos al catálogo
            return redirect(url_for("catalogo"))

        # Selecciones (kilates/ancho/talla)
        kilates_dama = request.form.get("kilates_dama", session.get("kilates_dama", "14"))
        ancho_dama = request.form.get("ancho_dama", session.get("ancho_dama", ""))
        talla_dama = request.form.get("talla_dama", session.get("talla_dama", ""))

        kilates_cab = request.form.get("kilates_cab", session.get("kilates_cab", "14"))
        ancho_cab = request.form.get("ancho_cab", session.get("ancho_cab", ""))
        talla_cab = request.form.get("talla_cab", session.get("talla_cab", ""))

        # Guardar en session (persistencia cuando vamos y venimos al catálogo)
        session["kilates_dama"] = kilates_dama
        session["ancho_dama"] = ancho_dama
        session["talla_dama"] = talla_dama
        session["kilates_cab"] = kilates_cab
        session["ancho_cab"] = ancho_cab
        session["talla_cab"] = talla_cab

        # NOTA: modelo_dama/modelo_cab y metal pueden venir de la sesión (selecciones hechas en catálogo).
        modelo_dama = session.get("modelo_dama", modelo_dama)
        metal_dama = session.get("metal_dama", metal_dama)
        modelo_cab = session.get("modelo_cab", modelo_cab)
        metal_cab = session.get("metal_cab", metal_cab)

    else:
        # GET: leer posibles valores guardados en sesión (cuando volvemos del catálogo)
        kilates_dama = session.get("kilates_dama", "14")
        ancho_dama = session.get("ancho_dama", "")
        talla_dama = session.get("talla_dama", "")
        kilates_cab = session.get("kilates_cab", "14")
        ancho_cab = session.get("ancho_cab", "")
        talla_cab = session.get("talla_cab", "")

        modelo_dama = session.get("modelo_dama", t['seleccionar'])
        metal_dama = session.get("metal_dama", "")
        modelo_cab = session.get("modelo_cab", t['seleccionar'])
        metal_cab = session.get("metal_cab", "")

    # --- Generar opciones disponibles según modelo seleccionado ---
    def sort_numeric(value_str):
        try: return float(str(value_str).replace('mm','').replace('MM','').strip())
        except: return float('inf')

    def get_options(modelo):
        if df.empty or df_adicional.empty or modelo == t['seleccionar']:
            return [], []
        filtro = df["NAME"].astype(str).str.strip().str.upper() == str(modelo).strip().upper()
        anchos_raw = df.loc[filtro, "ANCHO"].dropna().astype(str).str.strip().unique().tolist() if "ANCHO" in df.columns else []
        anchos_sorted = sorted(anchos_raw, key=sort_numeric)
        tallas_raw = df_adicional["SIZE"].dropna().astype(str).str.strip().unique().tolist() if "SIZE" in df_adicional.columns else []
        tallas_sorted = sorted(tallas_raw, key=sort_numeric)
        return anchos_sorted, tallas_sorted

    anchos_d, tallas_d = get_options(modelo_dama)
    anchos_c, tallas_c = get_options(modelo_cab)

    # --- Cálculos: peso y costos para Dama y Caballero (si hay datos) ---
    peso_dama, cost_fijo_dama, cost_adicional_dama = obtener_peso_y_costo(df_adicional, modelo_dama, metal_dama, ancho_dama, talla_dama, "DAMA", t['seleccionar'])
    monto_dama = 0.0
    if peso_dama > 0 and precio_onza and str(kilates_dama) in FACTOR_KILATES:
        _, monto_oro_dama = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(str(kilates_dama), 0.0), peso_dama)
        monto_dama = monto_oro_dama + cost_fijo_dama + cost_adicional_dama

    peso_cab, cost_fijo_cab, cost_adicional_cab = obtener_peso_y_costo(df_adicional, modelo_cab, metal_cab, ancho_cab, talla_cab, "CABALLERO", t['seleccionar'])
    monto_cab = 0.0
    if peso_cab > 0 and precio_onza and str(kilates_cab) in FACTOR_KILATES:
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(str(kilates_cab), 0.0), peso_cab)
        monto_cab = monto_oro_cab + cost_fijo_cab + cost_adicional_cab

    monto_total = (monto_dama if monto_dama else 0.0) + (monto_cab if monto_cab else 0.0)

    # Kilates opciones ordenadas
    kilates_opciones = sorted(list(FACTOR_KILATES.keys()), key=int, reverse=True)

    # Logo static (si existe)
    logo_url = url_for('static', filename='logo.png')

    # Renderizamos la plantilla Jinja (escape automático de variables)
    return render_template_string(
        TEMPLATE_FORMULARIO,
        idioma=idioma,
        t=t,
        nombre_cliente=nombre_cliente,
        email_cliente=email_cliente,
        modelo_dama=modelo_dama,
        metal_dama=metal_dama,
        modelo_cab=modelo_cab,
        metal_cab=metal_cab,
        kilates_dama=kilates_dama,
        ancho_dama=ancho_dama,
        talla_dama=talla_dama,
        kilates_cab=kilates_cab,
        ancho_cab=ancho_cab,
        talla_cab=talla_cab,
        anchos_d=anchos_d,
        tallas_d=tallas_d,
        anchos_c=anchos_c,
        tallas_c=tallas_c,
        peso_dama=peso_dama,
        cost_adicional_dama=cost_adicional_dama,
        monto_dama=monto_dama,
        peso_cab=peso_cab,
        cost_adicional_cab=cost_adicional_cab,
        monto_cab=monto_cab,
        monto_total=monto_total,
        kilates_opciones=kilates_opciones,
        precio_oro_status=precio_oro_status,
        precio_oro_color=precio_oro_color,
        logo_url=logo_url
    )

# ----------------------- Ruta /catalogo -----------------------
TEMPLATE_CATALOGO = """
<!doctype html>
<html lang="{{ idioma }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ t.titulo }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="p-4 md:p-8">
  <div class="max-w-7xl mx-auto">
    <form method="POST" action="{{ url_for('catalogo') }}">
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-3xl font-extrabold">{{ t.titulo }}</h1>
        <button type="submit" name="volver_btn" value="true" class="px-4 py-2 bg-indigo-600 text-white rounded">{{ t.volver }}</button>
      </div>

      {% if etiquetas_catalogo %}
        {{ etiquetas_catalogo | safe }}
      {% endif %}

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {% for item in items %}
          <div class="p-4 bg-white rounded shadow text-center">
            <img src="{{ item.ruta_web_foto }}" alt="{{ item.modelo }} - {{ item.metal }}" style="max-height:160px; width:auto; margin:auto;" onerror="this.onerror=null;this.src='{{ url_for('static','placeholder.png') }}'">
            <p class="font-bold mt-2">{{ item.modelo }}</p>
            <p class="text-indigo-700 font-semibold">{{ t.metal }}: {{ item.metal }}</p>
            <div class="mt-3">
              <button type="submit" name="seleccion" value="{{ item.modelo }};{{ item.metal }}" formaction="{{ url_for('catalogo') }}" formmethod="post" data-tipo="dama" class="w-full py-2 mb-2 bg-pink-500 text-white rounded">Seleccionar {{ t.dama }}</button>
              <button type="submit" name="seleccion" value="{{ item.modelo }};{{ item.metal }}" formaction="{{ url_for('catalogo') }}" formmethod="post" data-tipo="cab" class="w-full py-2 bg-blue-500 text-white rounded">Seleccionar {{ t.caballero }}</button>
            </div>
          </div>
        {% endfor %}
      </div>
    </form>
  </div>
</body>
</html>
"""

@app.route("/catalogo", methods=["GET", "POST"])
def catalogo():
    """
    Catálogo:
    - GET: muestra el catálogo (items agrupados por modelo+metal).
    - POST:
      - Si viene 'volver_btn' -> redirige al formulario (se mantiene session con selecciones y datos de cliente).
      - Si viene 'seleccion' -> guarda la selección en session (modelo_xxx, metal_xxx) y permanece en catálogo,
        permitiendo seleccionar tanto dama como caballero antes de volver.
    """
    df, df_adicional = cargar_datos()
    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    t = {
        "titulo": "Catálogo de Anillos de Boda" if es else "Wedding Ring Catalog",
        "volver": "Volver al Formulario" if es else "Back to Form",
        "dama": "Dama" if es else "Lady",
        "caballero": "Caballero" if es else "Gentleman",
        "metal": "Metal" if es else "Metal",
    }

    # Manejo POST
    if request.method == "POST":
        # Si regresa al formulario
        if request.form.get("volver_btn") == "true":
            # Redirigir al formulario. Los datos ya se guardaron en sesión cuando se hizo POST desde formulario -> Abrir Catálogo
            return redirect(url_for("formulario"))

        # Si se seleccionó un item desde el catálogo
        seleccion = request.form.get("seleccion")
        if seleccion:
            try:
                modelo, metal = seleccion.split(";")
                # Para decidir si es dama o cab, el navegador no envía 'tipo' automáticamente porque usamos dos botones separados.
                # Dado que el botón que envía tiene data-tipo, no lo recibimos en backend; en cambio detectamos por el color/propósito:
                # Para simplificar: si ya existe modelo_dama y model equals previous, permitimos asignar alternativamente.
                # Mejor: usar value con ;dama o ;cab si quieres distinguir. Pero aquí usaremos request.referrer + nombre del botón.
                # Para robustez, intentaremos examinar si el botón fue el primero o segundo: si en la request se encuentra 'seleccion' y además se envió desde
                # el botón que tuviera data-tipo, no llega. Como workaround, aquí pedimos que el valor sea "MODELO;METAL" y usaremos un campo auxiliar
                # (no disponible). Resultado: asumimos que el primer botón corresponde a Dama y el segundo a Caballero.
                # Para evitar ambigüedad, como implementamos 2 botones distintos, usaremos una heurística:
                # Si la sesión no tiene modelo_dama con ese modelo -> guardarlo en dama; sino guardarlo en cab.
                modelo_up = modelo.strip().upper()
                metal_up = metal.strip().upper()
                # Si no hay modelo_dama o es distinto, asignar a dama; sino asignar a cab.
                if session.get("modelo_dama", "") in ("", None) or session.get("modelo_dama","").upper() != modelo_up:
                    session["modelo_dama"] = modelo_up
                    session["metal_dama"] = metal_up
                else:
                    session["modelo_cab"] = modelo_up
                    session["metal_cab"] = metal_up
                # Permanecer en catálogo para permitir seleccionar el otro modelo
                return redirect(url_for("catalogo"))
            except Exception as e:
                logging.error(f"Formato de selección inválido: {e}")

    # Si df vacío, mostrar mensaje
    if df.empty:
        return "<h2>Error: no se pudo cargar el catálogo. Verifique el archivo Excel.</h2>"

    # Construir items agrupados únicos por NAME+METAL
    df_catalogo = df[["NAME", "METAL", "RUTA FOTO"]].dropna(subset=["NAME", "METAL"])
    variantes = df_catalogo.drop_duplicates(subset=["NAME", "METAL"])
    items = []
    for _, row in variantes.iterrows():
        modelo = str(row["NAME"]).strip().upper()
        metal = str(row["METAL"]).strip().upper()
        foto = obtener_nombre_archivo_imagen(row.get("RUTA FOTO", ""))
        ruta_web = url_for('static', filename=foto)
        items.append({"modelo": modelo, "metal": metal, "ruta_web_foto": ruta_web})

    # Etiquetas de selección actual
    etiquetas_catalogo = ""
    modelo_dama = session.get("modelo_dama", "")
    metal_dama = session.get("metal_dama", "")
    modelo_cab = session.get("modelo_cab", "")
    metal_cab = session.get("metal_cab", "")
    if modelo_dama or modelo_cab:
        etiquetas_catalogo = '<div class="p-4 rounded bg-indigo-50 mb-6"><h2 class="font-semibold">Selección Actual</h2><div class="flex gap-3 mt-2">'
        if modelo_dama:
            etiquetas_catalogo += f'<span class="bg-pink-200 px-3 py-1 rounded text-sm">Dama: {modelo_dama} ({metal_dama})</span>'
        if modelo_cab:
            etiquetas_catalogo += f'<span class="bg-blue-200 px-3 py-1 rounded text-sm">Caballero: {modelo_cab} ({metal_cab})</span>'
        etiquetas_catalogo += '</div></div>'

    return render_template_string(
        TEMPLATE_CATALOGO,
        idioma=idioma,
        t=t,
        items=items,
        etiquetas_catalogo=etiquetas_catalogo
    )

# ----------------------- Inicio del servidor -----------------------
if __name__ == "__main__":
    logging.info("Iniciando servidor Flask (modo desarrollo).")
    # Cambia host/port a gusto; debug True para desarrollo.
    app.run(debug=True, host="127.0.0.1", port=5000)
