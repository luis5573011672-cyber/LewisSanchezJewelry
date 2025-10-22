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

# --------------------- CONFIGURACIÓN GLOBAL ---------------------
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
DEFAULT_SELECTION_TEXT = "SELECCIONE UNA OPCIÓN DE CATÁLOGO"

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
        # Usar fallback si la API Key es la de testing o no se especifica
        if not API_KEY or API_KEY == "goldapi-4g9e8p719mgvhodho-io":
             return DEFAULT_GOLD_PRICE, "fallback"
             
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        price = data.get("price")
        
        if price is not None and not math.isnan(price):
            logging.info(f"Precio del Oro: ${price:,.2f} (LIVE)")
            return float(price), "live"
            
        logging.warning("API respondió OK (200), pero faltaba o era inválido el precio. Usando fallback.")
        return DEFAULT_GOLD_PRICE, "fallback"
        
    except (requests.exceptions.RequestException, Exception) as e:
        logging.error(f"Error al obtener precio del oro: {e}. Usando fallback ({DEFAULT_GOLD_PRICE}).")
        return DEFAULT_GOLD_PRICE, "fallback"

def calcular_valor_gramo(valor_onza: float, pureza_factor: float, peso_gramos: float) -> Tuple[float, float]:
    """Calcula el valor del oro y el monto total de la joya."""
    if valor_onza is None or valor_onza <= 0 or peso_gramos is None or peso_gramos <= 0 or pureza_factor <= 0:
        return 0.0, 0.0
    
    valor_gramo = (valor_onza / 31.1035) * pureza_factor
    monto_total = valor_gramo * peso_gramos
    return valor_gramo, monto_total

def cargar_datos() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga los DataFrames desde el archivo Excel.
    """
    global df_global, df_adicional_global
    if not df_global.empty and not df_adicional_global.empty:
        return df_global, df_adicional_global

    try:
        # 1. Cargar la hoja WEDDING BANDS
        df_raw = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=None)
        # Asume que la fila 1 (índice 1) tiene los nombres de las columnas que queremos usar.
        new_columns_df = df_raw.iloc[1].astype(str).str.strip().str.upper()
        df = df_raw.iloc[2:].copy()
        df.columns = new_columns_df
        
        # Unificación de columna de ancho (si existe WIDTH, se renombra a ANCHO)
        if 'WIDTH' in df.columns and 'ANCHO' not in df.columns:
            df.rename(columns={'WIDTH': 'ANCHO'}, inplace=True)
            
        # 2. Cargar la hoja SIZE
        df_adicional_raw = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl", header=None)
        # Asume que la fila 0 (índice 0) tiene los nombres de las columnas.
        new_columns_adicional = df_adicional_raw.iloc[0].astype(str).str.strip().str.upper()
        df_adicional = df_adicional_raw.iloc[1:].copy()
        df_adicional.columns = new_columns_adicional
        
        # 3. Limpieza y Estandarización de valores
        # Limpieza de valores clave en df (WEDDING BANDS)
        for col in ["NAME", "METAL", "RUTA FOTO", "GENERO"]: 
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.upper() 
            
        # Limpieza y estandarización de la columna ANCHO (eliminando 'MM')
        if 'ANCHO' in df.columns:
            df['ANCHO'] = df['ANCHO'].astype(str).apply(limpiar_valor_ancho)
            
        # Limpieza de valores clave en df_adicional (SIZE)
        for col in ["SIZE", "ADICIONAL"]: 
            if col in df_adicional.columns:
                df_adicional[col] = df_adicional[col].astype(str).str.strip().str.upper()
        
        # 4. Verificación mínima de columnas necesarias
        if not all(col in df.columns for col in ["NAME", "METAL", "RUTA FOTO", "ANCHO", "GENERO"]):
             logging.error(f"Columnas CRÍTICAS faltantes en 'WEDDING BANDS'. Actuales: {df.columns.tolist()}")
             return pd.DataFrame(), pd.DataFrame()
             
        df_global = df
        df_adicional_global = df_adicional
        
        logging.info(f"Columnas df (WEDDING BANDS): {df.columns.tolist()}")
        logging.info(f"Columnas df_adicional (SIZE): {df_adicional.columns.tolist()}")
        
        return df, df_adicional
        
    except FileNotFoundError:
        logging.error(f"Error: No se encontró el archivo Excel en la ruta: {EXCEL_PATH}")
        return pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        logging.error(f"Error CRÍTICO al leer el archivo Excel: {e}") 
        return pd.DataFrame(), pd.DataFrame()
    

def limpiar_valor_ancho(valor_ancho: str) -> str:
    """Limpia el valor del ancho, quitando 'MM', 'MM.' o espacios extra, dejando solo el número."""
    if pd.isna(valor_ancho) or not str(valor_ancho).strip():
        return ""
    
    # 1. Eliminar 'MM', 'MM.', 'MM ' o ' MM' (mayúsculas o minúsculas)
    limpio = re.sub(r'\s*MM\s*\.?\s*$', '', str(valor_ancho).strip(), flags=re.IGNORECASE)
    # 2. Quitar el sufijo de milímetros que puede venir pegado o con punto.
    limpio = re.sub(r'MM\.?$', '', limpio, flags=re.IGNORECASE).strip()
    
    return limpio.upper()

def obtener_nombre_archivo_imagen(ruta_completa: str) -> str:
    """
    Extrae solo el nombre del archivo del path, limpia codificación URL y 
    normaliza el nombre para que funcione como estático.
    """
    if pd.isna(ruta_completa) or not str(ruta_completa).strip():
        return "placeholder.png"
    
    ruta_limpia = str(ruta_completa).replace('\\', '/').strip()
    
    # Intenta decodificar URL (%20, etc.)
    try:
        from urllib.parse import unquote
        ruta_limpia = unquote(ruta_limpia)
    except ImportError:
        ruta_limpia = ruta_limpia.replace('%20', ' ')
    
    # Extraer el nombre del archivo al final de la ruta
    match = re.search(r'[^/\\?#]+$', ruta_limpia)
    if match:
        nombre_archivo = match.group(0).strip()
    else:
        nombre_archivo = ruta_limpia.strip()

    # **CLAVE para Flask:** Reemplazar espacios por guiones bajos para nombres de archivos estáticos.
    nombre_normalizado = nombre_archivo.strip().replace(' ', '_') 
    
    # Asegurar que la extensión se mantenga. 
    return nombre_normalizado

def obtener_peso_y_costo(df_adicional_local: pd.DataFrame, modelo: str, metal: str, ancho: str, talla: str, genero: str, select_text: str) -> Tuple[float, float, float]:
    """Busca peso y costos fijo/adicional."""
    global df_global 
    
    # Estandarizar los inputs de búsqueda
    modelo = modelo.upper()
    metal = metal.upper()
    # Usar el ancho LIMPIO para la búsqueda
    ancho_limpio = limpiar_valor_ancho(ancho) 
    talla = talla.upper()
    genero = genero.upper()

    if df_global.empty or not all([modelo, metal, ancho_limpio, talla, genero]) or modelo == select_text:
        return 0.0, 0.0, 0.0 
        
    # 1. Buscar el PESO y COSTO FIJO en df (WEDDING BANDS)
    filtro_base = (df_global["NAME"] == modelo) & \
                  (df_global["ANCHO"] == ancho_limpio) & \
                  (df_global["METAL"] == metal) & \
                  (df_global["GENERO"] == genero) 
    
    peso = 0.0
    price_cost = 0.0 # Costo Fijo
    
    try:
        if not df_global.loc[filtro_base].empty:
            base_fila = df_global.loc[filtro_base].iloc[0]
            # Prioriza PESO_AJUSTADO si existe, sino usa PESO
            peso_raw = base_fila.get("PESO_AJUSTADO", base_fila.get("PESO", 0)) 
            price_cost_raw = base_fila.get("PRICE COST", 0) 
            try: peso = float(peso_raw)
            except: peso = 0.0
            try: price_cost = float(price_cost_raw)
            except: price_cost = 0.0
    except KeyError as e:
         logging.error(f"Error de columna al buscar peso/costo: {e}. Asegúrate de que las columnas están en el Excel.")
         return 0.0, 0.0, 0.0

    # 2. Buscar el COSTO ADICIONAL en df_adicional_local (Hoja SIZE)
    cost_adicional = 0.0
    if not df_adicional_local.empty and "SIZE" in df_adicional_local.columns and "ADICIONAL" in df_adicional_local.columns:
        filtro_adicional = (df_adicional_local["SIZE"] == talla) 
        
        if not df_adicional_local.loc[filtro_adicional].empty:
            adicional_fila = df_adicional_local.loc[filtro_adicional].iloc[0]
            cost_adicional_raw = adicional_fila.get("ADICIONAL", 0)
            try: cost_adicional = float(cost_adicional_raw)
            except: cost_adicional = 0.0

    return peso, price_cost, cost_adicional

def redondear_a_decena_superior(monto: float) -> float:
    """Redondea el monto al alza a la decena más cercana (ej. 1225.49 -> 1230.00)."""
    if monto <= 0:
        return 0.0
    return math.ceil(monto / 10.0) * 10.0

# --------------------- RUTAS FLASK ---------------------

@app.route("/", methods=["GET", "POST"])
def formulario():
    """Ruta principal: maneja datos de cliente, selección de Kilates, Ancho, Talla y cálculo."""
    
    # Cargar datos del Excel
    df, df_adicional = cargar_datos()
    precio_onza, status = obtener_precio_oro()

    monto_total_raw = 0.0
    
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
        "error_excel": "ERROR CRÍTICO: No se pudo cargar el Excel. Revisar log." if df.empty else ""
    }
    
    fresh_selection = request.args.get("fresh_selection")
    
    # --- 1. Lógica de Limpieza Inicial / Persistencia ---
    is_initial_load = request.method == "GET" and not fresh_selection and not session.get("modelo_dama")
    
    if is_initial_load:
        # Limpiar completamente la sesión para un inicio limpio
        for key in list(session.keys()):
             if key not in ["idioma", "nombre_cliente", "email_cliente"]:
                 session.pop(key, None)
             
        # Valores por defecto para el inicio
        nombre_cliente = session.get("nombre_cliente", "")
        email_cliente = session.get("email_cliente", "")
        modelo_dama = DEFAULT_SELECTION_TEXT
        metal_dama = ""
        modelo_cab = DEFAULT_SELECTION_TEXT
        metal_cab = ""
        kilates_dama = "14"
        ancho_dama = ""
        talla_dama = ""
        kilates_cab = "14"
        ancho_cab = ""
        talla_cab = ""
    else:
        # Cargar datos de la sesión (o POST si viene un submit)
        nombre_cliente = request.form.get("nombre_cliente", session.get("nombre_cliente", ""))
        email_cliente = request.form.get("email_cliente", session.get("email_cliente", ""))
        
        # Modelo y Metal vienen de la sesión (establecidos en /catalogo)
        modelo_dama = session.get("modelo_dama", DEFAULT_SELECTION_TEXT).upper()
        metal_dama = session.get("metal_dama", "").upper()
        modelo_cab = session.get("modelo_cab", DEFAULT_SELECTION_TEXT).upper()
        metal_cab = session.get("metal_cab", "").upper()
            
        # Kilates, Ancho y Talla vienen del POST o de la sesión
        kilates_dama = request.form.get("kilates_dama", session.get("kilates_dama", "14"))
        kilates_cab = request.form.get("kilates_cab", session.get("kilates_cab", "14"))

        # Si venimos del catálogo (fresh_selection=True), debemos forzar la autoselección de ancho/talla
        if fresh_selection:
            ancho_dama = ""
            talla_dama = ""
            ancho_cab = ""
            talla_cab = ""
        else:
            # Si NO es fresh_selection, cargamos el último valor enviado por POST o guardado en sesión.
            ancho_dama = limpiar_valor_ancho(request.form.get("ancho_dama", session.get("ancho_dama", "")))
            talla_dama = str(request.form.get("talla_dama", session.get("talla_dama", ""))).strip()
            ancho_cab = limpiar_valor_ancho(request.form.get("ancho_cab", session.get("ancho_cab", "")))
            talla_cab = str(request.form.get("talla_cab", session.get("talla_cab", ""))).strip()


    # --- 2. Manejo de POST (Guardar y redirigir para recálculo) ---
    if request.method == "POST":
        
        # Guardar datos del cliente
        session["nombre_cliente"] = nombre_cliente
        session["email_cliente"] = email_cliente

        # Guardar selecciones de anillo (Kilates, Ancho, Talla) 
        session["kilates_dama"] = kilates_dama
        session["ancho_dama"] = ancho_dama
        session["talla_dama"] = talla_dama
        session["kilates_cab"] = kilates_cab
        session["ancho_cab"] = ancho_cab
        session["talla_cab"] = talla_cab
        
        # Redirigir si se cambió idioma o kilates, ancho, o talla (auto-submit)
        if "idioma" in request.form or "kilates_dama" in request.form or "kilates_cab" in request.form or "ancho_dama" in request.form or "ancho_cab" in request.form or "talla_dama" in request.form or "talla_cab" in request.form:
             return redirect(url_for("formulario"))

    
    # --- 3. Opciones disponibles y Forzar selección de Ancho/Talla por defecto ---
    def get_options(modelo):
        if df.empty or df_adicional.empty or modelo == DEFAULT_SELECTION_TEXT:
            return [], []
        
        filtro_ancho = (df["NAME"] == modelo)
        
        # Función de ordenación numérica (maneja floats y strings)
        def sort_numeric(value_str):
            try: return float(value_str.replace(',', '.'))
            except ValueError: return float('inf') 
        
        # Se obtiene el ancho LIMPIO desde el DataFrame (ya está limpio gracias a cargar_datos)
        anchos_raw = df.loc[filtro_ancho, "ANCHO"].astype(str).str.strip().str.upper().unique().tolist() if "ANCHO" in df.columns else []
        anchos = sorted(list(set(anchos_raw)), key=sort_numeric)
        
        # Ordenar numéricamente la talla
        tallas_raw = df_adicional["SIZE"].astype(str).str.strip().str.upper().unique().tolist() if "SIZE" in df_adicional.columns else []
        tallas = sorted(tallas_raw, key=lambda x: (sort_numeric(re.sub(r'[^\d\.]', '', x)), x))
        
        return anchos, tallas

    anchos_d, tallas_d = get_options(modelo_dama)
    anchos_c, tallas_c = get_options(modelo_cab)

    # Autoselección si el campo está vacío y hay opciones disponibles
    def auto_select_and_save(modelo, actual_ancho, anchos_disponibles, session_key_ancho, actual_talla, tallas_disponibles, session_key_talla):
        if modelo != DEFAULT_SELECTION_TEXT:
            # Auto-seleccionar Ancho
            if not actual_ancho and anchos_disponibles:
                actual_ancho = anchos_disponibles[0]
            # Auto-seleccionar Talla
            if not actual_talla and tallas_disponibles:
                actual_talla = tallas_disponibles[0]
        
        # Guardar en sesión
        session[session_key_ancho] = actual_ancho
        session[session_key_talla] = actual_talla
            
        return actual_ancho, actual_talla

    ancho_dama, talla_dama = auto_select_and_save(modelo_dama, ancho_dama, anchos_d, "ancho_dama", talla_dama, tallas_d, "talla_dama")
    ancho_cab, talla_cab = auto_select_and_save(modelo_cab, ancho_cab, anchos_c, "ancho_cab", talla_cab, tallas_c, "talla_cab")
            
    # --- 4. Cálculos ---
    peso_dama, cost_fijo_dama, cost_adicional_dama = obtener_peso_y_costo(df_adicional, modelo_dama, metal_dama, ancho_dama, talla_dama, "DAMA", DEFAULT_SELECTION_TEXT)
    monto_dama = 0.0
    if peso_dama > 0 and precio_onza is not None and kilates_dama in FACTOR_KILATES:
        _, monto_oro_dama = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_dama, 0.0), peso_dama)
        monto_dama = monto_oro_dama + cost_fijo_dama + cost_adicional_dama 
        monto_total_raw += monto_dama

    peso_cab, cost_fijo_cab, cost_adicional_cab = obtener_peso_y_costo(df_adicional, modelo_cab, metal_cab, ancho_cab, talla_cab, "CABALLERO", DEFAULT_SELECTION_TEXT)
    monto_cab = 0.0
    if peso_cab > 0 and precio_onza is not None and kilates_cab in FACTOR_KILATES:
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_cab, 0.0), peso_cab)
        monto_cab = monto_oro_cab + cost_fijo_cab + cost_adicional_cab
        monto_total_raw += monto_cab
    
    # Aplicar redondeo al alza a la decena superior solo al monto final
    monto_total_redondeado = redondear_a_decena_superior(monto_total_raw)
        
    logo_url = url_for('static', filename='logo.png')
    
    # --- 5. Generación de Selectores HTML ---
        
    def generate_selectors(tipo, modelo, metal, kilates_actual, anchos, tallas, ancho_actual, talla_actual):
        kilates_opciones = sorted(FACTOR_KILATES.keys(), key=int, reverse=True)
        
        # Selector de Kilates
        kilates_selector = f"""
            <div class="w-full md:w-1/3">
                <label for="kilates_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['kilates']}</label>
                <select id="kilates_{tipo}" name="kilates_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{k}" {"selected" if k == kilates_actual else ""}>{k}K</option>' for k in kilates_opciones])}
                </select>
            </div>
        """
        
        if modelo == DEFAULT_SELECTION_TEXT or not anchos or not tallas:
            warning_msg = f'<p class="text-red-500 pt-3">Modelo: <span class="font-bold">{modelo} ({metal if metal else "No Seleccionado"})</span>. Seleccione un modelo/metal para habilitar Ancho y Talla.</p>'
            if modelo != DEFAULT_SELECTION_TEXT and (not anchos or not tallas):
                 warning_msg = f'<p class="text-red-500 pt-3">Modelo: <span class="font-bold">{modelo} ({metal})</span>. No hay datos de Ancho/Talla en Excel para esta combinación.</p>'
            
            return f'<div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">{kilates_selector}</div>{warning_msg}'
        
        # Selectores de Ancho y Talla - **CORREGIDO: Solo muestra el número + ' mm'**
        html = f"""
        <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
            {kilates_selector}
            <div class="w-full md:w-1/3">
                <label for="ancho_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['ancho']}</label>
                <select id="ancho_{tipo}" name="ancho_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{a}" {"selected" if str(a) == str(ancho_actual) else ""}>{a} mm</option>' for a in anchos])}
                </select>
            </div>
            <div class="w-full md:w-1/3">
                <label for="talla_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['talla']}</label>
                <select id="talla_{tipo}" name="talla_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
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
    
    # --------------------- Generación del HTML para el Formulario ---------------------
        
    html_form = f"""
    <!DOCTYPE html>
    <html lang="{idioma.lower()}">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{t['titulo']}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
            body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; }}
            .card {{ background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); }}
            .header-content {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 24px;
            }}
            .logo-img {{
                max-height: 50px; 
                width: auto;
                min-width: 50px; /* Asegura espacio para el logo */
                margin-right: 15px;
            }}
            .title-group {{
                flex-grow: 1;
                text-align: center;
            }}
            .language-selector-container {{
                width: 100px; 
                text-align: right;
                margin-left: 15px; /* Espacio para el selector */
            }}
        </style>
    </head>
    <body class="p-4 md:p-8 flex justify-center items-start min-h-screen">
        <div class="w-full max-w-2xl card p-6 md:p-10 mt-6">
            
            <form method="POST" action="/" class="space-y-4">
            
                <div class="header-content">
                    <img src="{logo_url}" alt="Logo" class="logo-img" onerror="this.style.display='none';" />
                    <div class="title-group">
                        <h1 class="text-3xl font-extrabold text-gray-800">{t['titulo']}</h1>
                    </div>
                    <div class="language-selector-container">
                        <label for="idioma" class="sr-only">{t['cambiar_idioma']}</label>
                        <select id="idioma" name="idioma" class="p-2 border border-gray-300 rounded-lg text-sm" onchange="this.form.submit()">
                            <option value="Español" {"selected" if idioma == 'Español' else ""}>Español</option>
                            <option value="English" {"selected" if idioma == 'English' else ""}>English</option>
                        </select>
                    </div>
                </div>
                
                {f'<p class="text-center text-lg text-red-700 font-bold mb-6 bg-red-100 p-3 rounded">{t["error_excel"]}</p>' if t["error_excel"] else ''}
                
                <p class="text-center text-sm mb-6 {precio_oro_color}">{precio_oro_status}</p>

                <h2 class="text-xl font-semibold pt-4 text-gray-700">{t['cliente_datos']}</h2>
                <div class="bg-gray-100 p-4 rounded-lg space-y-4 mb-6">
                    <div>
                        <label for="nombre_cliente" class="block text-sm font-medium text-gray-700 mb-1">{t['nombre']}</label>
                        <input type="text" id="nombre_cliente" name="nombre_cliente" value="{nombre_cliente}" 
                               class="w-full p-2 border border-gray-300 rounded-lg" required>
                    </div>
                    <div>
                        <label for="email_cliente" class="block text-sm font-medium text-gray-700 mb-1">{t['email']}</label>
                        <input type="email" id="email_cliente" name="email_cliente" value="{email_cliente}"
                               class="w-full p-2 border border-gray-300 rounded-lg">
                    </div>
                </div>
                
                <h2 class="text-xl font-semibold pt-4 text-pink-700">Modelo {t['dama']}</h2>
                <div class="bg-pink-50 p-4 rounded-lg space-y-3">
                    <p class="text-sm font-medium text-gray-700">
                        Modelo: <span class="font-bold text-gray-900">{modelo_dama}</span>
                        {' (' + metal_dama + ')' if metal_dama else ''}
                    </p>
                    {selectores_dama}
                    <span class="text-xs text-gray-500 block pt-2">
                        {'Monto Estimado: $' + f'{monto_dama:,.2f}' + ' USD (Peso: ' + f'{peso_dama:,.2f}' + 'g, Adicional: $' + f'{cost_adicional_dama:,.2f}' + ')' if monto_dama > 0 else 'Seleccione todos los detalles para calcular.'}
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
                        {'Monto Estimado: $' + f'{monto_cab:,.2f}' + ' USD (Peso: ' + f'{peso_cab:,.2f}' + 'g, Adicional: $' + f'{cost_adicional_cab:,.2f}' + ')' if monto_cab > 0 else 'Seleccione todos los detalles para calcular.'}
                    </span>
                </div>

                <a href="{url_for('catalogo')}" class="inline-block px-4 py-2 text-white bg-indigo-600 rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 text-sm font-semibold">
                    {t['catalogo_btn']} (Cambiar Modelo/Metal)
                </a>

                <div class="pt-6">
                    <label class="block text-lg font-bold text-gray-800 mb-2">{t['monto']}</label>
                    <p class="text-4xl font-extrabold text-indigo-600">${monto_total_redondeado:,.2f} USD</p>
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
    """Ruta del catálogo: selecciona solo Modelo y Metal."""
    df, _ = cargar_datos()
    
    # Manejo de Idioma y Textos
    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    
    t = {
        "titulo": "Catálogo de Anillos de Boda" if es else "Wedding Ring Catalog",
        "volver": "Volver al Formulario" if es else "Back to Form",
        "dama": "Dama" if es else "Lady",
        "caballero": "Caballero" if es else "Gentleman",
        "metal": "Metal" if es else "Metal",
        "seleccion_actual": "Selección Actual" if es else "Current Selection",
        "error_excel": "ERROR CRÍTICO: No se pudo cargar el Excel. Revisar log." if df.empty else ""
    }

    # Recuperar selecciones actuales para las etiquetas y el resaltado
    modelo_dama = session.get("modelo_dama", "")
    metal_dama = session.get("metal_dama", "")
    modelo_cab = session.get("modelo_cab", "")
    metal_cab = session.get("metal_cab", "")
    
    # 1. Manejo del POST
    if request.method == "POST":
        
        # Si se pulsa el botón de volver, redirigimos inmediatamente
        if request.form.get("volver_btn") == "true":
            # Redirige al formulario principal con fresh_selection para forzar la autoselección de ancho/talla
            return redirect(url_for("formulario", fresh_selection=True)) 

        # Si se pulsa un botón de selección (Dama o Caballero)
        seleccion = request.form.get("seleccion")
        tipo = request.form.get("tipo")
        
        if seleccion and tipo:
            try:
                modelo, metal = seleccion.split(";")
                
                # Guardamos los nuevos valores en la sesión
                session[f"modelo_{tipo}"] = modelo.strip().upper()
                session[f"metal_{tipo}"] = metal.strip().upper()
                
                # Limpiamos ancho/talla para forzar autoselección al regresar
                session[f"ancho_{tipo}"] = ""
                session[f"talla_{tipo}"] = ""
                
                # Permanece en el catálogo, forzando un GET para recargar el estado visual (resaltado)
                return redirect(url_for("catalogo")) 
            except ValueError:
                logging.error("Error en el formato de selección del catálogo.")

    # --- LÓGICA DE AGRUPACIÓN (Tarjeta por Variante Única: Modelo + Metal) ---
    if df.empty:
         html_error = f"""<!DOCTYPE html><html><body><div style="text-align: center; padding: 50px;"><h1 style="color: red;">Error de Carga de Datos</h1><p>{t['error_excel']}</p><a href="{url_for('formulario')}">Volver al Formulario</a></div></body></html>"""
         return render_template_string(html_error)

    # Filtrar solo las columnas necesarias para el catálogo
    df_catalogo = df[["NAME", "METAL", "RUTA FOTO"]].dropna(subset=["NAME", "METAL", "RUTA FOTO"])
    # Obtener filas únicas
    variantes_unicas = df_catalogo.drop_duplicates(subset=['NAME', 'METAL'])
    
    catalogo_items = []
    for _, fila in variantes_unicas.iterrows():
        modelo = str(fila["NAME"]).strip().upper()
        metal = str(fila["METAL"]).strip().upper()
        ruta_foto = str(fila["RUTA FOTO"]).strip()
        
        catalogo_items.append({
            "modelo": modelo,
            "metal": metal,
            # Asegurar que el nombre del archivo se extraiga y limpie correctamente
            "nombre_foto": obtener_nombre_archivo_imagen(ruta_foto) 
        })

    # Etiquetas de Selección Actual en el Catálogo
    etiquetas_catalogo = ""
    is_something_selected = (modelo_dama and modelo_dama != DEFAULT_SELECTION_TEXT) or (modelo_cab and modelo_cab != DEFAULT_SELECTION_TEXT)
    
    if is_something_selected:
        etiquetas_catalogo += f"""
        <div class="p-4 rounded-lg bg-indigo-50 mb-6">
            <h2 class="text-xl font-semibold text-gray-700 mb-3">{t['seleccion_actual']}</h2>
            <div class="flex flex-wrap gap-3">
        """
        if modelo_dama and modelo_dama != DEFAULT_SELECTION_TEXT:
            etiquetas_catalogo += f"""
            <span class="bg-pink-200 text-pink-900 text-sm font-medium px-3 py-1 rounded-full">
                {t['dama']}: {modelo_dama} ({metal_dama})
            </span>
            """
        if modelo_cab and modelo_cab != DEFAULT_SELECTION_TEXT:
            etiquetas_catalogo += f"""
            <span class="bg-blue-200 text-blue-900 text-sm font-medium px-3 py-1 rounded-full">
                {t['caballero']}: {modelo_cab} ({metal_cab})
            </span>
            """
        etiquetas_catalogo += "</div></div>"

    logo_url = url_for('static', filename='logo.png')
    
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
            .card {{ background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); transition: border-color 0.3s; }}
            .header-container {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 24px;
            }}
            .logo-img {{
                max-height: 50px;
                width: auto;
                min-width: 50px;
                margin-right: 15px;
            }}
            .title-content {{
                flex-grow: 1;
                text-align: center;
            }}
            .language-selector-container {{
                min-width: 100px;
                text-align: right;
            }}
        </style>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            
            <form method="POST" action="{url_for('catalogo')}">

                <div class="header-container">
                    <img src="{logo_url}" alt="Logo" class="logo-img" onerror="this.style.display='none';" />
                    <div class="title-content">
                        <h1 class="text-3xl font-extrabold text-gray-800">{t['titulo']}</h1>
                    </div>
                    <div class="language-selector-container">
                        <button type="submit" name="volver_btn" value="true"
                                class="px-4 py-2 bg-indigo-600 text-white font-bold rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 text-sm">
                            {t['volver']}
                        </button>
                    </div>
                </div>
                
                {f'<p class="text-center text-lg text-red-700 font-bold mb-6 bg-red-100 p-3 rounded">{t["error_excel"]}</p>' if t["error_excel"] else ''}

                {etiquetas_catalogo}
                
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
    """
    
    for item in catalogo_items:
        modelo = item['modelo']
        metal = item['metal']
        nombre_foto = item['nombre_foto']
        # Uso de url_for para construir la ruta estática
        ruta_web_foto = url_for('static', filename=nombre_foto) 
        valor_seleccion = f"{modelo};{metal}"
        
        # Lógica para aplicar el resaltado
        borde_clase = "border border-gray-200"
        etiqueta = ""
        
        is_dama_selected = modelo == modelo_dama and metal == metal_dama
        is_cab_selected = modelo == modelo_cab and metal == metal_cab
        
        if is_dama_selected or is_cab_selected:
            borde_clase = "border-4 border-green-500"
            etiqueta_texto = ""
            if is_dama_selected:
                etiqueta_texto += f" {t['dama']}"
            if is_cab_selected:
                etiqueta_texto += f" / {t['caballero']}" if is_dama_selected else f" {t['caballero']}"
                
            etiqueta = f"""
                <span class="absolute top-2 right-2 bg-green-500 text-white text-xs font-bold px-2 py-1 rounded-full shadow-lg">
                    Seleccionado{etiqueta_texto}
                </span>
            """

        html_catalogo += f"""
                    <div class="card p-4 flex flex-col items-center text-center relative {borde_clase}">
                        {etiqueta}
                        <img src="{ruta_web_foto}" alt="{modelo} - {metal}" 
                             class="w-full h-auto max-h-48 object-contain rounded-lg mb-3" 
                             onerror="this.onerror=null;this.src='{url_for('static', filename='placeholder.png')}';"
                        >
                        <p class="text-xl font-bold text-gray-900 mb-1">{modelo}</p>
                        <p class="text-md font-semibold text-indigo-700 mb-4">{t['metal']}: {metal}</p>

                        <div class="mt-2 space-y-3 w-full border-t pt-3">
                            <button type="submit" name="seleccion" value="{valor_seleccion}" 
                                    class="select-btn inline-block w-full px-3 py-1.5 text-white bg-pink-500 rounded text-sm font-semibold hover:bg-pink-600 transition duration-150 text-center mb-1"
                                    onclick="document.getElementById('tipo_input').value='dama';">
                                Seleccionar {t['dama']}
                            </button>
                            
                            <button type="submit" name="seleccion" value="{valor_seleccion}" 
                                    class="select-btn inline-block w-full px-3 py-1.5 text-white bg-blue-500 rounded text-sm font-semibold hover:bg-blue-600 transition duration-150 text-center"
                                    onclick="document.getElementById('tipo_input').value='cab';">
                                Seleccionar {t['caballero']}
                            </button>
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
    
    # Crea un directorio 'static' y añade 'logo.png' y 'placeholder.png'
    os.makedirs('static', exist_ok=True) 
    
    # NOTA IMPORTANTE: Para que las fotos funcionen, los archivos de imagen (.png, .jpg, etc.) 
    # DEBEN estar físicamente dentro de la carpeta 'static' y tener el mismo nombre (limpio)
    # que se extrae de la columna "RUTA FOTO" del Excel (espacios deben ser remplazados por '_').
    
    app.run(debug=True)