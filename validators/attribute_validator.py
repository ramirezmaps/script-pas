"""
Módulo de Validación Atributular y Geométrica
Verifica proyecciones, dimensiones 2D/3D, concordancia con plantillas CONAF,
dominios numéricos/categóricos, recálculo de superficies/longitudes, coordenadas y formato de cadenas.
"""

import re
import numpy as np
import pandas as pd
import geopandas as gpd
from typing import Dict, List, Tuple, Any
from config.templates import PLANTILLAS, DOMINIOS_CONAF
from utils.loader import map_python_type_to_schema

def check_crs(gdf: gpd.GeoDataFrame, target_epsg: int = 32719) -> Tuple[bool, str]:
    """Verifica si el sistema de coordenadas coincide con el objetivo (EPSG:32719 por defecto)."""
    if gdf.crs is None:
        return False, "Sin CRS definido (NA)"
    
    epsg = gdf.crs.to_epsg()
    if epsg == target_epsg:
        return True, f"CORRECTO (WGS84 / UTM 19S, EPSG:{target_epsg})"
    else:
        return False, f"INCORRECTO (Tiene EPSG:{epsg or gdf.crs.name})"

def check_zm(gdf: gpd.GeoDataFrame) -> Tuple[bool, str]:
    """Verifica si el shapefile tiene dimensiones 3D o Z/M."""
    try:
        has_z = bool(gdf.geometry.has_z.any())
    except Exception:
        has_z = False

    if has_z:
        return False, "Geometría 3D/ZM detectada (Se requiere 2D)"
    return True, "Geometría 2D (Sin dimensiones Z/M)"

def validate_domain(series: pd.Series, domain: List[Any]) -> Tuple[bool, List[int]]:
    """Valida si los valores de una columna pertenecen al dominio permitido sin estar vacíos/NA."""
    domain_str = [str(x).strip() for x in domain]
    
    def is_invalid(val):
        if pd.isna(val) or str(val).strip() == "":
            return True
        return str(val).strip() not in domain_str

    invalid_mask = series.apply(is_invalid)
    idx_invalid = list(series.index[invalid_mask])
    return (len(idx_invalid) == 0), idx_invalid

def validate_layer_attributes(
    layer_name: str, 
    gdf: gpd.GeoDataFrame, 
    fiona_meta: Dict[str, Any]
) -> Tuple[pd.DataFrame, List[Dict[str, str]]]:
    """
    Compara la estructura y datos del GeoDataFrame contra la plantilla CONAF correspondiente.
    Retorna la tabla comparativa (DataFrame) y un listado de logs/alertas.
    """
    logs = []
    
    # Determinar prefijo de plantilla
    prefijo = None
    for p_key in PLANTILLAS.keys():
        if layer_name == p_key or layer_name.startswith(p_key + "_"):
            prefijo = p_key
            break
            
    if not prefijo or prefijo not in PLANTILLAS:
        logs.append({"capa": layer_name, "tipo": "WARNING", "mensaje": "Capa no definida en la plantilla CONAF"})
        return pd.DataFrame(), logs

    plantilla = PLANTILLAS[prefijo]
    plantilla_df = pd.DataFrame(plantilla)
    
    # Obtener esquema de fiona si está disponible
    fiona_schema = fiona_meta.get("schema", {}).get("properties", {}) if fiona_meta else {}

    shape_cols = [c for c in gdf.columns if c != 'geometry']
    
    # 1. Comprobar orden exacto de columnas
    coincide_orden = (list(plantilla_df["nombre"]) == shape_cols)
    if coincide_orden:
        logs.append({"capa": layer_name, "tipo": "OK", "mensaje": "Orden de campos CORRECTO"})
    else:
        logs.append({"capa": layer_name, "tipo": "ERROR", "mensaje": f"Orden INCORRECTO. Esperado: {list(plantilla_df['nombre'])} | Encontrado: {shape_cols}"})

    rows = []
    for _, item in plantilla_df.iterrows():
        field_name = item["nombre"]
        tipo_plant = item["tipo"]
        long_plant = item["longitud"]
        dec_plant = item["decimales"]

        existe = "Sí" if field_name in gdf.columns else "No"
        
        if existe == "Sí":
            # Tipo en pandas/fiona
            fiona_type = fiona_schema.get(field_name, str(gdf[field_name].dtype))
            
            # Parsear tipo y ancho si fiona trae string(50) o float(11.2)
            match_width = re.search(r'\((\d+)(\.(\d+))?\)', str(fiona_type))
            if match_width:
                long_shp = int(match_width.group(1))
                dec_shp = int(match_width.group(3)) if match_width.group(3) else 0
            else:
                long_shp = None
                dec_shp = None

            tipo_shp = map_python_type_to_schema(fiona_type)
            coin_tipo = (tipo_plant == tipo_shp)

            long_correcta = (long_plant == long_shp) if (long_plant is not None and long_shp is not None) else True
            dec_correcto = (dec_plant == dec_shp) if (dec_plant is not None and dec_shp is not None) else True
        else:
            tipo_shp = None
            coin_tipo = False
            long_shp = None
            long_correcta = False
            dec_shp = None
            dec_correcto = False

        rows.append({
            "shape": layer_name,
            "nombre": field_name,
            "Tipo_Plant": tipo_plant,
            "Tipo_Shp": tipo_shp,
            "Existe_Campo": existe,
            "Coin_Tipo_Campo": coin_tipo,
            "Long_Plant": long_plant,
            "Long_Shp": long_shp,
            "Long_Correcta": long_correcta,
            "Dec_Plant": dec_plant,
            "Dec_Shp": dec_shp,
            "Dec_Correcto": dec_correcto,
            "orden_correcto": coincide_orden
        })

    res_df = pd.DataFrame(rows)

    # 2. Validación de Dominios CONAF
    for field_name in gdf.columns:
        if field_name in DOMINIOS_CONAF:
            ok_dom, idx_bad = validate_domain(gdf[field_name], DOMINIOS_CONAF[field_name])
            if not ok_dom:
                logs.append({
                    "capa": layer_name,
                    "tipo": "ERROR",
                    "mensaje": f"Campo '{field_name}' contiene {len(idx_bad)} valores fuera de dominio o vacíos."
                })
            else:
                logs.append({
                    "capa": layer_name,
                    "tipo": "OK",
                    "mensaje": f"Campo de dominio '{field_name}' OK"
                })

    # 3. Verificación de Sup_ha vs geometría
    if "Sup_ha" in gdf.columns:
        # Área en hectáreas
        geom_areas_ha = (gdf.geometry.area / 10000.0).round(2)
        attr_areas = pd.to_numeric(gdf["Sup_ha"], errors='coerce').fillna(0)
        
        dif_relativa = np.abs(geom_areas_ha - attr_areas) / np.maximum(geom_areas_ha, 1e-6)
        bad_areas = (dif_relativa > 0.01)

        if bad_areas.any():
            logs.append({
                "capa": layer_name,
                "tipo": "ERROR",
                "mensaje": f"Hay {bad_areas.sum()} registros con diferencia > 1% entre Sup_ha y el área geométrica recalculada."
            })
        else:
            logs.append({
                "capa": layer_name,
                "tipo": "OK",
                "mensaje": "Superficie Sup_ha coherente con geometría."
            })

    # 4. Verificación de Longitudes de Líneas (Caminos, Hidrografia, LTE, etc.)
    for long_col in ["Long_Cam", "Long_Dren", "Long_LTE", "Long_Curva", "Long_Send"]:
        if long_col in gdf.columns:
            geom_len_m = gdf.geometry.length.round(2)
            attr_len = pd.to_numeric(gdf[long_col], errors='coerce').fillna(0)
            dif_len = np.abs(geom_len_m - attr_len)
            
            if (dif_len > 2.0).any(): # tolerancia 2 metros
                logs.append({
                    "capa": layer_name,
                    "tipo": "WARNING",
                    "mensaje": f"Hay registros donde '{long_col}' difiere en más de 2m de la longitud recalculada."
                })
            else:
                logs.append({
                    "capa": layer_name,
                    "tipo": "OK",
                    "mensaje": f"Campo de longitud '{long_col}' coherente con geometría."
                })

    # 5. Verificación de Coordenadas Coord_X / Coord_Y
    if "Coord_X" in gdf.columns and "Coord_Y" in gdf.columns:
        centroids = gdf.geometry.centroid
        cent_x = centroids.x.round().astype(int)
        cent_y = centroids.y.round().astype(int)

        attr_x = pd.to_numeric(gdf["Coord_X"], errors='coerce').fillna(0).astype(int)
        attr_y = pd.to_numeric(gdf["Coord_Y"], errors='coerce').fillna(0).astype(int)

        bad_coords = (cent_x != attr_x) | (cent_y != attr_y)
        if bad_coords.any():
            logs.append({
                "capa": layer_name,
                "tipo": "ERROR",
                "mensaje": f"Hay {bad_coords.sum()} registros donde Coord_X / Coord_Y difieren del centroide recalculado."
            })
        else:
            logs.append({
                "capa": layer_name,
                "tipo": "OK",
                "mensaje": "Coord_X / Coord_Y coherentes con los centroides de geometría."
            })

    # 6. Caracteres especiales y dobles espacios en campos texto
    text_cols = gdf.select_dtypes(include=['object', 'string']).columns
    for tcol in text_cols:
        series_str = gdf[tcol].dropna().astype(str)
        # Buscar acentos
        has_accents = series_str.str.contains(r"[áéíóúÁÉÍÓÚ'àèìòùÀÈÌÒÙ´`]", regex=True)
        if has_accents.any():
            logs.append({
                "capa": layer_name,
                "tipo": "WARNING",
                "mensaje": f"Campo de texto '{tcol}' contiene acentos o tildes en {has_accents.sum()} filas."
            })

        # Buscar dobles espacios
        has_double_spaces = series_str.str.contains(r"  ", regex=True)
        if has_double_spaces.any():
            logs.append({
                "capa": layer_name,
                "tipo": "WARNING",
                "mensaje": f"Campo de texto '{tcol}' contiene dobles espacios en {has_double_spaces.sum()} filas."
            })

    # 7. Validez Geométrica
    is_valid = gdf.geometry.is_valid
    if not is_valid.all():
        logs.append({
            "capa": layer_name,
            "tipo": "ERROR",
            "mensaje": f"{(~is_valid).sum()} geometrías inválidas (self-intersection o anillos corruptos)."
        })
    else:
        logs.append({"capa": layer_name, "tipo": "OK", "mensaje": "Geometrías válidas."})

    return res_df, logs
