import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import json
import os
from time import sleep
from io import BytesIO
from tqdm import tqdm

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
def load_xlsx_data(xlsx_path):
    df = pd.read_excel(xlsx_path)
    return df

# 🚀 Main function to process the data
def process(xlsx_file, user_coords, category_priority):
    df = load_xlsx_data(xlsx_file)
    
    if not all(col in df.columns for col in ["School", "Mandal", "Category"]):
        st.error("The Excel file must contain columns: 'School', 'Mandal', 'Category'")
        return None
    
    geolocator = Nominatim(user_agent="teacher-transfer-tool")
    cache = load_cache()

    st.write("📍 Geocoding user location...")
    if not user_coords:
        st.error("❌ Could not geocode user location")
        return None

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

    # Separate valid and missing geocoded rows
    df_valid = df.dropna(subset=["Distance_km"]).copy()
    df_missing = df.loc[missing_rows].copy()

    # Process valid geocoded rows
    df_valid['PriorityIndex'] = df_valid['Category'].apply(lambda c: category_priority.index(c))
    df_valid_sorted = df_valid.sort_values(by=["PriorityIndex", "Distance_km"])
    df_valid_sorted = df_valid_sorted[["School", "Mandal", "Category", "Distance_km"]]

    # Process missing geocoded rows using only mandal
    st.write("🧭 Calculating distance for missing schools by Mandal...")
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
    df_missing['PriorityIndex'] = df_missing['Category'].apply(lambda c: category_priority.index(c))
    df_missing_sorted = df_missing.sort_values(by=["PriorityIndex", "Distance_km"])
    df_missing_sorted = df_missing_sorted[["School", "Mandal", "Category", "Distance_km"]]

    # Final result without duplicates
    final_df = pd.concat([df_valid_sorted, df_missing_sorted], ignore_index=True)

    # Save the final output to a BytesIO buffer
    output = BytesIO()
    final_df.to_excel(output, index=False)
    output.seek(0)  # Seek to the beginning of the BytesIO object
    
    return output

# Streamlit UI
# Adding custom CSS for UI enhancement
st.markdown("""
    <style>
        .main {
            background-color: #F3E6FF;
            color: #5A2A83;
            font-family: 'Arial', sans-serif;
        }
        .stButton>button {
            background-color: #9B77E4;
            color: white;
            border-radius: 12px;
            padding: 12px 25px;
            font-size: 16px;
        }
        h1 {
            color: #6A2D9B;
            font-size: 40px;
            text-align: center;
            font-weight: 600;
        }
        .stTextInput>label {
            color: #6A2D9B;
        }
        .stFileUploader>label {
            color: #6A2D9B;
        }
        .stDownloadButton>button {
            background-color: #9B77E4;
            color: white;
            border-radius: 12px;
            padding: 12px 25px;
            font-size: 16px;
        }
        .header-image {
            width: 100%;
            height: auto;
            border-radius: 10px;
            object-fit: cover;
        }
    </style>
""", unsafe_allow_html=True)

# Adding an image at the top for the background
st.image('https://via.placeholder.com/800x400.png?text=Teacher+Transfer+System', caption='School System', use_column_width=True)

st.title("Teacher Transfer Tool")

uploaded_file = st.file_uploader("Upload your school list (XLSX)", type=["xlsx"])

if uploaded_file:
    # Get user location input
    user_location = st.text_input("Enter your location (e.g., Bapatla, Andhra Pradesh) or press Enter to enter coordinates:")
    
    if user_location:
        # Geolocate user input address
        geolocator = Nominatim(user_agent="teacher-transfer-tool")
        cache = load_cache()
        user_coords = geocode_address_nominatim(geolocator, user_location + ", Andhra Pradesh", cache)
        
        if user_coords:
            category_priority = list(map(int, st.text_input("Enter category priority (e.g., 4 3 2 1)").split()))
            if not category_priority:
                category_priority = [4, 3, 2, 1]
            result_file = process(uploaded_file, user_coords, category_priority)
            
            if result_file:
                st.download_button(
                    "Download Sorted List", 
                    result_file, 
                    "sorted_school_distances_with_missing.xlsx", 
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.error("❌ Could not geocode user location")
    else:
        # Get latitude and longitude inputs
        lat = st.number_input("Enter latitude (e.g., 15.902):", format="%.6f")
        lon = st.number_input("Enter longitude (e.g., 80.467):", format="%.6f")
        
        user_coords = (lat, lon)
        category_priority = [4, 3, 2, 1]
        result_file = process(uploaded_file, user_coords, category_priority)
        
        if result_file:
            st.download_button(
                "Download Sorted List", 
                result_file, 
                "sorted_school_distances_with_missing.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
