import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import json
import os
from time import sleep
from tqdm import tqdm
import tempfile

# 👉 USER CONFIG
st.title("Teacher Transfer Tool")
st.write("Upload the school data (XLSX) and provide location details.")

# Upload school data (XLSX)
uploaded_file = st.file_uploader("Upload your school list XLSX", type=["xlsx"])

# Input for user location
USER_LOCATION = st.text_input("Enter your location (e.g., Bapatla, Andhra Pradesh) or press Enter to enter coordinates:")

# Input for category priority
CATEGORY_PRIORITY = st.text_input("Enter category priority (e.g., 4 3 2 1):")
CATEGORY_PRIORITY = list(map(int, CATEGORY_PRIORITY.split())) if CATEGORY_PRIORITY else [4, 3, 2, 1]

USE_COORDS_DIRECTLY = False

# Input for latitude and longitude if coordinates are provided
if not USER_LOCATION:
    lat = st.number_input("Enter your latitude (e.g., 15.902):", value=15.902)
    lon = st.number_input("Enter your longitude (e.g., 80.467):", value=80.467)
    USER_COORDS = (lat, lon)
    USE_COORDS_DIRECTLY = True

DISTRICT = "Guntur"

# 🗂️ Load geocode cache
def load_cache(filename="geo_cache.json"):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache, filename="geo_cache.json"):
    with open(filename, "w") as f:
        json.dump(cache, f)

# 📍 Geocode using Nominatim (with cache)
def geocode_address_nominatim(geolocator, address, cache):
    if address in cache:
        return cache[address]
    try:
        location = geolocator.geocode(address, timeout=10)
        if location:
            coords = (location.latitude, location.longitude)
            cache[address] = coords
            return coords
    except Exception as e:
        print(f"Error for '{address}': {e}")
    return None

# 🧾 Load the data from the XLSX file
def load_xlsx_data(xlsx_file):
    df = pd.read_excel(xlsx_file)
    return df

# 🚀 Main function to process the data
def process(xlsx_file):
    df = load_xlsx_data(xlsx_file)
    
    # Check if the necessary columns exist
    st.write("Available columns in the file:")
    st.write(df.columns)
    
    if not all(col in df.columns for col in ["School", "Mandal", "Category"]):
        raise ValueError("The Excel file must contain columns: 'School', 'Mandal', 'Category'")
    
    geolocator = Nominatim(user_agent="teacher-transfer-tool")
    cache = load_cache()

    st.write("📍 Geocoding user location...")
    if USE_COORDS_DIRECTLY:
        user_coords = USER_COORDS
    else:
        user_coords = geocode_address_nominatim(geolocator, USER_LOCATION + ", Andhra Pradesh", cache)
    if not user_coords:
        raise Exception("❌ Could not geocode user location")

    st.write(f"🧭 Calculating distance for {len(df)} schools...")
    distances = []
    missing_rows = []

    for idx, row in tqdm(df.iterrows(), total=len(df)):
        address = f"{row['School']}, {row['Mandal']}, {DISTRICT}, Andhra Pradesh"
        coords = geocode_address_nominatim(geolocator, address, cache)
        sleep(1)  # Nominatim rate limit
        if coords:
            dist = geodesic(user_coords, coords).km
            distances.append(dist)
        else:
            distances.append(None)
            missing_rows.append(idx)

    save_cache(cache)
    df['Distance_km'] = distances

    # Separate successful and missing geocodes
    df_valid = df.dropna(subset=["Distance_km"]).copy()
    df_missing = df.loc[missing_rows].copy()

    # Process valid geocoded rows
    df_valid['PriorityIndex'] = df_valid['Category'].apply(lambda c: CATEGORY_PRIORITY.index(c))
    df_valid_sorted = df_valid.sort_values(by=["PriorityIndex", "Distance_km"])
    df_valid_sorted = df_valid_sorted[["School", "Mandal", "Category", "Distance_km"]]

    # Process missing geocoded rows using only mandal
    st.write(f"🧭 Calculating distance for missing schools by Mandal...")
    missing_distances = []

    for _, row in tqdm(df_missing.iterrows(), total=len(df_missing)):
        address = f"{row['Mandal']}, {DISTRICT}, Andhra Pradesh"
        coords = geocode_address_nominatim(geolocator, address, cache)
        sleep(1)
        if coords:
            dist = geodesic(user_coords, coords).km
        else:
            dist = None
        missing_distances.append(dist)

    df_missing['Distance_km'] = missing_distances
    df_missing['PriorityIndex'] = df_missing['Category'].apply(lambda c: CATEGORY_PRIORITY.index(c))
    df_missing_sorted = df_missing.sort_values(by=["PriorityIndex", "Distance_km"])
    df_missing_sorted = df_missing_sorted[["School", "Mandal", "Category", "Distance_km"]]

    # Final result without duplicates
    final_df = pd.concat([df_valid_sorted, df_missing_sorted], ignore_index=True)

    # Save output to temporary file
    output_xlsx = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    final_df.to_excel(output_xlsx.name, index=False)

    return output_xlsx.name

if uploaded_file is not None:
    try:
        output_file = process(uploaded_file)

        # Provide download link
        with open(output_file, "rb") as f:
            st.download_button(
                label="Download the processed data as XLSX",
                data=f,
                file_name="sorted_school_distances_with_missing.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    except Exception as e:
        st.error(f"Error: {e}")
