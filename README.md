# Cardux's Motorbike Report

A Python application for scraping motorbike listings from [Moto.it](https://www.moto.it), generating an interactive HTML report with price vs. year analysis, a map of listing locations, and detailed statistics. Features a user-friendly Tkinter GUI.

## Features
- **Web Scraping**: Extracts motorbike listings from Moto.it, including year, price, mileage (km), and location.
- **Robust Parsing**: Accurately extracts years and mileage using regex patterns, with fallback verification on listing detail pages.
- **Interactive Report**: Generates an HTML report with:
  - Scatter plot (Price vs. Year)
  - Line plot (Average price per year)
  - Interactive map of listing locations (via OpenStreetMap/Nominatim)
  - Detailed tables for statistics and listings
- **GUI**: Tkinter-based interface for inputting brand, model, or Moto.it search URL, with options for max pages, request delay, and output directory.
- **Output**: Saves results as a CSV file (`annunci_motoit.csv`) and an HTML report (`report_motoit.html`) in a model-specific folder on the Desktop by default.
- **Credit**: Includes a clickable Instagram link to [@fuori.tempo.massimo](https://www.instagram.com/fuori.tempo.massimo).

## Prerequisites
- **Python**: Version 3.7 or higher
- **Dependencies**:
  ```bash
  pip install requests beautifulsoup4 pandas plotly lxml
  ```
- **Tkinter**: Usually included with Python; ensure it's installed (e.g., `python3-tk` on Linux).
- **Internet Connection**: Required for scraping and map geocoding in the HTML report.

## Installation
1. Clone or download this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   Or manually:
   ```bash
   pip install requests beautifulsoup4 pandas plotly lxml
   ```
3. Run the script:
   ```bash
   python motorbike_report.py
   ```

## Usage
1. Launch the application:
   ```bash
   python motorbike_report.py
   ```
2. In the GUI:
   - Enter the motorbike **Brand** and **Model** (e.g., "Honda" and "CBR 650 R"), or paste a Moto.it search URL.
   - Adjust **Max Pages** (default: 12) and **Request Delay** (default: 1.0s) as needed.
   - Enable/disable **Verify Year on Detail Page** for more accurate year extraction.
   - Choose an output directory (defaults to `Desktop/<model>`).
3. Click **Generate Report** to scrape data and create the report.
4. Use **Open Report** to view the HTML report in a browser or **Open Folder** to access the output directory.
5. Check the **Help** button for detailed usage instructions and troubleshooting.

## Output
- **CSV File**: `annunci_motoit.csv` contains all scraped listings with columns: `brand`, `model`, `year`, `price_eur`, `km`, `location`, `source_url`.
- **HTML Report**: `report_motoit.html` includes:
  - Scatter and line plots for price analysis.
  - A map showing listing locations (requires internet for geocoding).
  - Tables for per-year statistics and full listing details.
  - Interactive DataTables for sorting and filtering.

## Notes
- **Respectful Scraping**: The script includes a configurable delay to avoid overloading Moto.it's servers. Keep the delay at 1.0s or higher.
- **Error Handling**: Check the GUI log for errors (e.g., network issues, invalid URLs). Common fixes are in the Help section.
- **Geocoding**: The map uses Nominatim (OpenStreetMap) for geocoding, which requires an internet connection when opening the report.
- **Dependencies**: Ensure `lxml` is installed for faster HTML parsing with BeautifulSoup.

## Troubleshooting
- **No listings found**: Verify the URL or brand/model; reduce max pages or check Moto.it's site structure.
- **Scraping timeout**: Increase the request delay or check your internet connection.
- **Incorrect year/km**: Ensure "Verify Year on Detail Page" is enabled; check the CSV for specific listing issues.
- **Map not loading**: Ensure internet access when opening the report; allow a few seconds for geocoding.

## Credits
Developed by Cardux. Follow on Instagram: [@fuori.tempo.massimo](https://www.instagram.com/fuori.tempo.massimo).

## License
This project is licensed under no license, because it's just an amateur project. Use it as you wish!
