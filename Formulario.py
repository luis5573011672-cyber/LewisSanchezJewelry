import requests
import os
import pandas as pd
from flask import Flask, request, render_template_string, session, redirect, url_for
import logging
import re

# ... (Misma CONFIGURACIÓN GLOBAL, FUNCIONES DE UTILIDAD y cargar_datos) ...

# FACTOR_KILATES DEBE ESTAR DISPONIBLE EN GLOBAL
FACTOR_KILATES = {"22": 0.9167, "18": 0.75, "14": 0.5833, "10": 0.4167}

@app.route("/", methods=["GET", "POST"])
def formulario():
    """Ruta principal: maneja datos de cliente, selección de Kilates, Ancho, Talla y cálculo."""
    
    df, df_size = cargar_datos() 
    precio_onza, status = obtener_precio_oro()

    # ... (Lógica de idioma y t - traducciones) ...
    idioma = request.form.get("idioma", session.get("idioma", "Español"))
    session["idioma"] = idioma
    es = idioma == "Español"
    t = {
        "titulo": "Formulario de Presupuesto u Orden" if es else "Estimate or Work Order Form",
        "seleccionar": "Seleccione una opción de catálogo" if es else "Select a catalog option",
        "kilates": "Kilates (Carat)", # Nuevo
        "ancho": "Ancho (mm)" if es else "Width (mm)",
        "talla": "Talla (Size)",
        "guardar": "Guardar" if es else "Save",
        "monto": "Monto total del presupuesto" if es else "Total estimate amount",
        "dama": "Dama" if es else "Lady",
        "cab": "Caballero" if es else "Gentleman",
        "catalogo_btn": "Abrir Catálogo" if es else "Open Catalog"
    }

    # 1. Obtener selecciones del Catálogo (Solo Modelo y Metal)
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
        tallas = sorted(df_size.loc[filtro_size, "SIZE"].astype(str).str.strip().unique().tolist(), 
                        key=lambda x: (re.sub(r'\D', '', x), x))
        return anchos, tallas

    anchos_d, tallas_d = get_options(modelo_dama)
    anchos_c, tallas_c = get_options(modelo_cab)

    # --- Función de Búsqueda de Peso y Costo (Actualizada - ya no busca Kilate) ---
    def obtener_peso_y_costo(modelo, metal, ancho, talla):
        if not all([modelo, metal, ancho, talla]) or modelo == t['seleccionar']:
            return 0, 0, 0
            
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

        # 2. Buscar el COSTO FIJO en df (solo por Modelo y Metal - el costo NO depende de Kilate)
        filtro_costo = (df["NAME"] == modelo) & \
                       (df["METAL"] == metal)
        
        price_cost = 0
        if not df.loc[filtro_costo].empty:
            # Tomamos la primera coincidencia
            costo_fila = df.loc[filtro_costo].iloc[0] 
            price_cost = costo_fila.get("PRICE COST", 0)
            try: price_cost = float(price_cost)
            except: price_cost = 0

        return peso, price_cost, 1

    # --- Cálculo dama ---
    peso_dama, cost_dama, found_dama = obtener_peso_y_costo(modelo_dama, metal_dama, ancho_dama, talla_dama)
    monto_dama = 0.0
    if peso_dama > 0 and precio_onza is not None and kilates_dama in FACTOR_KILATES:
        # Se calcula el valor del oro usando el KILATE seleccionado en el formulario.
        _, monto_oro_dama = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_dama, 0), peso_dama)
        monto_dama = monto_oro_dama + cost_dama
        monto_total += monto_dama

    # --- Cálculo caballero ---
    peso_cab, cost_cab, found_cab = obtener_peso_y_costo(modelo_cab, metal_cab, ancho_cab, talla_cab)
    monto_cab = 0.0
    if peso_cab > 0 and precio_onza is not None and kilates_cab in FACTOR_KILATES:
        # Se calcula el valor del oro usando el KILATE seleccionado en el formulario.
        _, monto_oro_cab = calcular_valor_gramo(precio_onza, FACTOR_KILATES.get(kilates_cab, 0), peso_cab)
        monto_cab = monto_oro_cab + cost_cab
        monto_total += monto_cab

    # --------------------- Generación del HTML para el Formulario ---------------------
    
    def generate_selectors(tipo, modelo, metal, kilates_actual, anchos, tallas, ancho_actual, talla_actual):
        # Asume que las opciones de kilates son las claves de FACTOR_KILATES
        kilates_opciones = sorted(FACTOR_KILATES.keys(), key=int, reverse=True) 

        if modelo == t['seleccionar'] or not anchos or not tallas:
            # Mostramos el selector de Kilates incluso si el modelo no está seleccionado
            kilates_html = f"""
                <div>
                    <label for="kilates_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['kilates']}</label>
                    <select id="kilates_{tipo}" name="kilates_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg">
                        {''.join([f'<option value="{k}" {"selected" if k == kilates_actual else ""}>{k}K</option>' for k in kilates_opciones])}
                    </select>
                </div>
            """
            if modelo == t['seleccionar']:
                 return kilates_html + f'<p class="text-red-500 pt-3">Seleccione un modelo para habilitar Ancho y Talla.</p>'
            
            return kilates_html + f'<p class="text-red-500 pt-3">No hay datos de Ancho/Talla en Excel para este modelo.</p>'

        
        html = f"""
        <div class="flex flex-col md:flex-row md:space-x-4 space-y-4 md:space-y-0 pt-4">
            <div class="w-full md:w-1/3">
                <label for="kilates_{tipo}" class="block text-sm font-medium text-gray-700 mb-1">{t['kilates']}</label>
                <select id="kilates_{tipo}" name="kilates_{tipo}" class="w-full p-2 border border-gray-300 rounded-lg">
                    {''.join([f'<option value="{k}" {"selected" if k == kilates_actual else ""}>{k}K</option>' for k in kilates_opciones])}
                </select>
            </div>
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
    
    # ... (Resto del HTML del formulario, con los selectores insertados)
    
    html_form = f"""
    <!DOCTYPE html>
    <body class="p-4 md:p-8 flex justify-center items-start min-h-screen">
        <div class="w-full max-w-2xl card p-6 md:p-10 mt-6">
            <h1 class="text-3xl font-extrabold mb-4 text-gray-800 text-center">{t['titulo']}</h1>
            <form method="POST" action="/" class="space-y-4">
                <h2 class="text-xl font-semibold pt-4 text-pink-700">Modelo {t['dama']}</h2>
                <div class="bg-pink-50 p-4 rounded-lg space-y-3">
                    <p class="text-sm font-medium text-gray-700">
                        Modelo: <span class="font-bold text-gray-900">{modelo_dama}</span> 
                        {' (' + metal_dama + ')' if metal_dama else ''}
                    </p>
                    {selectores_dama}
                    <span class="text-xs text-gray-500">
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
                    <span class="text-xs text-gray-500">
                        {'Monto Estimado: $' + f'{monto_cab:,.2f}' + ' USD (Peso: ' + f'{peso_cab:,.2f}' + 'g)' if monto_cab > 0 else 'Seleccione todos los detalles para calcular.'}
                    </span>
                </div>

                <a href="{url_for('catalogo')}" class="inline-block px-4 py-2 text-white bg-indigo-600 rounded-lg shadow-md hover:bg-indigo-700 transition duration-150 text-sm font-semibold">
                    {t['catalogo_btn']} (Cambiar Modelo/Metal)
                </a>

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

### 2. Modificaciones en la Ruta del Catálogo (`/catalogo`)

El catálogo se simplifica: su único trabajo es guardar el **Modelo** y el **Metal**, y luego redirigir a `/`.

```python
@app.route("/catalogo", methods=["GET", "POST"])
def catalogo():
    """Ruta del catálogo: selecciona Modelo y Metal y vuelve al formulario."""
    df, _ = cargar_datos()
    
    # 1. Manejo del POST: Si se selecciona un producto, guardamos y volvemos.
    if request.method == "POST":
        seleccion = request.form.get("seleccion")
        tipo = request.form.get("tipo")
        
        if seleccion and tipo:
            try:
                # El valor del botón ahora es: 'MODELO;METAL' (Kilates se selecciona en el formulario)
                modelo, metal = seleccion.split(";")
                session[f"modelo_{tipo}"] = modelo
                session[f"metal_{tipo}"] = metal
                
                # NO limpiamos Kilates, Ancho, ni Talla. Usamos los valores anteriores.

                return redirect(url_for("formulario"))
            except ValueError:
                logging.error("Error en el formato de selección del catálogo.")
        
        return redirect(url_for("formulario"))


    # 2. Generación del catálogo (Agrupado por Modelo, opciones por Metal)
    # ... (Misma lógica de agrupación 'catalogo_agrupado', pero solo por MODELO y METAL) ...

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
    
    # --------------------- HTML/JINJA2 para el Catálogo (Actualizado) ---------------------
    
    # ... (Mismo HTML del catálogo)
    
    for modelo, data in catalogo_agrupado.items():
        # ... (código para la imagen y el título) ...
        
        for metal in data['METALES']:
            valor_seleccion = f"{modelo};{metal}" # ¡SOLO MODELO Y METAL!
            
            html_catalogo += f"""
                            <div class="bg-gray-50 p-3 rounded-lg border">
                                <p class="text-sm font-medium text-gray-800 mb-2">{metal}</p>
                                
                                <button type="submit" name="seleccion" value="{valor_seleccion}" 
                                        class="inline-block w-full px-3 py-1.5 text-white bg-pink-500 rounded text-xs font-semibold hover:bg-pink-600 transition duration-150 text-center mb-1" 
                                        onclick="document.getElementById('tipo_input').value='dama';">
                                    Dama (Seleccionar)
                                </button>
                                
                                <button type="submit" name="seleccion" value="{valor_seleccion}" 
                                        class="inline-block w-full px-3 py-1.5 text-white bg-blue-500 rounded text-xs font-semibold hover:bg-blue-600 transition duration-150 text-center"
                                        onclick="document.getElementById('tipo_input').value='cab';">
                                    Caballero (Seleccionar)
                                </button>
                            </div>
                            """
        # ... (Resto del cierre del HTML) ...
    
    # ... (Cierre del HTML) ...
    return render_template_string(html_catalogo)

if __name__ == '__main__':
    logging.info("\n--- INICIANDO SERVIDOR FLASK EN MODO DESARROLLO ---")
    app.run(debug=True)