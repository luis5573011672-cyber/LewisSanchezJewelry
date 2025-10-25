import requests
import os
import pandas as pd
from flask import Flask, request, render_template_string, session, redirect, url_for
import logging
import math
from urllib.parse import unquote
from typing import Tuple, List, Dict

# Configuración de Logging
logging.basicConfig(level=logging.INFO)

# --- CONFIGURACIÓN GLOBAL ---
app = Flask(__name__)
# Es CRUCIAL que la clave secreta se establezca para que las sesiones funcionen.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "una_clave_secreta_fuerte_aqui_para_testing") 

EXCEL_PATH = "Formulario Catalogo.xlsm" 
# Factores de pureza (Kilates / 24)
FACTOR_KILATES = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}
DEFAULT_GOLD_PRICE = 5600.00 # USD por Onza (Valor por defecto/fallback)

# Variables globales para los DataFrames (Caché)
df_global = pd.DataFrame()
df_adicional_global = pd.DataFrame()
costos_diamantes_global = {} 

# --------------------- FUNCIONES DE UTILIDAD ---------------------

def obtener_precio_oro() -> Tuple[float, str]:
    """Obtiene el precio actual del oro (XAU/USD) por onza o usa un fallback."""
    API_KEY = "goldapi-4g9e8p719mgvhodho-io" 
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": API_KEY, "Content-Type": "application/json"}
    
    try:
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
    Calcula el valor del gramo de la aleación y el monto total de oro de la joya.
    """
    if valor_onza <= 0 or peso_gramos <= 0 or pureza_factor <= 0:
        return 0.0, 0.0
    
    valor_gramo_puro = valor_onza / 31.1035 # Onza Troy (31.1035 gramos)
    valor_gramo_aleacion = valor_gramo_puro * pureza_factor
    monto_total = valor_gramo_aleacion * peso_gramos
    
    return valor_gramo_aleacion, monto_total

def calcular_monto_aproximado(monto_bruto: float) -> float:
    """Aproxima (redondea hacia arriba) el monto al múltiplo de 10 más cercano."""
    if monto_bruto <= 0:
        return 0.0
    aproximado = math.ceil(monto_bruto / 10.0) * 10.0
    return aproximado

def safe_float(value) -> float:
    """Intenta convertir un valor a float de manera segura, retornando 0.0 en caso de error."""
    try:
        if pd.notna(value) and str(value).strip():
            return float(str(value).strip())
    except:
        pass
    return 0.0

def cargar_datos() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    """Carga los DataFrames con manejo de caché y limpieza de columnas, y extrae costos de diamante."""
    global df_global, df_adicional_global, costos_diamantes_global
    
    # 1. Usar caché si ya está cargado para prevenir re-lecturas (ayuda con 502)
    if not df_global.empty and not df_adicional_global.empty and costos_diamantes_global:
        return df_global, df_adicional_global, costos_diamantes_global

    costos_diamantes = {"laboratorio": 0.0, "natural": 0.0}
    try:
        # 2. Cargar la hoja WEDDING BANDS
        df_raw = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=None)
        new_columns_df = df_raw.iloc[1].astype(str).str.strip().str.upper()
        df = df_raw.iloc[2:].copy()
        df.columns = new_columns_df
        if 'WIDTH' in df.columns:
            df.rename(columns={'WIDTH': 'ANCHO'}, inplace=True)
            
        # 3. Cargar la hoja SIZE (usamos header=None para acceder por índice numérico si es necesario)
        df_adicional_raw = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl", header=None)
        # Identificar encabezados para el df procesado
        df_adicional_headers = df_adicional_raw.iloc[0].astype(str).str.strip().str.upper()
        df_adicional = df_adicional_raw.iloc[1:].copy()
        df_adicional.columns = df_adicional_headers
        
        # 4. Extracción de Costos de Diamantes (Laboratorio y Natural)
        
        # Costo Laboratorio: Columna MONTO F3 / MONTO. Asumimos Fila 2 de datos (índice 1 del df_adicional procesado)
        if "MONTO F3" in df_adicional_headers:
             df_adicional.rename(columns={'MONTO F3': 'MONTO'}, inplace=True)
        
        monto_laboratorio_raw = None
        if "MONTO" in df_adicional.columns and len(df_adicional) > 1:
            monto_laboratorio_raw = df_adicional["MONTO"].iloc[1]
            
        # Costo Natural: Columna F (índice 5), Fila 2 (índice 2 del df_adicional_raw, o índice 1 del df_adicional)
        # Usaremos el índice numérico [2, 5] en df_adicional_raw para mayor seguridad (Fila 3, Columna F del Excel)
        monto_natural_raw = None
        if len(df_adicional_raw) > 2 and len(df_adicional_raw.columns) > 5:
            # Fila 3 del Excel (índice 2 en pandas), Columna F del Excel (índice 5 en pandas)
            monto_natural_raw = df_adicional_raw.iloc[2, 5] 
        
        costos_diamantes["laboratorio"] = safe_float(monto_laboratorio_raw)
        costos_diamantes["natural"] = safe_float(monto_natural_raw)
        
        # 5. Limpieza y estandarización
        cols_to_strip = ["NAME", "METAL", "RUTA FOTO", "PESO", "GENERO", "CT", "ANCHO", "CARAT"] 
        for col in cols_to_strip:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        if "ANCHO" in df.columns:
            df["ANCHO"] = df["ANCHO"].str.replace('MM', '', regex=False).str.strip()
        
        df_global = df
        df_adicional_global = df_adicional
        costos_diamantes_global = costos_diamantes
        
        return df, df_adicional, costos_diamantes
        
    except Exception as e:
        # Esto ayuda a diagnosticar el 502 si es por un error de Python
        logging.error(f"Error CRÍTICO al leer el archivo Excel: {e}") 
        return pd.DataFrame(), pd.DataFrame(), costos_diamantes


def obtener_peso_y_costo(df_adicional_local: pd.DataFrame, modelo: str, metal: str, ancho: str, kilates: str, talla: str, genero: str, select_text: str) -> Tuple[float, float, float, float]: 
    """
    Busca peso BASE, costos fijo/adicional (por talla) y CT.
    """
    
    global df_global 
    
    if df_global.empty or not all([modelo, metal, ancho, kilates, talla, genero]) or modelo == select_text:
        return 0.0, 0.0, 0.0, 0.0 
        
    # 1. Buscar el PESO (BASE), COSTO FIJO y CT en df_global (WEDDING BANDS)
    filtro_base = (df_global["NAME"] == modelo) & \
                  (df_global["ANCHO"] == ancho) & \
                  (df_global["METAL"] == metal) & \
                  (df_global["CARAT"] == kilates) & \
                  (df_global["GENERO"] == genero) 
    
    peso = 0.0 
    price_cost = 0.0 
    ct = 0.0 
    
    if not df_global.loc[filtro_base].empty:
        base_fila = df_global.loc[filtro_base].iloc[0]
        peso_raw = base_fila.get("PESO", 0) 
        price_cost_raw = base_fila.get("PRICE COST", 0) 
        ct_raw = base_fila.get("CT", 0) 
        
        peso = safe_float(peso_raw)
        price_cost = safe_float(price_cost_raw)
        ct = safe_float(ct_raw)

    # 2. Buscar el COSTO ADICIONAL por TALLA en df_adicional_local (Hoja SIZE)
    cost_adicional = 0.0
    if not df_adicional_local.empty and "SIZE" in df_adicional_local.columns and "ADICIONAL" in df_adicional_local.columns:
        
        if "SIZE_STRIP" not in df_adicional_local.columns:
            df_adicional_local["SIZE_STRIP"] = df_adicional_local["SIZE"].astype(str).str.strip()
            
        filtro_adicional = (df_adicional_local["SIZE_STRIP"] == talla) 
        
        if not df_adicional_local.loc[filtro_adicional].empty:
            adicional_fila = df_adicional_local.loc[filtro_adicional].iloc[0]
            cost_adicional_raw = adicional_fila.get("ADICIONAL") 
            cost_adicional = safe_float(cost_adicional_raw)

    return peso, price_cost, cost_adicional, ct 

# --------------------- RUTAS FLASK ---------------------

@app.route("/", methods=["GET", "POST"])
def formulario():
    """Ruta principal: maneja datos de cliente, selección de Kilates, Ancho, Talla y cálculo."""
    
    df, df_adicional, costos_diamantes = cargar_datos()
    precio_onza, status = obtener_precio_oro()
    monto_total_bruto = 0.0
    
    # Costos por tipo de diamante
    monto_f3_diamante_laboratorio = costos_diamantes.get("laboratorio", 0.0)
    monto_f3_diamante_natural = costos_diamantes.get("natural", 0.0)
    
    # --- Carga de Idioma y Textos ---
    idioma = request.form.get("idioma", session.get("idioma", "Español"))
    session["idioma"] = idioma 
    es = idioma == "Español"

    t = {
        "titulo": "PRESUPUESTO" if es else "ESTIMATE",
        "seleccionar": "Seleccione una opción de catálogo" if es else "Select a catalog option",
        "kilates": "Kilates (Carat)",
        "ancho": "Ancho (mm)" if es else "Width (mm)",
        "talla": "Talla (Size)",
        "diamante": "Tipo de Diamante" if es else "Diamond Type",
        "laboratorio": "Laboratorio",
        "natural": "Natural",
        "guardar": "Guardar" if es else "Save",
        "monto": "Monto total del presupuesto" if es else "Total estimate amount",
        "dama": "Dama" if es else "Lady",
        "cab": "Caballero" if es else "Gentleman",
        "catalogo_btn": "Abrir Catálogo" if es else "Open Catalog",
        "cliente_datos": "Datos del Cliente" if es else "Client Details",
        "nombre": "Nombre del Cliente" if es else "Client Name",
        "email": "Email de Contacto" if es else "Contact Email",
        "cambiar_idioma": "Cambiar Idioma" if es else "Change Language"
    }

    # --- Carga/Persistencia de Variables ---
    nombre_cliente = request.form.get("nombre_cliente", session.get("nombre_cliente", "")) 
    email_cliente = request.form.get("email_cliente", session.get("email_cliente", "")) 
    kilates_dama = request.form.get("kilates_dama", session.get("kilates_dama", "14"))
    ancho_dama = request.form.get("ancho_dama", session.get("ancho_dama", ""))
    talla_dama = request.form.get("talla_dama", session.get("talla_dama", ""))
    tipo_diamante_dama = request.form.get("tipo_diamante_dama", session.get("tipo_diamante_dama", "Laboratorio"))
    modelo_dama = session.get("modelo_dama", t['seleccionar']).upper()
    metal_dama = session.get("metal_dama", "").upper()
    
    kilates_cab = request.form.get("kilates_cab", session.get("kilates_cab", "14"))
    ancho_cab = request.form.get("ancho_cab", session.get("ancho_cab", ""))
    talla_cab = request.form.get("talla_cab", session.get("talla_cab", ""))
    tipo_diamante_cab = request.form.get("tipo_diamante_cab", session.get("tipo_diamante_cab", "Laboratorio"))
    modelo_cab = session.get("modelo_cab", t['seleccionar']).upper()
    metal_cab = session.get("metal_cab", "").upper()

    session["nombre_cliente"] = nombre_cliente 
    session["email_cliente"] = email_cliente 
    session["kilates_dama"] = kilates_dama
    session["ancho_dama"] = ancho_dama
    session["talla_dama"] = talla_dama
    session["tipo_diamante_dama"] = tipo_diamante_dama
    session["kilates_cab"] = kilates_cab
    session["ancho_cab"] = ancho_cab
    session["talla_cab"] = talla_cab
    session["tipo_diamante_cab"] = tipo_diamante_cab
    
    if request.method == "POST" and "idioma" in request.form and "volver_btn" not in request.form:
         return redirect(url_for("formulario"))
        
    fresh_selection = request.args.get("fresh_selection")
    if fresh_selection:
        session["ancho_dama"] = "" 
        session["talla_dama"] = ""
        session["ancho_cab"] = ""
        session["talla_cab"] = ""
        ancho_dama = ""
        talla_dama = ""
        ancho_cab = ""
        talla_cab = ""

    # --- Opciones disponibles y Autoselección ---
    def get_options(modelo, metal):
        if df.empty or df_adicional.empty or modelo == t['seleccionar'].upper() or not metal:
            return [], []
        
        filtro_base_options = (df["NAME"] == modelo) & (df["METAL"] == metal)
        
        def sort_numeric_key(value_str):
            try: return float(value_str)
            except ValueError: return float('inf') 
                
        anchos_raw = df.loc[filtro_base_options, "ANCHO"].astype(str).str.strip().unique().tolist() if "ANCHO" in df.columns else []
        anchos = sorted(anchos_raw, key=sort_numeric_key)
        
        tallas_raw = df_adicional["SIZE"].astype(str).str.strip().unique().tolist() if "SIZE" in df_adicional.columns else []
        tallas = sorted(tallas_raw, key=sort_numeric_key)

        return anchos, tallas

    anchos_d, tallas_d = get_options(modelo_dama, metal_dama)
    anchos_c, tallas_c = get_options(modelo_cab, metal_cab)

    def auto_select(tipo, modelo, anchos, tallas):
        nonlocal ancho_dama, talla_dama, ancho_cab, talla_cab
        if modelo != t['seleccionar'].upper():
            if tipo == "dama":
                if not ancho_dama and anchos:
                    ancho_dama = anchos[0]
                    session["ancho_dama"] = ancho_dama 
                if not talla_dama and tallas:
                    talla_dama = tallas[0]
                    session["talla_dama"] = talla_dama 
            elif tipo == "cab":
                if not ancho_cab and anchos:
                    ancho_cab = anchos[0]
                    session["ancho_cab"] = ancho_cab 
                if not talla_cab and tallas:
                    talla_cab = tallas[0]
                    session["talla_cab"] = talla_cab 

    auto_select("dama", modelo_dama, anchos_d, tallas_d)
    auto_select("cab", modelo_cab, anchos_c, tallas_c) 

    # --- 2. Cálculos (Aplicando Tipo de Diamante) ---
    
    # --- Dama ---
    peso_base_dama, cost_fijo_dama, cost_adicional_dama, ct_dama = obtener_peso_y_costo(df_adicional, modelo_dama, metal_dama, ancho_dama, kilates_dama, talla_dama, "DAMA", t['seleccionar'].upper())
    monto_dama = 0.0
    monto_diamantes_dama = 0.0 
    costo_diamante_dama_final = 0.0

    if peso_base_dama > 0 and precio_onza is not None and kilates_dama in FACTOR_KILATES:
        
        factor_pureza_dama = FACTOR_KILATES.get(kilates_dama, 0.0)
        
        if tipo_diamante_dama == "Natural":
            costo_diamante_dama_final = monto_f3_diamante_natural
        else:
            costo_diamante_dama_final = monto_f3_diamante_laboratorio

        _, monto_oro_dama = calcular_valor_gramo(precio_onza, factor_pureza_dama, peso_base_dama)
        
        if ct_dama > 0 and costo_diamante_dama_final > 0:
            monto_diamantes_dama = ct_dama * costo_diamante_dama_final
        else:
            monto_diamantes_dama = 0.0

        monto_dama = monto_oro_dama + cost_fijo_dama + cost_adicional_dama + monto_diamantes_dama 
        monto_total_bruto += monto_dama

    # --- Caballero ---
    peso_base_cab, cost_fijo_cab, cost_adicional_cab, ct_cab = obtener_peso_y_costo(df_adicional, modelo_cab, metal_cab, ancho_cab, kilates_cab, talla_cab, "CABALLERO", t['seleccionar'].upper())
    monto_cab = 0.0
    monto_diamantes_cab = 0.0 
    costo_diamante_cab_final = 0.0
    
    if peso_base_cab > 0 and precio_onza is not None and kilates_cab in FACTOR_KILATES:
        
        factor_pureza_cab = FACTOR_KILATES.get(kilates_cab, 0.0)

        if tipo_diamante_cab == "Natural":
            costo_diamante_cab_final = monto_f3_diamante_natural
        else:
            costo_diamante_cab_final = monto_f3_diamante_laboratorio
        
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, factor_pureza_cab, peso_base_cab)
        
        if ct_cab > 0 and costo_diamante_cab_final > 0:
            monto_diamantes_cab = ct_cab * costo_diamante_cab_final
        else:
            monto_diamantes_cab = 0.0

        monto_cab = monto_oro_cab + cost_fijo_cab + cost_adicional_cab + monto_diamantes_cab 
        monto_total_bruto += monto_cab
        
    monto_total_aprox = calcular_monto_aproximado(monto_total_bruto)
    
    # Detalle de cálculo para mostrar en la interfaz
    detalle_dama = (
        f' (Peso: {peso_base_dama:,.2f}g ({kilates_dama}K), '
        f'Add: ${cost_adicional_dama:,.2f}, CT: {ct_dama:,.3f}, '
        f'Diamante: {tipo_diamante_dama}, Costo/CT: ${costo_diamante_dama_final:,.2f}, '
        f'Subtotal Diamantes: ${monto_diamantes_dama:,.2f})'
    )
        
    detalle_cab = (
        f' (Peso: {peso_base_cab:,.2f}g ({kilates_cab}K), '
        f'Add: ${cost_adicional_cab:,.2f}, CT: {ct_cab:,.3f}, '
        f'Diamante: {tipo_diamante_cab}, Costo/CT: ${costo_diamante_cab_final:,.2f}, '
        f'Subtotal Diamantes: ${monto_diamantes_cab:,.2f})'
    )
    
    # --------------------- Generación del HTML para el Formulario ---------------------
        
    def generate_selectors(tipo, modelo, metal, kilates_actual, anchos, tallas, ancho_actual, talla_actual, tipo_diamante_actual):
        kilates_opciones = sorted(FACTOR_KILATES.keys(), key=int, reverse=True)
        diamante_opciones = ["Laboratorio", "Natural"]
        
        kilates_selector = f"""
            <div class="w-full md:w-1/4">
                <label for="kilates_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['kilates']}</label>
                <select id="kilates_{tipo}" name="kilates_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{k}" {"selected" if k == kilates_actual else ""}>{k}K</option>' for k in kilates_opciones])}
                </select>
            </div>
        """

        diamante_selector = f"""
            <div class="w-full md:w-1/4">
                <label for="tipo_diamante_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['diamante']}</label>
                <select id="tipo_diamante_{tipo}" name="tipo_diamante_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{d}" {"selected" if d == tipo_diamante_actual else ""}>{t[d.lower()]}</option>' for d in diamante_opciones])}
                </select>
            </div>
        """
        
        if modelo == t['seleccionar'].upper() or not metal:
            warning_msg = f'<p class="text-red-500 pt-3">Seleccione un modelo y metal en el Catálogo para habilitar opciones.</p>'
            return f"""
                <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
                    {kilates_selector}
                    {diamante_selector}
                </div>
                {warning_msg}
            """

        if not anchos or not tallas:
            html_ancho_talla = f'<div class="w-full md:w-1/2"><p class="text-red-500 pt-3">No hay opciones de Ancho/Talla disponibles para esta combinación de Metal.</p></div>'
            return f"""
                <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
                    {kilates_selector}
                    {diamante_selector}
                </div>
                <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
                    {html_ancho_talla}
                </div>
            """


        html = f"""
        <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
            {kilates_selector}
            <div class="w-full md:w-1/4">
                <label for="ancho_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['ancho']}</label>
                <select id="ancho_{tipo}" name="ancho_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{a}" {"selected" if str(a) == str(ancho_actual) else ""}>{a}</option>' for a in anchos])}
                </select>
            </div>
            <div class="w-full md:w-1/4">
                <label for="talla_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['talla']}</label>
                <select id="talla_{tipo}" name="talla_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{s}" {"selected" if str(s) == str(talla_actual) else ""}>{s}</option>' for s in tallas])}
                </select>
            </div>
            {diamante_selector}
        </div>
        """
        return html

    selectores_dama = generate_selectors("dama", modelo_dama, metal_dama, kilates_dama, anchos_d, tallas_d, ancho_dama, talla_dama, tipo_diamante_dama)
    selectores_cab = generate_selectors("cab", modelo_cab, metal_cab, kilates_cab, anchos_c, tallas_c, ancho_cab, talla_cab, tipo_diamante_cab)
    
    precio_oro_status = f"Precio Oro Onza: ${precio_onza:,.2f} USD ({status.upper()})"
    precio_oro_color = "text-green-600 font-medium" if status == "live" else "text-yellow-700 font-bold bg-yellow-100 p-2 rounded"
    logo_url = url_for('static', filename='logo.png')
    
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
            .header-content {{ 
                display: flex; 
                align-items: center; 
                justify-content: space-between; 
                width: 100%;
                margin-bottom: 1rem;
            }}
            .title-group {{
                display: flex;
                align-items: center;
                flex-grow: 1; 
            }}
            .logo-img {{ 
                height: 60px; 
                margin-right: 15px; 
            }}
            @media (max-width: 640px) {{
                .logo-img {{ height: 40px; }}
            }}
            h1 {{ 
                flex-grow: 1; 
                text-align: center; 
                margin: 0; 
            }} 
            .language-selector-container {{
                min-width: 120px; 
                text-align: right;
            }}
        </style>
    </head>
    <body class="p-4 md:p-8 flex justify-center items-start min-h-screen">
        <div class="w-full max-w-4xl card p-6 md:p-10 mt-6">
            
            <form method="POST" action="/" class="space-y-4"> 
                <div class="header-content">
                    <img src="{url_for('static', filename='logo.png')}" alt="Logo" class="logo-img" onerror="this.style.display='none';" />
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
                        {'Monto Estimado BRUTO: $' + f'{monto_dama:,.2f}' + ' USD' + detalle_dama if monto_dama > 0 or ct_dama > 0 else 'Seleccione todos los detalles para calcular.'}
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
                        {'Monto Estimado BRUTO: $' + f'{monto_cab:,.2f}' + ' USD' + detalle_cab if monto_cab > 0 or ct_cab > 0 else 'Seleccione todos los detalles para calcular.'}
                    </span>
                </div>

                <a href="{url_for('catalogo')}" class="inline-block px-4 py-2 text-white bg-indigo-600 rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 text-sm font-semibold">
                    {t['catalogo_btn']} (Cambiar Modelo/Metal)
                </a>

                <div class="pt-6">
                    <label class="block text-lg font-bold text-gray-800 mb-2">{t['monto']}</label>
                    <p class="text-4xl font-extrabold text-indigo-600">${monto_total_aprox:,.2f} USD</p>
                </div>
                
                <div class="pt-6">
                    <button type="submit" class="w-full px-6 py-3 bg-green-600 text-white font-bold rounded-lg shadow-lg hover:bg-green-700 transition duration-150 focus:outline-none focus:ring-4 focus:ring-green-500 focus:ring-opacity-50">
                        {t['guardar']} (Aplicar Cambios y Guardar)
                    </button>
                </div>
            </form> 
        </div>
        
        <script>
            // Lógica de guardado en localStorage (Mantener)
            const nombreInput = document.getElementById('nombre_cliente');
            const emailInput = document.getElementById('email_cliente');
            document.addEventListener('DOMContentLoaded', () => {{
                if (!nombreInput.value && localStorage.getItem('nombre_cliente')) {{
                    nombreInput.value = localStorage.getItem('nombre_cliente');
                }}
                if (!emailInput.value && localStorage.getItem('email_cliente')) {{
                    emailInput.value = localStorage.getItem('email_cliente');
                }}
            }});
            nombreInput.addEventListener('input', (e) => {{
                localStorage.setItem('nombre_cliente', e.target.value);
            }});
            emailInput.addEventListener('input', (e) => {{
                localStorage.setItem('email_cliente', e.target.value);
            }});
        </script>
    </body>
    </html>
    """
    return render_template_string(html_form)

# ------------------------------------------------------------------------------------------------

@app.route("/catalogo", methods=["GET", "POST"])
def catalogo():
    """Ruta del catálogo: selecciona Modelo y Metal."""
    # Usamos try/except para cargar solo el DataFrame si es posible, sin fallar si el costo de diamante falla
    try:
        df, _, _ = cargar_datos() 
    except Exception as e:
        logging.error(f"Error cargando datos en catálogo: {e}")
        df = pd.DataFrame()
        
    mensaje_exito = None
    
    if request.method == "POST":
        seleccion = request.form.get("seleccion")
        tipo = request.form.get("tipo")
        
        if request.form.get("volver_btn") == "true":
            return redirect(url_for("formulario", fresh_selection=True))
        
        if seleccion and tipo:
            try:
                modelo, metal = seleccion.split(";")
                session[f"modelo_{tipo}"] = modelo.strip().upper()
                session[f"metal_{tipo}"] = metal.strip().upper()
                session[f"ancho_{tipo}"] = ""
                session[f"talla_{tipo}"] = ""
                
                tipo_display = "Dama" if tipo == "dama" else "Caballero"
                mensaje_exito = f"✅ ¡Modelo **{modelo} ({metal})** para **{tipo_display}** guardado! Seleccione el otro o presione 'Volver al Formulario'."
                
            except ValueError:
                logging.error("Error en el formato de selección del catálogo.")
                mensaje_exito = "❌ Error al procesar la selección."


    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    
    t = {
        "titulo": "Catálogo de Anillos de Boda" if es else "WEDDING RING CATALOG", 
        "volver": "Volver al Formulario" if es else "Back to Form",
        "dama": "Dama" if es else "Lady",
        "caballero": "Caballero" if es else "Gentleman",
        "metal": "Metal" if es else "Metal",
    }
    
    modelo_dama_actual = session.get("modelo_dama", "")
    metal_dama_actual = session.get("metal_dama", "")
    modelo_cab_actual = session.get("modelo_cab", "")
    metal_cab_actual = session.get("metal_cab", "")
    logo_url = url_for('static', filename='logo.png')
    
    if df.empty:
          html_catalogo = f"""
        <!DOCTYPE html>
        <html><body><div style="text-align: center; padding: 50px;">
        <h1 style="color: red;">Error de Carga de Datos</h1>
        <p>No se pudo cargar el archivo Excel o la hoja "WEDDING BANDS" está vacía.</p>
        <p>Asegúrese de que '{EXCEL_PATH}' existe y tiene datos.</p>
        <a href="{url_for('formulario')}">Volver al Formulario</a>
        </div></body></html>
        """
          return render_template_string(html_catalogo)

    df_catalogo = df[["NAME", "METAL", "RUTA FOTO"]].dropna(subset=["NAME", "METAL", "RUTA FOTO"])
    variantes_unicas = df_catalogo.drop_duplicates(subset=['NAME', 'METAL'])
    
    def obtener_nombre_archivo_imagen(ruta_completa: str) -> str:
        if pd.isna(ruta_completa) or not str(ruta_completa).strip():
            return "placeholder.png" 
        ruta_limpia = str(ruta_completa).replace('\\', '/')
        nombre_archivo = os.path.basename(ruta_limpia).strip()
        return unquote(nombre_archivo)
        
    catalogo_items = []
    for _, fila in variantes_unicas.iterrows():
        modelo = str(fila["NAME"]).strip().upper()
        metal = str(fila["METAL"]).strip().upper()
        ruta_foto = str(fila["RUTA FOTO"]).strip()
        
        catalogo_items.append({
            "modelo": modelo,
            "metal": metal,
            "nombre_foto": obtener_nombre_archivo_imagen(ruta_foto)
        })

    html_items = ""
    for item in catalogo_items:
        modelo = item["modelo"]
        metal = item["metal"]
        nombre_foto = item["nombre_foto"]
        ruta_web_foto = url_for('static', filename=nombre_foto)

        borde_clase = ""
        etiqueta = ""
        seleccionado_dama = (modelo == modelo_dama_actual and metal == metal_dama_actual)
        seleccionado_cab = (modelo == modelo_cab_actual and metal == metal_cab_actual)

        if seleccionado_dama and seleccionado_cab:
            borde_clase = "selected-both"
            etiqueta = f'<span class="absolute top-2 left-2 bg-green-500 text-white px-2 py-1 rounded-full text-xs font-bold">Ambos ({t["dama"]}/{t["caballero"]})</span>'
        elif seleccionado_dama:
            borde_clase = "selected-dama"
            etiqueta = f'<span class="absolute top-2 left-2 bg-pink-500 text-white px-2 py-1 rounded-full text-xs font-bold">{t["dama"]}</span>'
        elif seleccionado_cab:
            borde_clase = "selected-cab"
            etiqueta = f'<span class="absolute top-2 left-2 bg-blue-500 text-white px-2 py-1 rounded-full text-xs font-bold">{t["caballero"]}</span>'

        html_items += f"""
        <div class="card p-4 flex flex-col items-center text-center relative {borde_clase}">
            {etiqueta}
            <img src="{ruta_web_foto}" alt="{modelo} - {metal}" 
                 class="w-full h-auto max-h-48 object-contain rounded-lg mb-3" 
                 onerror="this.onerror=null;this.src='{url_for('static', filename='placeholder.png')}';"
            >
            <h2 class="text-lg font-semibold text-gray-800">{modelo}</h2>
            <p class="text-sm text-gray-600">{t['metal']}: {metal}</p>
            <div class="mt-4 flex flex-col space-y-2 w-full">
                <form method="POST" action="{url_for('catalogo')}" class="w-full">
                    <input type="hidden" name="seleccion" value="{modelo};{metal}">
                    <input type="hidden" name="tipo" value="dama">
                    <button type="submit" class="w-full px-3 py-2 text-white bg-pink-600 rounded-lg hover:bg-pink-700 transition duration-150 text-sm font-semibold">
                        Seleccionar {t['dama']}
                    </button>
                </form>
                <form method="POST" action="{url_for('catalogo')}" class="w-full">
                    <input type="hidden" name="seleccion" value="{modelo};{metal}">
                    <input type="hidden" name="tipo" value="cab">
                    <button type="submit" class="w-full px-3 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition duration-150 text-sm font-semibold">
                        Seleccionar {t['caballero']}
                    </button>
                </form>
            </div>
        </div>
        """
    
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
            .card {{ background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); }}
            .title-container {{
                display: flex; 
                align-items: center; 
                justify-content: center;
                margin-bottom: 2rem; 
            }}
            .logo-img {{ 
                height: 60px; 
                margin-right: 15px; 
            }}
            .selected-dama {{ border: 4px solid #EC4899; }} 
            .selected-cab {{ border: 4px solid #3B82F6; }} 
            .selected-both {{ border: 4px solid #10B981; }} 
        </style>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            
            <div class="title-container">
                <img src="{logo_url}" alt="Logo" class="logo-img" onerror="this.style.display='none';" />
                <h1 class="text-3xl font-extrabold text-gray-800">{t['titulo']}</h1>
                <div style="width: 60px; margin-left: 15px;"></div> 
            </div>
            
            {f'<div class="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative mb-6 text-center" role="alert">{mensaje_exito}</div>' if mensaje_exito else ''}

            <form method="POST" action="{url_for('catalogo')}">
                <div class="mb-8 text-center">
                    <input type="hidden" name="volver_btn" value="true">
                    <button type="submit" class="px-6 py-3 bg-indigo-600 text-white font-bold rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 focus:outline-none focus:ring-4 focus:ring-indigo-500 focus:ring-opacity-50">
                        {t['volver']}
                    </button>
                </div>
            </form>
            
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                {html_items}
            </div>
            
            <form method="POST" action="{url_for('catalogo')}">
                <div class="my-8 text-center">
                    <input type="hidden" name="volver_btn" value="true">
                    <button type="submit" class="px-6 py-3 bg-indigo-600 text-white font-bold rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 focus:outline-none focus:ring-4 focus:ring-indigo-500 focus:ring-opacity-50">
                        {t['volver']}
                    </button>
                </div>
            </form>

        </div>
    </body>
    </html>
    """
    return render_template_string(html_catalogo)

if __name__ == "__main__":
    app.run(debug=True)