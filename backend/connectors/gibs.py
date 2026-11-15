"""NASA GIBS imagery layer catalogue used by the globe. Tiles are fetched directly by
the browser from gibs.earthdata.nasa.gov (WMTS, EPSG:4326). No key required."""

LAYERS = [
    {"id": "MODIS_Terra_CorrectedReflectance_TrueColor", "name": "True colour (Terra/MODIS)", "group": "imagery", "matrix": "250m", "fmt": "jpg", "max": 8, "daily": True, "since": "2000-02-24"},
    {"id": "VIIRS_SNPP_CorrectedReflectance_TrueColor", "name": "True colour (SNPP/VIIRS)", "group": "imagery", "matrix": "250m", "fmt": "jpg", "max": 8, "daily": True, "since": "2015-11-24"},
    {"id": "VIIRS_SNPP_DayNightBand_At_Sensor_Radiance", "name": "Night lights (VIIRS day/night band)", "group": "imagery", "matrix": "500m", "fmt": "png", "max": 7, "daily": True, "since": "2016-11-30"},
    {"id": "MODIS_Terra_Land_Surface_Temp_Day", "name": "Land surface temperature, day", "group": "temperature", "matrix": "1km", "fmt": "png", "max": 6, "daily": True, "since": "2002-07-04"},
    {"id": "GHRSST_L4_MUR_Sea_Surface_Temperature", "name": "Sea surface temperature (MUR L4)", "group": "ocean", "matrix": "1km", "fmt": "png", "max": 6, "daily": True, "since": "2002-06-01"},
    {"id": "IMERG_Precipitation_Rate", "name": "Precipitation rate (GPM IMERG)", "group": "precipitation", "matrix": "2km", "fmt": "png", "max": 5, "daily": True, "since": "2000-06-01"},
    {"id": "MODIS_Terra_NDVI_8Day", "name": "Vegetation index NDVI (8-day)", "group": "vegetation", "matrix": "250m", "fmt": "png", "max": 8, "daily": True, "since": "2000-02-18"},
    {"id": "MODIS_Terra_Thermal_Anomalies_All", "name": "Fires & thermal anomalies (MODIS)", "group": "wildfires", "matrix": "1km", "fmt": "png", "max": 6, "daily": True, "since": "2000-11-01"},
    {"id": "MODIS_Terra_Aerosol", "name": "Aerosol optical depth (MODIS)", "group": "air", "matrix": "2km", "fmt": "png", "max": 5, "daily": True, "since": "2000-02-24"},
    {"id": "MODIS_Terra_Snow_Cover", "name": "Snow cover (MODIS)", "group": "snowice", "matrix": "500m", "fmt": "png", "max": 7, "daily": True, "since": "2000-02-24"},
    {"id": "AMSR2_Sea_Ice_Concentration_12km", "name": "Sea ice concentration (AMSR2)", "group": "snowice", "matrix": "2km", "fmt": "png", "max": 5, "daily": True, "since": "2012-07-02"},
    {"id": "SMAP_L3_Passive_Soil_Moisture_Day", "name": "Soil moisture (SMAP L3)", "group": "soil", "matrix": "2km", "fmt": "png", "max": 5, "daily": True, "since": "2015-03-31"},
    {"id": "MERRA2_2m_Air_Temperature_Monthly", "name": "2 m air temperature, monthly (MERRA-2)", "group": "temperature", "matrix": "2km", "fmt": "png", "max": 5, "daily": True, "since": "1980-01-01"},
    {"id": "MODIS_Terra_Cloud_Top_Temp_Day", "name": "Cloud-top temperature (MODIS)", "group": "air", "matrix": "2km", "fmt": "png", "max": 5, "daily": True, "since": "2000-02-24"},
    {"id": "CERES_EBAF_TOA_Net_Flux_Monthly", "name": "TOA net flux, monthly (CERES EBAF)", "group": "solar", "matrix": "2km", "fmt": "png", "max": 5, "daily": True, "since": "2000-03-01"},
    {"id": "BlueMarble_ShadedRelief_Bathymetry", "name": "Blue Marble (base)", "group": "base", "matrix": "500m", "fmt": "jpeg", "max": 7, "daily": False, "since": None},
]

def catalogue():
    return LAYERS