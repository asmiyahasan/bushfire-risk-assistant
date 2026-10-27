import os

from dotenv import load_dotenv

load_dotenv()  # reads .env locally; does nothing in Azure

USER_AGENT = os.getenv("USER_AGENT", "bushfire-risk-assistant (contact: you@example.com)")

# Storage
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")  # "local" or "azure"
LOCAL_DATA_DIR = os.getenv("LOCAL_DATA_DIR", "../data")
BLOB_CONTAINER = os.getenv("BLOB_CONTAINER", "raw")
AZURE_STORAGE_CONNECTION_STRING = (
    os.getenv("AZURE_STORAGE_CONNECTION_STRING") or os.getenv("AzureWebJobsStorage", "")
)

# Victoria bounding box: west, south, east, north
VIC_BBOX = "140.9,-39.2,150.0,-33.9"

# NASA FIRMS
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "")
FIRMS_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"]

# VicEmergency
VICEMERGENCY_URL = "https://emergency.vic.gov.au/public/events-geojson.json"

# CFA fire district RSS feeds. Check URLs against https://cfa.vic.gov.au/rss-feeds
CFA_RSS_TEMPLATE = "https://www.cfa.vic.gov.au/cfa/rssfeed/{district}-firedistrict_rss.xml"
CFA_DISTRICTS = [
    "mallee", "wimmera", "southwest", "northerncountry", "northcentral",
    "northeast", "central", "eastgippsland", "westandsouthgippsland",
]

# BOM fire danger ratings via anonymous FTP. Confirm the product ID in BOM's FTP listing.
BOM_FDR_PRODUCT_ID = os.getenv("BOM_FDR_PRODUCT_ID", "IDV18555")
BOM_FTP_TEMPLATE = "ftp://ftp.bom.gov.au/anon/gen/fwo/{product_id}.xml"
