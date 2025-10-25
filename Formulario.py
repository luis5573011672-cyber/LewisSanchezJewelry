import requests
import os
import pandas as pd
from flask import Flask, request, render_template_string, session, redirect, url_for
import logging
import math
from urllib.parse import unquote
from typing import Tuple, List

# Configuración de Logging
logging.basicConfig(level=logging.INFO)

# --- CONFIGURACIÓN GLOBAL ---
app = Flask(__name__)
# Es CRUCIAL que la clave secreta se establezca para que las sesiones funcionen.
# DEBES CAMBIAR ESTA CLAVE EN PRODUCCIÓN
app.secret_key = os.getenv("FLASK_SECRET_KEY", "una_clave_secreta_fuerte_aqui_para_testing") 

# Asegúrate de que este archivo exista en la misma ubicación que tu script.
EXCEL_PATH = "Formulario Catalogo.xlsm" 
# Factores de pureza (Kilates / 24)
FACTOR_KILATES = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}
DEFAULT_GOLD_PRICE = 5600.00 # USD por Onza (Valor por defecto/fallback)

# Variables globales para los DataFrames (Caché)
df_global = pd.DataFrame()
df_adicional_global = pd.DataFrame()

# --------------------- FUNCIONES DE UTILIDAD ---------------------

def obtener_precio_oro() -> Tuple[float, str]:
    """
    Obtiene el precio actual del oro (XAU/USD) por onza.
    """
    # Usando una API_KEY de ejemplo. Reemplaza con una clave válida en producción.
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
            
        logging.warning("API respondió OK (200), pero el precio era inválido. Usando fallback.")
        return DEFAULT_GOLD_PRICE, "fallback"
        
    except (requests.exceptions.RequestException, Exception) as e:
        logging.error(f"Error al obtener precio del oro: {e}. Usando fallback ({DEFAULT_GOLD_PRICE}).")
        return DEFAULT_GOLD_PRICE, "fallback"

def calcular_valor_gramo(valor_onza: float, pureza_factor: float, peso_gramos: float) -> Tuple[float, float]:
    """
    Calcula el valor del gramo de oro (ajustado por pureza) y el monto total de oro de la joya.
    
    El cálculo es: (Precio Onza / Gramos en Onza) * Pureza * Peso Total
    Esto es el cálculo correcto del valor del oro puro contenido en la aleación.
    """
    if valor_onza <= 0 or peso_gramos <= 0 or pureza_factor <= 0:
        return 0.0, 0.0
    
    # Onza Troy (31.1035 gramos)
    valor_gramo_puro = valor_onza / 31.1035
    valor_gramo_aleacion = valor_gramo_puro * pureza_factor
    monto_total = valor_gramo_aleacion * peso_gramos
    
    return valor_gramo_aleacion, monto_total

def calcular_monto_aproximado(monto_bruto: float) -> float:
    """Aproxima (redondea hacia arriba) el monto al múltiplo de 10 más cercano."""
    if monto_bruto <= 0:
        return 0.0
    
    aproximado = math.ceil(monto_bruto / 10.0) * 10.0
    return aproximado

def cargar_datos() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga los DataFrames con las correcciones de nombres de columna, aplicando caché global.
    """
    global df_global, df_adicional_global
    if not df_global.empty and not df_adicional_global.empty:
        return df_global, df_adicional_global

    try:
        # 1. Cargar la hoja WEDDING BANDS
        df_raw = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=None)
        # La fila de encabezados es la segunda (índice 1)
        new_columns_df = df_raw.iloc[1].astype(str).str.strip().str.upper()
        df = df_raw.iloc[2:].copy()
        df.columns = new_columns_df
        
        if 'WIDTH' in df.columns:
            df.rename(columns={'WIDTH': 'ANCHO'}, inplace=True)
            
        # 2. Cargar la hoja SIZE
        df_adicional_raw = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl", header=None)
        # La fila de encabezados es la primera (índice 0)
        new_columns_adicional = df_adicional_raw.iloc[0].astype(str).str.strip().str.upper()
        df_adicional = df_adicional_raw.iloc[1:].copy()
        df_adicional.columns = new_columns_adicional
        
        # 3. Limpieza de valores clave en WEDDING BANDS
        for col in ["NAME", "METAL", "RUTA FOTO", "ANCHO", "PESO", "PESO_AJUSTADO", "GENERO", "CT"]: 
            if col in df.columns:
                if col == "ANCHO":
                     df[col] = df[col].astype(str).str.strip().str.replace('MM', '', regex=False).str.strip()
                else:
                    df[col] = df[col].astype(str).str.strip()
            
        # 4. Limpieza de columnas clave en SIZE (Añadido MONTO)
        for col_name in ["SIZE", "ADICIONAL", "MONTO F3", "MONTO"]: 
            if col_name in df_adicional.columns:
                df_adicional[col_name] = df_adicional[col_name].astype(str).str.strip()
            # Renombrar MONTO F3 a MONTO si existe, para unificar y buscar el costo del diamante
            if "MONTO F3" in df_adicional.columns and "MONTO" not in df_adicional.columns:
                 df_adicional.rename(columns={'MONTO F3': 'MONTO'}, inplace=True)
        
        df_global = df
        df_adicional_global = df_adicional
        
        return df, df_adicional
        
    except Exception as e:
        logging.error(f"Error CRÍTICO al leer el archivo Excel: {e}") 
        return pd.DataFrame(), pd.DataFrame()
    

def obtener_nombre_archivo_imagen(ruta_completa: str) -> str:
    """
    Extrae solo el nombre del archivo del path.
    """
    if pd.isna(ruta_completa) or not str(ruta_completa).strip():
        return "placeholder.png" 
    
    ruta_limpia = str(ruta_completa).replace('\\', '/')
    nombre_archivo = os.path.basename(ruta_limpia).strip()
    
    nombre_archivo_final = unquote(nombre_archivo)
    
    return nombre_archivo_final

def obtener_peso_y_costo(df_adicional_local: pd.DataFrame, modelo: str, metal: str, ancho: str, talla: str, genero: str, select_text: str) -> Tuple[float, float, float, float]: 
    """
    Busca peso BASE, costos fijo/adicional (por talla) y CT en los DataFrames,
    basado en el modelo seleccionado, metal, ancho y género.
    """
    
    global df_global 
    
    if df_global.empty or not all([modelo, metal, ancho, talla, genero]) or modelo == select_text:
        return 0.0, 0.0, 0.0, 0.0 
        
    # 1. Buscar el PESO (BASE), COSTO FIJO y CT en df_global (WEDDING BANDS)
    filtro_base = (df_global["NAME"] == modelo) & \
                  (df_global["ANCHO"] == ancho) & \
                  (df_global["METAL"] == metal) & \
                  (df_global["GENERO"] == genero) 
    
    peso = 0.0 # Peso BASE del metal (sin ajuste por Kilates aún)
    price_cost = 0.0 # Costo Fijo (PRICE COST)
    ct = 0.0 # Quilataje total del diamante (CT)
    
    if not df_global.loc[filtro_base].empty:
        base_fila = df_global.loc[filtro_base].iloc[0]
        # Obtener los valores crudos
        peso_raw = base_fila.get("PESO", 0) 
        price_cost_raw = base_fila.get("PRICE COST", 0) 
        ct_raw = base_fila.get("CT", 0) 
        
        # Conversión a float
        try: peso = float(peso_raw)
        except: peso = 0.0
        try: price_cost = float(price_cost_raw)
        except: price_cost = 0.0
        try: ct = float(ct_raw) 
        except: ct = 0.0


    # 2. Buscar el COSTO ADICIONAL por TALLA en df_adicional_local (Hoja SIZE)
    cost_adicional = 0.0
    if not df_adicional_local.empty and "SIZE" in df_adicional_local.columns:
        filtro_adicional = (df_adicional_local["SIZE"] == talla) 
        
        if not df_adicional_local.loc[filtro_adicional].empty:
            adicional_fila = df_adicional_local.loc[filtro_adicional].iloc[0]
            cost_adicional_raw = adicional_fila.get("ADICIONAL", 0)
            try: cost_adicional = float(cost_adicional_raw)
            except: cost_adicional = 0.0

    # Devuelve el peso base, costos fijo, adicional por talla, y quilataje de diamante.
    return peso, price_cost, cost_adicional, ct 

# --------------------- RUTAS FLASK ---------------------

@app.route("/", methods=["GET", "POST"])
def formulario():
    """Ruta principal: maneja datos de cliente, selección de Kilates, Ancho, Talla y cálculo."""
    
    df, df_adicional = cargar_datos()
    precio_onza, status = obtener_precio_oro()
    monto_total_bruto = 0.0
    
    # --- 0. Obtener MONTO (Costo unitario por quilate de diamante) de la hoja SIZE (Celda F3 -> Índice 1 de los datos) ---
    monto_f3_diamante = 0.0
    if not df_adicional.empty and "MONTO" in df_adicional.columns: 
        try:
            # Índice 1 corresponde a la tercera fila del Excel (F3) en los datos cargados.
            # Esto asume que el header fue la fila 1 y los datos comienzan en la fila 2.
            monto_f3_raw = df_adicional["MONTO"].iloc[1] if len(df_adicional) > 1 else (df_adicional["MONTO"].iloc[0] if len(df_adicional) > 0 else None)
            if pd.notna(monto_f3_raw) and str(monto_f3_raw).strip():
                 monto_f3_diamante = float(str(monto_f3_raw).strip())
            
        except Exception as e:
            logging.warning(f"Error al obtener/convertir el valor de MONTO (F3). Usando 0.0. Error: {e}")
            monto_f3_diamante = 0.0 

    
    # --- 1. Definición de Textos y Carga de Idioma ---
    
    idioma = request.form.get("idioma", session.get("idioma", "Español"))
    session["idioma"] = idioma 
    es = idioma == "Español"

    t = {
        "titulo": "PRESUPUESTO" if es else "ESTIMATE",
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
        "cambiar_idioma": "Cambiar Idioma" if es else "Change Language"
    }
    
    # --- 3. Manejo de Inicio Fresco o Reseteo Completo (GET sin datos) ---
    is_initial_load = request.method == "GET" and session.get("modelo_dama") is None
    
    if is_initial_load:
        session["nombre_cliente"] = ""
        session["email_cliente"] = ""
        session["modelo_dama"] = t['seleccionar'].upper()
        session["metal_dama"] = ""
        session["modelo_cab"] = t['seleccionar'].upper()
        session["metal_cab"] = ""
        session["kilates_dama"] = "14" 
        session["kilates_cab"] = "14"
        session["ancho_dama"] = ""
        session["talla_dama"] = ""
        session["ancho_cab"] = ""
        session["talla_cab"] = ""
    
    
    # --- 2. Carga de Variables de SESIÓN (GET) o POST (Actualización) ---
    
    nombre_cliente = request.form.get("nombre_cliente", session.get("nombre_cliente", "")) 
    email_cliente = request.form.get("email_cliente", session.get("email_cliente", "")) 
    kilates_dama = request.form.get("kilates_dama", session.get("kilates_dama", "14"))
    ancho_dama = request.form.get("ancho_dama", session.get("ancho_dama", ""))
    talla_dama = request.form.get("talla_dama", session.get("talla_dama", ""))
    modelo_dama = session.get("modelo_dama", t['seleccionar']).upper()
    metal_dama = session.get("metal_dama", "").upper()
    kilates_cab = request.form.get("kilates_cab", session.get("kilates_cab", "14"))
    ancho_cab = request.form.get("ancho_cab", session.get("ancho_cab", ""))
    talla_cab = request.form.get("talla_cab", session.get("talla_cab", ""))
    modelo_cab = session.get("modelo_cab", t['seleccionar']).upper()
    metal_cab = session.get("metal_cab", "").upper()
    
    
    # --- 4. Persistir los valores LEÍDOS del GET/POST en la SESIÓN ---
    session["nombre_cliente"] = nombre_cliente 
    session["email_cliente"] = email_cliente 
    session["kilates_dama"] = kilates_dama
    session["ancho_dama"] = ancho_dama
    session["talla_dama"] = talla_dama
    session["kilates_cab"] = kilates_cab
    session["ancho_cab"] = ancho_cab
    session["talla_cab"] = talla_cab

    # Manejo del cambio de idioma (Redirección para actualizar textos)
    if request.method == "POST" and "idioma" in request.form:
         return redirect(url_for("formulario"))
        
    
    # --- 5. Manejo de Regreso de Catálogo (GET con fresh_selection) ---
    fresh_selection = request.args.get("fresh_selection")
    if fresh_selection:
        ancho_dama = ""
        talla_dama = ""
        ancho_cab = ""
        talla_cab = ""
        session["ancho_dama"] = "" 
        session["talla_dama"] = ""
        session["ancho_cab"] = ""
        session["talla_cab"] = ""


    # --- 6. Opciones disponibles y Forzar selección de Ancho/Talla por defecto ---
    def get_options(modelo):
        if df.empty or df_adicional.empty or modelo == t['seleccionar'].upper():
            return [], []
        
        filtro_ancho = (df["NAME"] == modelo)
        
        def sort_numeric_key(value_str):
            try:
                return float(value_str)
            except ValueError:
                return float('inf') 
                
        anchos_raw = df.loc[filtro_ancho, "ANCHO"].astype(str).str.strip().unique().tolist() if "ANCHO" in df.columns else []
        anchos = sorted(anchos_raw, key=sort_numeric_key)
        
        tallas_raw = df_adicional["SIZE"].astype(str).str.strip().unique().tolist() if "SIZE" in df_adicional.columns else []
        tallas = sorted(tallas_raw, key=sort_numeric_key)

        return anchos, tallas

    anchos_d, tallas_d = get_options(modelo_dama)
    anchos_c, tallas_c = get_options(modelo_cab)

    # Autoselección de Ancho y Talla si están vacíos
    if modelo_dama != t['seleccionar'].upper():
        if not ancho_dama and anchos_d:
            ancho_dama = anchos_d[0]
            session["ancho_dama"] = ancho_dama 
        if not talla_dama and tallas_d:
            talla_dama = tallas_d[0]
            session["talla_dama"] = talla_dama 

    if modelo_cab != t['seleccionar'].upper():
        if not ancho_cab and anchos_c:
            ancho_cab = anchos_c[0]
            session["ancho_cab"] = ancho_cab 
        if not talla_cab and tallas_c:
            talla_cab = tallas_c[0]
            session["talla_cab"] = talla_cab 

    # --- 7. Cálculos (AJUSTE CRUCIAL DEL PESO POR KILATAJE) ---
    
    # --- Dama ---
    # peso_base_dama es el peso obtenido de la fila del catálogo (WEDDING BANDS)
    peso_base_dama, cost_fijo_dama, cost_adicional_dama, ct_dama = obtener_peso_y_costo(df_adicional, modelo_dama, metal_dama, ancho_dama, talla_dama, "DAMA", t['seleccionar'].upper())
    monto_dama = 0.0
    monto_diamantes_dama = 0.0 
    peso_ajustado_dama = 0.0 # Peso ajustado por Kilates (Oro Puro) para visualización

    if peso_base_dama > 0 and precio_onza is not None and kilates_dama in FACTOR_KILATES:
        
        factor_pureza_dama = FACTOR_KILATES.get(kilates_dama, 0.0)
        
        # 1. Determinar el Peso de Oro Puro (para visualización)
        peso_ajustado_dama = peso_base_dama * factor_pureza_dama
        
        # 2. Calcular el valor del oro (usando peso base y factor de pureza)
        _, monto_oro_dama = calcular_valor_gramo(precio_onza, factor_pureza_dama, peso_base_dama)
        
        # 3. Calcular monto de diamantes (CT * MONTO de celda F3)
        if ct_dama > 0 and monto_f3_diamante > 0:
            monto_diamantes_dama = ct_dama * monto_f3_diamante
        else:
            monto_diamantes_dama = 0.0

        # 4. Monto Total Dama = Valor Oro + Costo Fijo + Costo Adicional Talla + Costo Diamantes
        monto_dama = monto_oro_dama + cost_fijo_dama + cost_adicional_dama + monto_diamantes_dama 
        monto_total_bruto += monto_dama

    # --- Caballero ---
    peso_base_cab, cost_fijo_cab, cost_adicional_cab, ct_cab = obtener_peso_y_costo(df_adicional, modelo_cab, metal_cab, ancho_cab, talla_cab, "CABALLERO", t['seleccionar'].upper())
    monto_cab = 0.0
    monto_diamantes_cab = 0.0 
    peso_ajustado_cab = 0.0 # Peso ajustado por Kilates (Oro Puro) para visualización
    
    if peso_base_cab > 0 and precio_onza is not None and kilates_cab in FACTOR_KILATES:
        
        factor_pureza_cab = FACTOR_KILATES.get(kilates_cab, 0.0)
        
        # 1. Determinar el Peso de Oro Puro (para visualización)
        peso_ajustado_cab = peso_base_cab * factor_pureza_cab
        
        # 2. Calcular el valor del oro
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, factor_pureza_cab, peso_base_cab)
        
        # 3. Calcular monto de diamantes
        if ct_cab > 0 and monto_f3_diamante > 0:
            monto_diamantes_cab = ct_cab * monto_f3_diamante
        else:
            monto_diamantes_cab = 0.0

        # 4. Monto Total Caballero
        monto_cab = monto_oro_cab + cost_fijo_cab + cost_adicional_cab + monto_diamantes_cab 
        monto_total_bruto += monto_cab
        
    monto_total_aprox = calcular_monto_aproximado(monto_total_bruto)
    
    # URL de la imagen
    logo_url = url_for('static', filename='logo.png')


    # Detalle de cálculo para mostrar en la interfaz (incluye el peso ajustado)
    detalle_dama = (
        f' (Peso Base: {peso_base_dama:,.2f}g, '
        f'Peso Oro Puro ({kilates_dama}K): {peso_ajustado_dama:,.2f}g, ' 
        f'Add: ${cost_adicional_dama:,.2f}, CT: {ct_dama:,.3f}, '
        f'Diamantes: ${monto_diamantes_dama:,.2f})'
    )
        
    detalle_cab = (
        f' (Peso Base: {peso_base_cab:,.2f}g, '
        f'Peso Oro Puro ({kilates_cab}K): {peso_ajustado_cab:,.2f}g, ' 
        f'Add: ${cost_adicional_cab:,.2f}, CT: {ct_cab:,.3f}, '
        f'Diamantes: ${monto_diamantes_cab:,.2f})'
    )
    
    # --------------------- Generación del HTML para el Formulario ---------------------
        
    def generate_selectors(tipo, modelo, metal, kilates_actual, anchos, tallas, ancho_actual, talla_actual):
        kilates_opciones = sorted(FACTOR_KILATES.keys(), key=int, reverse=True)
        
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
        
        html = f"""
        <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
            {kilates_selector}
            <div class="w-full md:w-1/3">
                <label for="ancho_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['ancho']}</label>
                <select id="ancho_{tipo}" name="ancho_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{a}" {"selected" if str(a) == str(ancho_actual) else ""}>{a}</option>' for a in anchos])}
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
        <div class="w-full max-w-2xl card p-6 md:p-10 mt-6">
            
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
            const nombreInput = document.getElementById('nombre_cliente');
            const emailInput = document.getElementById('email_cliente');

            // 1. Cargar datos de localStorage al cargar la página
            document.addEventListener('DOMContentLoaded', () => {{
                // Se usa {{ y }} para escapar las llaves de JavaScript de la f-string de Python
                if (!nombreInput.value && localStorage.getItem('nombre_cliente')) {{
                    nombreInput.value = localStorage.getItem('nombre_cliente');
                }}
                if (!emailInput.value && localStorage.getItem('email_cliente')) {{
                    emailInput.value = localStorage.getItem('email_cliente');
                }}
            }});

            // 2. Guardar datos en localStorage al cambiar el input (en tiempo real)
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
    df, _ = cargar_datos()
    
    mensaje_exito = None
    
    if request.method == "POST":
        seleccion = request.form.get("seleccion")
        tipo = request.form.get("tipo")
        
        # Lógica de Retorno al Formulario - Activado por el botón "Volver al Formulario"
        if request.form.get("volver_btn") == "true":
            # Redirige con fresh_selection=True para forzar el reseteo de Ancho/Talla en /
            return redirect(url_for("formulario", fresh_selection=True))
        
        # Lógica de Selección de Anillo - Activado por botones "Seleccionar Dama/Caballero"
        if seleccion and tipo:
            try:
                modelo, metal = seleccion.split(";")
                session[f"modelo_{tipo}"] = modelo.strip().upper()
                session[f"metal_{tipo}"] = metal.strip().upper()
                # Borrar Ancho y Talla en la sesión para forzar la pre-selección del nuevo modelo en el formulario
                session[f"ancho_{tipo}"] = ""
                session[f"talla_{tipo}"] = ""
                
                tipo_display = "Dama" if tipo == "dama" else "Caballero"
                mensaje_exito = f"✅ ¡Modelo **{modelo} ({metal})** para **{tipo_display}** guardado! Seleccione el otro o presione 'Volver al Formulario'."
                
            except ValueError:
                logging.error("Error en el formato de selección del catálogo.")
                mensaje_exito = "❌ Error al procesar la selección."


    # Generación del catálogo
    idioma = session.get("idioma", "Español")
    es = idioma == "Español"
    
    t = {
        "titulo": "Catálogo de Anillos de Boda" if es else "WEDDING RING CATALOG", 
        "volver": "Volver al Formulario" if es else "Back to Form",
        "dama": "Dama" if es else "Lady",
        "caballero": "Caballero" if es else "Gentleman",
        "metal": "Metal" if es else "Metal",
    }
    
    # Obtener selecciones actuales para mostrarlas en el catálogo
    modelo_dama_actual = session.get("modelo_dama", "")
    metal_dama_actual = session.get("metal_dama", "")
    modelo_cab_actual = session.get("modelo_cab", "")
    metal_cab_actual = session.get("metal_cab", "")
    
    # URL de la imagen
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


    # LÓGICA DE AGRUPACIÓN (Tarjeta por Variante Única: Modelo + Metal)
    df_catalogo = df[["NAME", "METAL", "RUTA FOTO"]].dropna(subset=["NAME", "METAL", "RUTA FOTO"])
    variantes_unicas = df_catalogo.drop_duplicates(subset=['NAME', 'METAL'])
    
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

    # --------------------- HTML/JINJA2 para el Catálogo ---------------------
    
    html_items = ""
    for item in catalogo_items:
        modelo = item["modelo"]
        metal = item["metal"]
        nombre_foto = item["nombre_foto"]
        ruta_web_foto = url_for('static', filename=nombre_foto)

        # Determinar si está seleccionado para Dama, Caballero, o ambos
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
            .card {{ background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); transition: all 0.2s; }}
            .card.selected-dama {{ border: 3px solid #EC4899; }}
            .card.selected-cab {{ border: 3px solid #3B82F6; }}
            .card.selected-both {{ border: 3px solid #10B981; }}
            .selection-status {{ font-size: 0.75rem; font-weight: 600; margin-top: 4px; }}
            .title-container {{ 
                display: flex; 
                align-items: center; 
                justify-content: space-between; 
                margin-bottom: 1rem;
                width: 100%;
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