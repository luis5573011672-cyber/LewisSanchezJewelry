import requests
import os
import pandas as pd
from flask import Flask, request, render_template_string, session, redirect, url_for
import logging
import math
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
FACTOR_KILATES = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}
DEFAULT_GOLD_PRICE = 5600.00 # USD por Onza (Valor por defecto/fallback)

# Variables globales para los DataFrames (Caché)
df_global = pd.DataFrame()
df_adicional_global = pd.DataFrame()

# --------------------- FUNCIONES DE UTILIDAD (Omitidas por brevedad, no hay cambios) ---------------------

def obtener_precio_oro() -> Tuple[float, str]:
# ... (Función obtener_precio_oro)
    API_KEY = "goldapi-4g9e8p719mgvhodho-io" 
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {"x-access-token": API_KEY, "Content-Type": "application/json"}
    
    try:
        if not API_KEY or API_KEY == "goldapi-4g9e8p719mgvhodho-io":
             logging.warning("Usando clave de API de prueba o no válida. Usando precio por defecto.")
             return DEFAULT_GOLD_PRICE, "fallback (API key issue)"

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
# ... (Función calcular_valor_gramo)
    if valor_onza <= 0 or peso_gramos <= 0 or pureza_factor <= 0:
        return 0.0, 0.0
    
    valor_gramo = (valor_onza / 31.1035) * pureza_factor
    monto_total = valor_gramo * peso_gramos
    return valor_gramo, monto_total

def calcular_monto_aproximado(monto_bruto: float) -> float:
# ... (Función calcular_monto_aproximado)
    if monto_bruto <= 0:
        return 0.0
    
    aproximado = math.ceil(monto_bruto / 10.0) * 10.0
    return aproximado

def cargar_datos() -> Tuple[pd.DataFrame, pd.DataFrame]:
# ... (Función cargar_datos)
    global df_global, df_adicional_global
    if not df_global.empty and not df_adicional_global.empty:
        return df_global, df_adicional_global

    try:
        df_raw = pd.read_excel(EXCEL_PATH, sheet_name="WEDDING BANDS", engine="openpyxl", header=None)
        new_columns_df = df_raw.iloc[1].astype(str).str.strip().str.upper()
        df = df_raw.iloc[2:].copy()
        df.columns = new_columns_df
        
        if 'WIDTH' in df.columns:
            df.rename(columns={'WIDTH': 'ANCHO'}, inplace=True)
            
        df_adicional_raw = pd.read_excel(EXCEL_PATH, sheet_name="SIZE", engine="openpyxl", header=None)
        new_columns_adicional = df_adicional_raw.iloc[0].astype(str).str.strip().str.upper()
        df_adicional = df_adicional_raw.iloc[1:].copy()
        df_adicional.columns = new_columns_adicional
        
        for col in ["NAME", "METAL", "RUTA FOTO", "ANCHO", "PESO", "PESO_AJUSTADO", "GENERO"]: 
            if col in df.columns:
                if col == "ANCHO":
                     df[col] = df[col].astype(str).str.strip().str.replace('MM', '', regex=False).str.strip()
                else:
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
# ... (Función obtener_nombre_archivo_imagen)
    if pd.isna(ruta_completa) or not str(ruta_completa).strip():
        return ""
    
    ruta_limpia = str(ruta_completa).replace('\\', '/')
    nombre_archivo = os.path.basename(ruta_limpia).strip()
    return nombre_archivo.replace('%20', ' ')

def obtener_peso_y_costo(df_adicional_local: pd.DataFrame, modelo: str, metal: str, ancho: str, talla: str, genero: str, select_text: str) -> Tuple[float, float, float]:
# ... (Función obtener_peso_y_costo)
    global df_global 
    
    if df_global.empty or not all([modelo, metal, ancho, talla, genero]) or modelo == select_text:
        return 0.0, 0.0, 0.0 
        
    filtro_base = (df_global["NAME"] == modelo) & \
                  (df_global["ANCHO"] == ancho) & \
                  (df_global["METAL"] == metal) & \
                  (df_global["GENERO"] == genero) 
    
    peso = 0.0
    price_cost = 0.0
    
    if not df_global.loc[filtro_base].empty:
        base_fila = df_global.loc[filtro_base].iloc[0]
        peso_raw = base_fila.get("PESO_AJUSTADO", base_fila.get("PESO", 0))
        price_cost_raw = base_fila.get("PRICE COST", 0) 
        try: peso = float(peso_raw)
        except: peso = 0.0
        try: price_cost = float(price_cost_raw)
        except: price_cost = 0.0

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
    
    # --- 0. Manejo de Limpieza Forzada (Accedido por /?clear=True) ---
    if request.method == "GET" and request.args.get("clear") == "True":
        logging.info("Limpieza Forzada de Sesión. Borrando Session.")
        session.clear()
        return redirect(url_for("formulario"))
    
    # --- Carga de Datos ---
    df, df_adicional = cargar_datos()
    precio_onza, status = obtener_precio_oro()
    monto_total_bruto = 0.0
    
    # --- 1. Cargar traducciones, idioma y datos del cliente (PRIMERO) ---
    
    idioma = request.form.get("idioma", session.get("idioma", "Español"))
    session["idioma"] = idioma 
    es = idioma == "Español"

    t = {
        # ... (Traducciones)
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
        "cambiar_idioma": "Cambiar Idioma" if es else "Change Language",
        "nueva_sesion": "Iniciar Nueva Sesión" if es else "Start New Session"
    }

    # Cargar datos del cliente: Leemos de la sesión.
    nombre_cliente = session.get("nombre_cliente", "") 
    email_cliente = session.get("email_cliente", "") 

    # Cargar datos del anillo de la SESIÓN (Valores actuales)
    kilates_dama = session.get("kilates_dama", "14")
    ancho_dama = session.get("ancho_dama", "")
    talla_dama = session.get("talla_dama", "")
    modelo_dama = session.get("modelo_dama", t['seleccionar']).upper()
    metal_dama = session.get("metal_dama", "").upper()
    
    kilates_cab = session.get("kilates_cab", "14")
    ancho_cab = session.get("ancho_cab", "")
    talla_cab = session.get("talla_cab", "")
    modelo_cab = session.get("modelo_cab", t['seleccionar']).upper()
    metal_cab = session.get("metal_cab", "").upper()
        
    
    # --- 2. Manejo de POST (Incluyendo cambio de Kilates, Ancho y Talla) ---
    if request.method == "POST":
        
        # 2.1. Guardar SIEMPRE los datos del cliente que vinieron en el POST
        nombre_cliente = request.form.get("nombre_cliente", nombre_cliente)
        email_cliente = request.form.get("email_cliente", email_cliente)
        session["nombre_cliente"] = nombre_cliente 
        session["email_cliente"] = email_cliente 
        
        # 2.2. Manejo del cambio de idioma 
        if "idioma" in request.form:
              return redirect(url_for("formulario"))
        
        # 2.3. Guardar las selecciones de anillo que vinieron en el POST
        # CORRECCIÓN: request.form.get() tiene prioridad. Esto asegura que el valor seleccionado (18)
        # se lea y se use para actualizar la variable local.
        kilates_dama = request.form.get("kilates_dama", kilates_dama)
        ancho_dama = request.form.get("ancho_dama", ancho_dama)
        talla_dama = request.form.get("talla_dama", talla_dama)
        
        kilates_cab = request.form.get("kilates_cab", kilates_cab)
        ancho_cab = request.form.get("ancho_cab", ancho_cab)
        talla_cab = request.form.get("talla_cab", talla_cab)
    
    # --- 3. Manejo de Regreso de Catálogo (GET con fresh_selection) ---
    fresh_selection = request.args.get("fresh_selection")
    if fresh_selection:
        # Se vacían Ancho/Talla para forzar la autoselección con el nuevo modelo/metal
        ancho_dama = ""
        talla_dama = ""
        ancho_cab = ""
        talla_cab = ""
        # NOTA: Kilates NO se vacía, mantiene su valor (14 por defecto o el último seleccionado por POST).

    # 4. Guardar los valores de anillo actuales/actualizados en sesión
    # Si kilates_dama es 18 (por el POST), se guarda 18 en la sesión.
    session["kilates_dama"] = kilates_dama
    session["ancho_dama"] = ancho_dama
    session["talla_dama"] = talla_dama
    session["kilates_cab"] = kilates_cab
    session["ancho_cab"] = ancho_cab
    session["talla_cab"] = talla_cab
    session["modelo_dama"] = modelo_dama
    session["metal_dama"] = metal_dama
    session["modelo_cab"] = modelo_cab
    session["metal_cab"] = metal_cab


    # --- 5. Opciones disponibles y Forzar selección de Ancho/Talla por defecto ---
    # ... (Lógica de get_options y autoselección de Ancho/Talla)

    def get_options(modelo):
        if df.empty or df_adicional.empty or modelo == t['seleccionar'].upper():
            return [], []
        
        filtro_ancho = (df["NAME"] == modelo)
        
        def sort_numeric_key(value_str):
            try: return float(value_str)
            except ValueError: return float('inf') 
                
        anchos_raw = df.loc[filtro_ancho, "ANCHO"].astype(str).str.strip().unique().tolist() if "ANCHO" in df.columns else []
        anchos = sorted(anchos_raw, key=sort_numeric_key)
        
        tallas_raw = df_adicional["SIZE"].astype(str).str.strip().unique().tolist() if "SIZE" in df_adicional.columns else []
        tallas = sorted(tallas_raw, key=sort_numeric_key)
        return anchos, tallas

    anchos_d, tallas_d = get_options(modelo_dama)
    anchos_c, tallas_c = get_options(modelo_cab)

    # Autoselección si el campo está vacío (ej. después de fresh_selection o cambio de modelo)
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

    # --- 6. Cálculos ---
    # ... (Lógica de cálculos)
    peso_dama, cost_fijo_dama, cost_adicional_dama = obtener_peso_y_costo(df_adicional, modelo_dama, metal_dama, ancho_dama, talla_dama, "DAMA", t['seleccionar'].upper())
    monto_dama = 0.0
    if peso_dama > 0 and precio_onza is not None and kilates_dama in FACTOR_KILATES:
        _, monto_oro_dama = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_dama, 0.0), peso_dama)
        monto_dama = monto_oro_dama + cost_fijo_dama + cost_adicional_dama 
        monto_total_bruto += monto_dama

    peso_cab, cost_fijo_cab, cost_adicional_cab = obtener_peso_y_costo(df_adicional, modelo_cab, metal_cab, ancho_cab, talla_cab, "CABALLERO", t['seleccionar'].upper())
    monto_cab = 0.0
    if peso_cab > 0 and precio_onza is not None and kilates_cab in FACTOR_KILATES:
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_cab, 0.0), peso_cab)
        monto_cab = monto_oro_cab + cost_fijo_cab + cost_adicional_cab
        monto_total_bruto += monto_cab
        
    monto_total_aprox = calcular_monto_aproximado(monto_total_bruto)
    
    # URL de la imagen (asumiendo que está en /static/logo.png)
    logo_url = url_for('static', filename='logo.png')

    # --------------------- Generación del HTML para el Formulario ---------------------
        
    def generate_selectors(tipo, modelo, metal, kilates_actual, anchos, tallas, ancho_actual, talla_actual):
        kilates_opciones = sorted(FACTOR_KILATES.keys(), key=int, reverse=True)
        
        # Kilates Selector
        kilates_selector = f"""
            <div class="w-full md:w-1/3">
                <label for="kilates_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['kilates']}</label>
                <select id="kilates_{tipo}" name="kilates_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg" onchange="this.form.submit()">
                    {''.join([f'<option value="{k}" {"selected" if k == kilates_actual else ""}>{k}K</option>' for k in kilates_opciones])}
                </select>
            </div>
        """
        # ... (Resto de selectores y HTML)
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
                    <a id="clear-session-btn" href="{url_for('formulario', clear=True)}" class="inline-block px-4 py-2 text-red-700 border border-red-500 rounded-lg text-sm font-semibold hover:bg-red-50 transition duration-150">
                        {t['nueva_sesion']}
                    </a>
                </div>
                
                <h2 class="text-xl font-semibold pt-4 text-pink-700">Modelo {t['dama']}</h2>
                <div class="bg-pink-50 p-4 rounded-lg space-y-3">
                    <p class="text-sm font-medium text-gray-700">
                        Modelo: <span class="font-bold text-gray-900">{modelo_dama}</span>
                        {' (' + metal_dama + ')' if metal_dama else ''}
                    </p>
                    {selectores_dama}
                    <span class="text-xs text-gray-500 block pt-2">
                        {'Monto Estimado BRUTO: $' + f'{monto_dama:,.2f}' + ' USD (Peso: ' + f'{peso_dama:,.2f}' + 'g, Adicional: $' + f'{cost_adicional_dama:,.2f}' + ')' if monto_dama > 0 else 'Seleccione todos los detalles para calcular.'}
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
                        {'Monto Estimado BRUTO: $' + f'{monto_cab:,.2f}' + ' USD (Peso: ' + f'{peso_cab:,.2f}' + 'g, Adicional: $' + f'{cost_adicional_cab:,.2f}' + ')' if monto_cab > 0 else 'Seleccione todos los detalles para calcular.'}
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
        // ... (Lógica de localStorage para cliente details) ...
        </script>
    </body>
    </html>
    """
    return render_template_string(html_form)

# ------------------------------------------------------------------------------------------------

@app.route("/catalogo", methods=["GET", "POST"])
def catalogo():
# ... (Función catalogo)
    df, _ = cargar_datos()
    
    mensaje_exito = None
    
    if request.method == "POST":
        seleccion = request.form.get("seleccion")
        tipo = request.form.get("tipo")
        
        if not seleccion and request.form.get("volver_btn"):
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


    # ... (Resto de la lógica y HTML del catálogo) ...
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

    html_catalogo = f"""
    <!DOCTYPE html>
    <html lang="{idioma.lower()}">
    <head>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-7xl mx-auto">
            
            <div class="title-container">
                <img src="{logo_url}" alt="Logo" class="logo-img" onerror="this.style.display='none';" />
                <h1 class="text-3xl font-extrabold text-gray-800">{t['titulo']}</h1>
                
                <div style="width: 60px; margin-left: 15px;"></div> 
            </div>
            
            {f'<div class="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative mb-6 text-center" role="alert">{mensaje_exito}</div>' if mensaje_exito else ''}

            <form method="POST" action="{url_for('catalogo')}" class="mb-8 text-center">
                <button type="submit" class="px-6 py-3 bg-indigo-600 text-white font-bold rounded-lg shadow-md hover:bg-indigo-700 transition duration-150" name="volver_btn" value="true">
                    {t['volver']}
                </button>
            </form>
                
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
    """
    
    for item in catalogo_items:
        modelo = item['modelo']
        metal = item['metal']
        nombre_foto = item['nombre_foto']
        ruta_web_foto = url_for('static', filename=nombre_foto) 
        valor_seleccion = f"{modelo};{metal}"
        
        is_dama = modelo == modelo_dama_actual and metal == metal_dama_actual
        is_cab = modelo == modelo_cab_actual and metal == metal_cab_actual
        card_class = "card"
        status_text = ""
        
        if is_dama and is_cab:
            card_class += " selected-both"
            status_text = "✅ Ambos seleccionados"
        elif is_dama:
            card_class += " selected-dama"
            status_text = f"✅ {t['dama']} seleccionada"
        elif is_cab:
            card_class += " selected-cab"
            status_text = f"✅ {t['caballero']} seleccionado"


        html_catalogo += f"""
                    <div class="{card_class} p-4 flex flex-col items-center text-center">
                        <img src="{ruta_web_foto}" alt="{modelo} - {metal}" 
                             class="w-full h-auto max-h-48 object-contain rounded-lg mb-3" 
                             onerror="this.onerror=null;this.src='{url_for('static', filename='placeholder.png')}';"
                        >
                        <p class="text-xl font-bold text-gray-900 mb-1">{modelo}</p>
                        <p class="text-md font-semibold text-indigo-700 mb-2">{t['metal']}: {metal}</p>
                        <p class="selection-status text-green-600">{status_text}</p>

                        <div class="mt-2 space-y-3 w-full border-t pt-3">
                            <form method="POST" action="{url_for('catalogo')}" class="inline-block w-full">
                                <input type="hidden" name="seleccion" value="{valor_seleccion}">
                                <button type="submit" name="tipo" value="dama"
                                        class="inline-block w-full px-3 py-1.5 text-white bg-pink-500 rounded text-sm font-semibold hover:bg-pink-600 transition duration-150 text-center mb-1">
                                    Seleccionar {t['dama']}
                                </button>
                            </form>
                            
                            <form method="POST" action="{url_for('catalogo')}" class="inline-block w-full">
                                <input type="hidden" name="seleccion" value="{valor_seleccion}">
                                <button type="submit" name="tipo" value="cab"
                                        class="inline-block w-full px-3 py-1.5 text-white bg-blue-500 rounded text-sm font-semibold hover:bg-blue-600 transition duration-150 text-center">
                                    Seleccionar {t['caballero']}
                                </button>
                            </form>
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

if __name__ == '__main__':
    logging.info("\n--- INICIANDO SERVIDOR FLASK EN MODO DESARROLLO ---")
    app.run(debug=True)