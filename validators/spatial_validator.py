"""
Módulo de Validación Espacial y Topológica
Realiza comprobaciones de superposición, contención de capas, duplicados de ID y genera capas GeoDataFrame de error.
"""

import pandas as pd
import geopandas as gpd
from typing import Dict, List, Tuple, Optional

def validate_spatial_relationships(
    dict_gdfs: Dict[str, gpd.GeoDataFrame],
    nombre_predio: str,
    master_area_corta_gdf: Optional[gpd.GeoDataFrame] = None,
    tol_area: float = 0.005
) -> Tuple[List[Dict[str, str]], Dict[str, gpd.GeoDataFrame]]:
    """
    Ejecuta todas las reglas de negocio y topológicas entre capas vectoriales.
    Retorna:
    - spatial_logs: Lista de eventos y errores detectados.
    - spatial_errors: Diccionario {nombre_capa_error: GeoDataFrame_error} para exportación a GIS.
    """
    spatial_logs: List[Dict[str, str]] = []
    spatial_errors: Dict[str, gpd.GeoDataFrame] = {}

    def get_gdf(prefix: str) -> Tuple[Optional[gpd.GeoDataFrame], str]:
        """Busca una capa por prefijo o nombre completo."""
        for k, gdf in dict_gdfs.items():
            if k == prefix or k == f"{prefix}_{nombre_predio}":
                return gdf, k
        return None, ""

    # =========================================================================
    # 1. VERIFICACIÓN DE ID DUPLICADOS
    # =========================================================================
    shp_area, name_area = get_gdf("Area")
    if shp_area is not None and "N_Area" in shp_area.columns:
        dups = shp_area[shp_area.duplicated("N_Area", keep=False)]
        if not dups.empty:
            spatial_logs.append({
                "capa": name_area, "tipo": "ERROR",
                "mensaje": f"Hay {len(dups)} valores duplicados en el campo N_Area: {dups['N_Area'].unique().tolist()}"
            })
            spatial_errors["duplicados_Area"] = dups
        else:
            spatial_logs.append({"capa": name_area, "tipo": "OK", "mensaje": "Sin duplicados en N_Area"})

    shp_ref, name_ref = get_gdf("Referencia")
    if shp_ref is not None and "Nom_Pto" in shp_ref.columns:
        dups = shp_ref[shp_ref.duplicated("Nom_Pto", keep=False)]
        if not dups.empty:
            spatial_logs.append({
                "capa": name_ref, "tipo": "ERROR",
                "mensaje": f"Hay {len(dups)} valores duplicados en Nom_Pto: {dups['Nom_Pto'].unique().tolist()}"
            })
            spatial_errors["duplicados_Referencia"] = dups
        else:
            spatial_logs.append({"capa": name_ref, "tipo": "OK", "mensaje": "Sin duplicados en Nom_Pto"})

    shp_parc, name_parc = get_gdf("Parcela")
    if shp_parc is not None and "N_Parc" in shp_parc.columns:
        dups = shp_parc[shp_parc.duplicated("N_Parc", keep=False)]
        if not dups.empty:
            spatial_logs.append({
                "capa": name_parc, "tipo": "ERROR",
                "mensaje": f"Hay {len(dups)} valores duplicados en N_Parc: {dups['N_Parc'].unique().tolist()}"
            })
            spatial_errors["duplicados_Parcela"] = dups
        else:
            spatial_logs.append({"capa": name_parc, "tipo": "OK", "mensaje": "Sin duplicados en N_Parc"})

    shp_rod, name_rod = get_gdf("Rodales")
    if shp_rod is not None and "Nom_Predio" in shp_rod.columns and "N_Rodal" in shp_rod.columns:
        rod_keys = shp_rod["Nom_Predio"].astype(str) + " / " + shp_rod["N_Rodal"].astype(str)
        dups_mask = rod_keys.duplicated(keep=False)
        if dups_mask.any():
            spatial_logs.append({
                "capa": name_rod, "tipo": "ERROR",
                "mensaje": f"Hay {dups_mask.sum()} rodales duplicados (Predio/Rodal): {rod_keys[dups_mask].unique().tolist()}"
            })
            spatial_errors["duplicados_Rodales"] = shp_rod[dups_mask]
        else:
            spatial_logs.append({"capa": name_rod, "tipo": "OK", "mensaje": "Sin duplicados en Rodales"})

    # =========================================================================
    # 2. ÁREA DE CORTA VS COMPILADO HISTÓRICO
    # =========================================================================
    if shp_area is not None and master_area_corta_gdf is not None:
        try:
            # Asegurar mismo CRS
            if shp_area.crs != master_area_corta_gdf.crs:
                master_area_corta_gdf = master_area_corta_gdf.to_crs(shp_area.crs)

            inter = gpd.overlay(shp_area, master_area_corta_gdf, how="intersection")
            if not inter.empty:
                inter["area_m2"] = inter.geometry.area
                real_inter = inter[inter["area_m2"] > 1e-4]
                if not real_inter.empty:
                    sup_ha = round(real_inter["area_m2"].sum() / 10000.0, 2)
                    spatial_logs.append({
                        "capa": name_area, "tipo": "ERROR",
                        "mensaje": f"Hay traslape entre el Área de Corta y el compilado histórico: {len(real_inter)} polígonos ({sup_ha} ha)."
                    })
                    spatial_errors["traslape_compilado_corta"] = real_inter
                else:
                    spatial_logs.append({"capa": name_area, "tipo": "OK", "mensaje": "Solo contacto de borde con compilado histórico de corta."})
            else:
                spatial_logs.append({"capa": name_area, "tipo": "OK", "mensaje": "Sin traslape con compilado histórico de corta."})
        except Exception as e:
            spatial_logs.append({"capa": name_area, "tipo": "WARNING", "mensaje": f"Error al procesar intersección con compilado: {e}"})

    # =========================================================================
    # 3. PARCELAS DENTRO DE RODALES Y COINCIDENCIA DE N_RODAL
    # =========================================================================
    if shp_parc is not None and shp_rod is not None:
        try:
            joined = gpd.sjoin(shp_parc, shp_rod, how="left", predicate="within")
            sin_rodal = joined["index_right"].isna()
            
            if sin_rodal.any():
                spatial_logs.append({
                    "capa": name_parc, "tipo": "ERROR",
                    "mensaje": f"{sin_rodal.sum()} parcelas están fuera de la cobertura de Rodales."
                })
                spatial_errors["parcelas_fuera_rodales"] = shp_parc[sin_rodal]
            else:
                spatial_logs.append({"capa": name_parc, "tipo": "OK", "mensaje": "Todas las parcelas están contenidas en Rodales."})

            if "N_Rodal_left" in joined.columns and "N_Rodal_right" in joined.columns:
                inconsistentes = joined[~sin_rodal & (joined["N_Rodal_left"] != joined["N_Rodal_right"])]
                if not inconsistentes.empty:
                    spatial_logs.append({
                        "capa": name_parc, "tipo": "ERROR",
                        "mensaje": f"Hay {len(inconsistentes)} parcelas donde N_Rodal no coincide con el rodal espacial contenedor."
                    })
                    spatial_errors["parcelas_inconsistentes_rodal"] = inconsistentes
                else:
                    spatial_logs.append({"capa": name_parc, "tipo": "OK", "mensaje": "N_Rodal en parcelas coincide exactamente con Rodales."})
        except Exception as e:
            spatial_logs.append({"capa": name_parc, "tipo": "WARNING", "mensaje": f"Error al validar parcelas en rodales: {e}"})

    # =========================================================================
    # 4. CONTENCIÓN EN LÍMITE PREDIAL Y ÁREA DE PROYECTO
    # =========================================================================
    shp_lim, name_lim = get_gdf("Limite_Predial")
    shp_aproj, name_aproj = get_gdf("Area_Proyecto")

    capas_chequeo = ["Area", "Suelos", "Rangos_pend"]
    
    for c_pref in capas_chequeo:
        shp_capa, name_capa = get_gdf(c_pref)
        if shp_capa is None or shp_capa.empty:
            continue

        # Contra Límite Predial
        if shp_lim is not None and not shp_lim.empty:
            try:
                union_lim = shp_lim.geometry.unary_union
                fuera = shp_capa.difference(union_lim)
                fuera_gdf = gpd.GeoDataFrame(geometry=fuera[~fuera.is_empty], crs=shp_capa.crs)
                
                if not fuera_gdf.empty:
                    fuera_gdf["area_m2"] = fuera_gdf.geometry.area
                    fuera_real = fuera_gdf[fuera_gdf["area_m2"] > tol_area]
                    if not fuera_real.empty:
                        total_m2 = round(fuera_real["area_m2"].sum(), 1)
                        total_ha = round(total_m2 / 10000.0, 2)
                        spatial_logs.append({
                            "capa": name_capa, "tipo": "ERROR",
                            "mensaje": f"Superficie fuera de Limite_Predial: {total_m2} m² ({total_ha} ha)."
                        })
                        spatial_errors[f"fuera_limite_{c_pref}"] = fuera_real
                    else:
                        spatial_logs.append({"capa": name_capa, "tipo": "OK", "mensaje": "Sin área fuera de Limite_Predial (dentro de tolerancia)."})
                else:
                    spatial_logs.append({"capa": name_capa, "tipo": "OK", "mensaje": "Completamente contenida en Limite_Predial."})
            except Exception as e:
                spatial_logs.append({"capa": name_capa, "tipo": "WARNING", "mensaje": f"Error al verificar contención en Limite_Predial: {e}"})

        # Contra Área de Proyecto
        if shp_aproj is not None and not shp_aproj.empty:
            try:
                union_aproj = shp_aproj.geometry.unary_union
                fuera = shp_capa.difference(union_aproj)
                fuera_gdf = gpd.GeoDataFrame(geometry=fuera[~fuera.is_empty], crs=shp_capa.crs)
                
                if not fuera_gdf.empty:
                    fuera_gdf["area_m2"] = fuera_gdf.geometry.area
                    fuera_real = fuera_gdf[fuera_gdf["area_m2"] > tol_area]
                    if not fuera_real.empty:
                        total_m2 = round(fuera_real["area_m2"].sum(), 1)
                        total_ha = round(total_m2 / 10000.0, 2)
                        spatial_logs.append({
                            "capa": name_capa, "tipo": "ERROR",
                            "mensaje": f"Superficie fuera de Area_Proyecto: {total_m2} m² ({total_ha} ha)."
                        })
                        spatial_errors[f"fuera_aproj_{c_pref}"] = fuera_real
                    else:
                        spatial_logs.append({"capa": name_capa, "tipo": "OK", "mensaje": "Sin área fuera de Area_Proyecto."})
                else:
                    spatial_logs.append({"capa": name_capa, "tipo": "OK", "mensaje": "Completamente contenida en Area_Proyecto."})
            except Exception as e:
                spatial_logs.append({"capa": name_capa, "tipo": "WARNING", "mensaje": f"Error al verificar contención en Area_Proyecto: {e}"})

    # =========================================================================
    # 5. PREDIOS VECINOS VS LÍMITE PREDIAL
    # =========================================================================
    shp_vec, name_vec = get_gdf("Predios_vecinos")
    if shp_vec is not None and shp_lim is not None:
        try:
            inter_vec = gpd.overlay(shp_vec, shp_lim, how="intersection")
            if not inter_vec.empty:
                inter_vec["area_m2"] = inter_vec.geometry.area
                real_inter = inter_vec[inter_vec["area_m2"] > 1e-4]
                if not real_inter.empty:
                    spatial_logs.append({
                        "capa": name_vec, "tipo": "ERROR",
                        "mensaje": f"Hay traslape entre Predios_vecinos y Limite_Predial ({round(real_inter['area_m2'].sum(),1)} m²)."
                    })
                    spatial_errors["traslape_vecinos_predio"] = real_inter
                else:
                    spatial_logs.append({"capa": name_vec, "tipo": "OK", "mensaje": "Solo contacto de borde entre Predios_vecinos y Limite_Predial."})
            else:
                spatial_logs.append({"capa": name_vec, "tipo": "OK", "mensaje": "Predios_vecinos no se traslapan con Limite_Predial."})
        except Exception as e:
            spatial_logs.append({"capa": name_vec, "tipo": "WARNING", "mensaje": f"Error al verificar predios vecinos: {e}"})

    # =========================================================================
    # 6. INFRAESTRUCTURA AISLADA SOBRE ÁREA DE PROYECTO
    # =========================================================================
    shp_infra, name_infra = get_gdf("Infra_aislada")
    if shp_infra is not None and shp_aproj is not None and "Nom_Infra" in shp_infra.columns:
        cats_rev = ["Control de erosion", "Sacos de tierra", "Bordo de piedra", "Zanja infiltracion", "Empalizada", "Fajina", "Microterraza"]
        shp_rev = shp_infra[shp_infra["Nom_Infra"].isin(cats_rev)]
        
        if not shp_rev.empty:
            try:
                joined = gpd.sjoin(shp_rev, shp_aproj, how="inner", predicate="intersects")
                if not joined.empty:
                    spatial_logs.append({
                        "capa": name_infra, "tipo": "ERROR",
                        "mensaje": f"Hay {len(joined)} elementos de conservación de suelo sobre el Area_Proyecto."
                    })
                    spatial_errors["infra_sobre_aproj"] = joined
                else:
                    spatial_logs.append({"capa": name_infra, "tipo": "OK", "mensaje": "Ninguna obra de conservación se ubica sobre Area_Proyecto."})
            except Exception as e:
                spatial_logs.append({"capa": name_infra, "tipo": "WARNING", "mensaje": f"Error al verificar Infra_aislada: {e}"})

    # =========================================================================
    # 7. CONSISTENCIA DE NOM_PREDIO EN TODAS LAS CAPAS
    # =========================================================================
    if shp_lim is not None and "Nom_Predio" in shp_lim.columns:
        nom_vals = shp_lim["Nom_Predio"].dropna().astype(str).str.strip()
        nom_vals = nom_vals[nom_vals != ""]
        
        if not nom_vals.empty:
            nom_ref = nom_vals.mode()[0]
            for name_k, gdf_k in dict_gdfs.items():
                if "Predios_vecinos" in name_k or "Limite_Comunal" in name_k:
                    continue
                if "Nom_Predio" in gdf_k.columns:
                    vals_k = gdf_k["Nom_Predio"].fillna("").astype(str).str.strip()
                    bad_idx = list(gdf_k.index[(vals_k == "") | (vals_k != nom_ref)])
                    if bad_idx:
                        spatial_logs.append({
                            "capa": name_k, "tipo": "ERROR",
                            "mensaje": f"Nom_Predio no coincide con la referencia '{nom_ref}' en {len(bad_idx)} filas."
                        })
                    else:
                        spatial_logs.append({"capa": name_k, "tipo": "OK", "mensaje": f"Nom_Predio coincide con referencia ('{nom_ref}')."})

    return spatial_logs, spatial_errors
