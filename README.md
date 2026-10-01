# 🌲 Control de Calidad Cartográfica PAS / CONAF (Python Web App)

Aplicación web desarrollada en **Python (Streamlit + GeoPandas + Shapely)** para la validación automática, auditoría de tablas de atributos y relaciones topológicas espaciales de capas vectoriales (Shapefiles) según el protocolo de la **Corporación Nacional Forestal (CONAF)** en Chile.

---

## ✨ Características Principales

- **Independiente de R y QGIS**: No requiere R, paquetes R ni instaladores externos de GDAL/QGIS.
- **Estructura Modular**: Separación limpia entre plantillas CONAF, validadores de atributos, validadores espaciales e interfaz web.
- **Validación Atributular y Geométrica**:
  - Proyección `EPSG:32719` (WGS84 / UTM 19S).
  - Verificación de dimensión 2D (sin coordenadas Z/M).
  - Coincidencia con plantilla CONAF (nombres de campos, tipos, largo de columna DBF, decimales y orden exacto).
  - Recálculo de superficie `Sup_ha` vs geometría de polígonos.
  - Recálculo de longitudes en metros para capas lineales (`Caminos`, `Hidrografia`, `LTE_HVDC`).
  - Coordenadas de centroides (`Coord_X`, `Coord_Y`).
  - Limpieza de texto (detección de acentos/tildes y dobles espacios).
- **Validaciones Espaciales y Topológicas**:
  - Detección de IDs duplicados.
  - Traslape con compilados de área de corta.
  - Inclusión de parcelas en rodales y coincidencia de `N_Rodal`.
  - Contención de superficies en Límite Predial y Área de Proyecto.
  - Verificación de predios vecinos e infraestructura aislada.
- **Entregables Automatizados**:
  - Descarga de **Reporte Consolidado en Excel (`.xlsx`)** con colores de estado (OK/Error).
  - Descarga de **Shapefile de Errores Espaciales (`.zip`)** para cargar en QGIS/ArcGIS.
  - Visor interactivo de mapas con **Folium**.

---

## 🛠️ Instalación y Uso

### 1. Clonar el repositorio
```bash
git clone https://github.com/ramirezmaps/script-pas.git
cd script-pas
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Ejecutar la aplicación web
```bash
streamlit run app.py
```
Abre tu navegador web en `http://localhost:8501`.

---

## 📂 Estructura del Proyecto

```
script-pas/
├── app.py                      # Interfaz gráfica web principal (Streamlit)
├── config/
│   └── templates.py            # Plantillas de capas CONAF y dominios permitidos
├── validators/
│   ├── attribute_validator.py  # Módulo de validaciones atributulares y numéricas
│   └── spatial_validator.py    # Módulo de validaciones espaciales y topología
├── utils/
│   ├── loader.py               # Lector de archivos Shapefile o compresión ZIP
│   └── exporter.py             # Generador de reportes Excel y capas ZIP de error
├── requirements.txt            # Librerías de Python requeridas
└── README.md                   # Documentación del proyecto
```
