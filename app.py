"""
Aplicativo Web de Validación y Control de Calidad Cartográfica (Protocolo CONAF)
Desarrollado en Python con Streamlit, GeoPandas y Shapely.
"""

import os
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
from streamlit_folium import st_folium

from config.templates import PLANTILLAS
from utils.loader import read_shapefiles_from_directory, extract_and_read_zip
from utils.exporter import generate_excel_report, export_spatial_errors_to_zip
from validators.attribute_validator import check_crs, check_zm, validate_layer_attributes
from validators.spatial_validator import validate_spatial_relationships

# Configuración de página Streamlit
st.set_page_config(
    page_title="Control de Calidad Cartográfica PAS / CONAF",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    .main-header {
        font-size: 26px;
        font-weight: bold;
        color: #1F4E78;
        margin-bottom: 5px;
    }
    .sub-header {
        font-size: 15px;
        color: #595959;
        margin-bottom: 25px;
    }
    .metric-card {
        background-color: #F8F9FA;
        border-radius: 8px;
        padding: 15px;
        border-left: 5px solid #1F4E78;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🌲 Sistema de Control de Calidad Cartográfica (Protocolo CONAF)</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Validación atributular, geometría 2D, dominios, proyecciones y relaciones topológicas espaciales.</div>', unsafe_allow_html=True)

# =============================================================================
# SIDEBAR DE CONFIGURACIÓN
# =============================================================================
st.sidebar.header("⚙️ Parámetros de Entrada")

nombre_predio = st.sidebar.text_input("Nombre del Predio:", value="PARTE_FUNDO_QUELEN")
epsg_target = st.sidebar.number_input("EPSG Objetivo:", value=32719, step=1, help="32719 para WGS 84 / UTM Zone 19S")
tol_area = st.sidebar.number_input("Tolerancia de Área (m²):", value=0.005, step=0.001, format="%.4f")

st.sidebar.markdown("---")
input_mode = st.sidebar.radio("Modo de Carga de Datos:", ["Archivo ZIP comprimido", "Directorio Local"])

uploaded_zip = None
dir_path = None

if input_mode == "Archivo ZIP comprimido":
    uploaded_zip = st.sidebar.file_uploader("Subir ZIP con archivos Shapefile (.shp, .dbf, .prj, .shx):", type=["zip"])
else:
    dir_path = st.sidebar.text_input("Ruta de Carpeta Local:", value=r"C:\SCRIPT-PAS\SHP")

st.sidebar.markdown("---")
st.sidebar.subheader(" Base Histórica (Opcional)")
master_zip = st.sidebar.file_uploader("Compilado de Áreas de Corta (.zip o .shp):", type=["zip", "shp"], key="master_zip")

run_validation = st.sidebar.button("🚀 Ejecutar Validación Cartográfica", type="primary", use_container_width=True)

# =============================================================================
# EJECUCIÓN DEL ANÁLISIS
# =============================================================================
if run_validation:
    dict_gdfs = {}
    dict_meta = {}
    files_found = []
    temp_dir_obj = None

    with st.spinner("Cargando y leyendo capas vectoriales..."):
        if input_mode == "Archivo ZIP comprimido":
            if uploaded_zip is None:
                st.error("Por favor, sube un archivo ZIP con los shapefiles.")
                st.stop()
            dict_gdfs, dict_meta, files_found, temp_dir_obj = extract_and_read_zip(uploaded_zip, nombre_predio)
        else:
            if not dir_path or not os.path.exists(dir_path):
                st.error(f"La ruta del directorio especificada no existe: {dir_path}")
                st.stop()
            dict_gdfs, dict_meta, files_found = read_shapefiles_from_directory(dir_path, nombre_predio)

    if not dict_gdfs:
        st.warning("No se encontraron archivos Shapefile (.shp) válidos en la fuente especificada.")
        st.stop()

    st.success(f"Se cargaron exitosamente **{len(dict_gdfs)} capas vectoriales**.")

    # Cargar compilado de áreas de corta si se proporcionó
    master_gdf = None
    if master_zip is not None:
        try:
            if master_zip.name.endswith(".zip"):
                m_gdfs, _, _, _ = extract_and_read_zip(master_zip, "master")
                if m_gdfs:
                    master_gdf = list(m_gdfs.values())[0]
        except Exception as e:
            st.warning(f"No se pudo cargar el compilado histórico: {e}")

    # =========================================================================
    # EJECUTAR VALIDACIONES ATRIBUTULARES Y ESPACIALES
    # =========================================================================
    all_reports = []
    all_logs = []

    # 1. Chequeo de Archivos Faltantes vs Plantilla
    esperados = [f"{prefijo}_{nombre_predio}" for prefijo in PLANTILLAS.keys()]
    encontrados = list(dict_gdfs.keys())
    
    # Mapeo flexible
    faltantes = []
    for pref in PLANTILLAS.keys():
        name_expected = f"{pref}_{nombre_predio}"
        if not any(k == pref or k == name_expected for k in encontrados):
            faltantes.append(name_expected)

    if faltantes:
        for f_missing in faltantes:
            all_logs.append({"capa": f_missing, "tipo": "ERROR", "mensaje": "Shapefile FALTANTE según protocolo CONAF."})

    # 2. Reviso cada capa cargada
    with st.spinner("Validando atributos, proyección, Z/M y dominios..."):
        for layer_name, gdf in dict_gdfs.items():
            f_meta = dict_meta.get(layer_name, {})
            
            # CRS
            crs_ok, crs_msg = check_crs(gdf, target_epsg=epsg_target)
            all_logs.append({"capa": layer_name, "tipo": "OK" if crs_ok else "ERROR", "mensaje": f"CRS: {crs_msg}"})
            
            # Z/M
            zm_ok, zm_msg = check_zm(gdf)
            all_logs.append({"capa": layer_name, "tipo": "OK" if zm_ok else "ERROR", "mensaje": f"Dimensión: {zm_msg}"})

            # Atributos y Plantilla
            res_df, layer_logs = validate_layer_attributes(layer_name, gdf, f_meta)
            if not res_df.empty:
                all_reports.append(res_df)
            all_logs.extend(layer_logs)

    # 3. Validaciones Espaciales
    with st.spinner("Validando relaciones topológicas y espaciales..."):
        spatial_logs, spatial_errors = validate_spatial_relationships(
            dict_gdfs, nombre_predio, master_area_corta_gdf=master_gdf, tol_area=tol_area
        )
        all_logs.extend(spatial_logs)

    # Consolidar Tablas
    final_report_df = pd.concat(all_reports, ignore_index=True) if all_reports else pd.DataFrame()
    logs_df = pd.DataFrame(all_logs)

    # Conteo de Métricas
    total_logs = len(logs_df)
    n_ok = (logs_df["tipo"] == "OK").sum() if not logs_df.empty else 0
    n_warn = (logs_df["tipo"] == "WARNING").sum() if not logs_df.empty else 0
    n_err = (logs_df["tipo"] == "ERROR").sum() if not logs_df.empty else 0

    # Guardar estado en sesión de Streamlit para mantener resultados activos
    st.session_state["analysis_done"] = True
    st.session_state["final_report_df"] = final_report_df
    st.session_state["logs_df"] = logs_df
    st.session_state["dict_gdfs"] = dict_gdfs
    st.session_state["spatial_errors"] = spatial_errors
    st.session_state["n_ok"] = n_ok
    st.session_state["n_warn"] = n_warn
    st.session_state["n_err"] = n_err

# =============================================================================
# MOSTRAR RESULTADOS SI YA SE EJECUTÓ
# =============================================================================
if st.session_state.get("analysis_done", False):
    logs_df = st.session_state["logs_df"]
    final_report_df = st.session_state["final_report_df"]
    dict_gdfs = st.session_state["dict_gdfs"]
    spatial_errors = st.session_state["spatial_errors"]
    
    st.markdown("---")
    # Tarjetas de Métricas
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Capas Analizadas", len(dict_gdfs))
    m2.metric("Pruebas Exitosas (OK)", st.session_state["n_ok"], delta="✅")
    m3.metric("Advertencias (WARNING)", st.session_state["n_warn"], delta="⚠️")
    m4.metric("Errores Críticos (ERROR)", st.session_state["n_err"], delta="-❌", delta_color="inverse")

    st.markdown("<br>", unsafe_allow_html=True)

    # Pestañas Principales
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Resumen Ejecutivo de Diagnóstico",
        "📊 Tabla de Atributos y Plantillas",
        "🗺️ Visor Geográfico Interactivo",
        "📥 Descargas (Excel y SHP de Errores)"
    ])

    with tab1:
        st.subheader("Registros del Sistema y Diagnóstico")
        
        # Filtros de logs
        col_f1, col_f2 = st.columns([1, 3])
        with col_f1:
            tipo_filter = st.multiselect("Filtrar por Severidad:", ["OK", "WARNING", "ERROR"], default=["WARNING", "ERROR"])
        with col_f2:
            search_capa = st.text_input("Buscar por Capa o Mensaje:")

        filtered_logs = logs_df.copy()
        if tipo_filter:
            filtered_logs = filtered_logs[filtered_logs["tipo"].isin(tipo_filter)]
        if search_capa:
            filtered_logs = filtered_logs[
                filtered_logs["capa"].str.contains(search_capa, case=False, na=False) |
                filtered_logs["mensaje"].str.contains(search_capa, case=False, na=False)
            ]

        def color_tipo(val):
            if val == "OK":
                return "background-color: #E2EFDA; color: #375623; font-weight: bold;"
            elif val == "WARNING":
                return "background-color: #FFF2CC; color: #7F6000; font-weight: bold;"
            elif val == "ERROR":
                return "background-color: #FCE4D6; color: #C65911; font-weight: bold;"
            return ""

        styler = filtered_logs.style
        style_func = getattr(styler, "map", getattr(styler, "applymap", None))
        styled_df = style_func(color_tipo, subset=["tipo"]) if style_func else filtered_logs

        st.dataframe(
            styled_df,
            use_container_width=True,
            height=450
        )

    with tab2:
        st.subheader("Verificación de Campos y Estructura vs Plantilla CONAF")
        if not final_report_df.empty:
            capa_sel = st.selectbox("Seleccionar Capa para inspeccionar:", final_report_df["shape"].unique())
            df_capa = final_report_df[final_report_df["shape"] == capa_sel]
            
            st.dataframe(df_capa, use_container_width=True, height=400)
        else:
            st.info("No hay datos de estructura atributular registrados.")

    with tab3:
        st.subheader("Vista Previa Geográfica de Capas y Errores")
        
        # Crear mapa centrado en los datos
        first_gdf = list(dict_gdfs.values())[0]
        first_gdf_4326 = first_gdf.to_crs(epsg=4326)
        bounds = first_gdf_4326.total_bounds
        center_lat = (bounds[1] + bounds[3]) / 2.0
        center_lon = (bounds[0] + bounds[2]) / 2.0

        m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")

        # Agregar Capas normales
        for l_name, l_gdf in dict_gdfs.items():
            try:
                l_gdf_4326 = l_gdf.to_crs(epsg=4326)
                folium.GeoJson(
                    l_gdf_4326,
                    name=l_name,
                    style_function=lambda x: {'fillColor': '#3186cc', 'color': '#1F4E78', 'weight': 1.5, 'fillOpacity': 0.2},
                    tooltip=folium.GeoJsonTooltip(fields=list(l_gdf_4326.columns[:3]), aliases=list(l_gdf_4326.columns[:3]))
                ).add_to(m)
            except Exception:
                pass

        # Agregar Capas de Error en ROJO destacadas
        for err_name, err_gdf in spatial_errors.items():
            if err_gdf is not None and not err_gdf.empty:
                try:
                    err_gdf_4326 = err_gdf.to_crs(epsg=4326)
                    folium.GeoJson(
                        err_gdf_4326,
                        name=f"⚠️ ERROR: {err_name}",
                        style_function=lambda x: {'fillColor': '#FF0000', 'color': '#990000', 'weight': 3, 'fillOpacity': 0.6},
                        tooltip=f"Error Detectado: {err_name}"
                    ).add_to(m)
                except Exception:
                    pass

        folium.LayerControl().add_to(m)
        st_folium(m, width="100%", height=550)

    with tab4:
        st.subheader("📦 Generación y Descarga de Entregables")
        
        col_d1, col_d2 = st.columns(2)
        
        with col_d1:
            st.markdown("### 📊 Reporte Consolidado en Excel")
            st.write("Contiene la auditoría completa de campos, tipos, decimales, dominios y log de errores espaciales.")
            
            excel_bytes = generate_excel_report(final_report_df, logs_df.to_dict('records'))
            st.download_button(
                label="📥 Descargar Reporte Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"00_Reporte_revision_campos_{nombre_predio}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

        with col_d2:
            st.markdown("### 🗺️ Shapefile de Errores Espaciales (ZIP)")
            st.write("Empaqueta todos los polígonos/puntos con traslapes o fuera de límite para cargarlos directamente en QGIS o ArcGIS.")
            
            if spatial_errors:
                zip_bytes = export_spatial_errors_to_zip(spatial_errors)
                if zip_bytes:
                    st.download_button(
                        label="⚠️ Descargar Errores Espaciales (.zip)",
                        data=zip_bytes,
                        file_name=f"Errores_Espaciales_{nombre_predio}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                else:
                    st.success("🎉 ¡Excelente! No hay errores espaciales para exportar.")
            else:
                st.success("🎉 ¡Excelente! No se registraron conflictos de geometrías.")
