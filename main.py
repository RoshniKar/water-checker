# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import math
import threading
import time
import requests  # ⬅️ NEW import for logging

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load pincode→hardness map
with open("pincode_water_hardness.json", "r") as f:
    hardness_map = json.load(f)

# Load pincode→city map
with open("pincode_to_city.json", "r") as f:
    pincode_to_city = json.load(f)

# Create city→pincodes mapping (for fallback)
city_to_pincodes = {}
for pincode, city in pincode_to_city.items():
    if city not in city_to_pincodes:
        city_to_pincodes[city] = []
    city_to_pincodes[city].append(pincode)

# Create hardness list for percentile calculation
all_ppms = [v["ppm"] for v in hardness_map.values() if v["ppm"] is not None]
mu_final = sum(all_ppms) / len(all_ppms)
sigma = (sum((x - mu_final) ** 2 for x in all_ppms) / len(all_ppms)) ** 0.5


# 🔹 Logging function
def log_to_sheet(pincode, city, ppm):
    if str(pincode) != "400001":  
        url = "https://script.google.com/macros/s/AKfycbye69XWAyYnrWOOpKlSr_ipd1d7O9SrKsZ5dMeHfygvFHMZCsXhIzRbUIf-NdPIhvrkfQ/exec"  
        payload = {"pincode": pincode, "city": city, "ppm": ppm}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print("❌ Failed to log to Google Sheet:", e)


@app.get("/water-check")
def check_water(pincode: str):
    ppm = None
    city = None

    # 1. Try exact pincode
    if pincode in hardness_map:
        ppm = hardness_map[pincode]["ppm"]
        city = hardness_map[pincode]["city"]
    else:
        # 2. Try same city → pick highest ppm
        if pincode in pincode_to_city:
            fallback_city = pincode_to_city[pincode]
            max_ppm = -1
            best_pin = None

            for other_pin in city_to_pincodes.get(fallback_city, []):
                if other_pin in hardness_map:
                    this_ppm = hardness_map[other_pin]["ppm"]
                    if this_ppm is not None and this_ppm > max_ppm:
                        max_ppm = this_ppm
                        ppm = this_ppm
                        best_pin = other_pin

            if max_ppm > -1:
                city = fallback_city

        # 3. Try any other pincode as final fallback
        if ppm is None:
            for data in hardness_map.values():
                if data["ppm"]:
                    ppm = data["ppm"]
                    city = data["city"]
                    break

    if ppm is None:
        raise HTTPException(status_code=404, detail="No fallback available")

    # Calculate percentile (like HelloKlean)
    percentile = 100 / (1 + math.exp(-(ppm - mu_final) / sigma))

    # 🔹 Log request to Google Sheet
    log_to_sheet(pincode, city, ppm)

    return [{
        "city": city,
        "pincode": pincode,
        "wasserhaerte_avg": ppm,
        "Hardness-unit": "ppm",
        "mu_final": mu_final,
        "sigma": sigma,
        "h_ppm": ppm,
        "hardness_percentile": percentile
    }]
