"""
Módulo de Carga de Archivos Espaciales
Permite cargar Shapefiles desde directorios locales o desde archivos ZIP subidos por el usuario.
"""

import os
import glob
import tempfile
import zipfile
import geopandas as gpd
from typing import Dict, Tuple, List, Optional
import fiona

def map_python_type_to_schema(dtype_str: str) -> str:
    """Mapea el tipo de dato de Pandas/Fiona al tipo esperado por la plantilla ('character', 'numeric', 'integer')."""
    s = str(dtype_str).lower()
    if any(t in s for t in ['int', 'int64', 'int32', 'int16']):
        return 'integer'
    elif any(t in s for t in ['float', 'float64', 'float32', 'double', 'real', 'numeric']):
        return 'numeric'
    else:
        return 'character'

def read_shapefiles_from_directory(directory_path: str, predio_name: str) -> Tuple[Dict[str, gpd.GeoDataFrame], Dict[str, Dict], List[str]]:
    """
    Lee todos los archivos Shapefile (.shp) dentro de un directorio.
    Retorna:
    - dict_gdfs: Diccionario {nombre_capa: GeoDataFrame}
    - dict_meta: Metadatos fiona {nombre_capa: metadata_fiona}
    - files_found: Lista de nombres base encontrados
    """
    shp_files = glob.glob(os.path.join(directory_path, "**", "*.shp"), recursive=True)
    dict_gdfs = {}
    dict_meta = {}
    files_found = []

    for shp_path in shp_files:
        base_name = os.path.splitext(os.path.basename(shp_path))[0]
        files_found.append(base_name)
        try:
            # Leer el GeoDataFrame
            gdf = gpd.read_file(shp_path)
            dict_gdfs[base_name] = gdf

            # Leer metadatos de esquema nativos con Fiona (ancho de columna y tipo DBF real)
            with fiona.open(shp_path) as src:
                dict_meta[base_name] = {
                    "crs": src.crs,
                    "schema": src.schema,
                    "driver": src.driver
                }
        except Exception as e:
            print(f"Error al leer shapefile {shp_path}: {e}")

    return dict_gdfs, dict_meta, files_found

def extract_and_read_zip(uploaded_zip_file, predio_name: str) -> Tuple[Dict[str, gpd.GeoDataFrame], Dict[str, Dict], List[str], tempfile.TemporaryDirectory]:
    """
    Extrae un archivo ZIP subido y lee todos sus shapefiles.
    Mantiene la carpeta temporal viva mediante el objeto retornado.
    """
    temp_dir = tempfile.TemporaryDirectory()
    zip_path = os.path.join(temp_dir.name, "upload.zip")

    with open(zip_path, "wb") as f:
        f.write(uploaded_zip_file.getbuffer())

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir.name)

    dict_gdfs, dict_meta, files_found = read_shapefiles_from_directory(temp_dir.name, predio_name)
    return dict_gdfs, dict_meta, files_found, temp_dir
