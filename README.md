# True Inflation Canada

A free, real-time Canadian inflation tracker that aggregates data from official and alternative sources to provide a transparent view of price changes.

![Dashboard Preview](dashboard_preview.png)

## 📊 Live Data Sources (100% Free)

We track inflation across 4 key categories using **zero-cost** data pipelines:

| Category | Source | Method | Status |
|----------|--------|--------|--------|
| **Headline** | **Bank of Canada** | Valet API (`V41690973`) | ✅ Live |
| **Food** | **OpenFoodFacts** | Public API | ✅ Live |
|          | **StatCan Retail**| CSV Download (22 staples) | ✅ Live |
|          | **Loblaws** | Apify Scraper (Superstore) | ✅ Live |
| **Housing** | **StatCan** | CSV Download (Shelter/Rent/Owned) | ✅ Live |
| **Transport**| **StatCan** | CSV Download (Gasoline) | ✅ Live |
| **Energy** | **OEB** | Web Scraper (Ontario Rates) | ✅ Live |

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- (Optional) Apify Account for daily grocery scraping

### Installation

1.  **Clone the repo**
    ```bash
    git clone https://github.com/lucasbarnes96/truenorth-index.git true-inflation-canada
    cd true-inflation-canada
    ```

2.  **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: You might need `pip install apify-client` manually)*

3.  **Setup Apify (Optional)**
    - Sign up at [Apify](https://apify.com/).
    - Subscribe to the `sunny_eternity/loblaws-grocery-scraper` actor.
    - Click **Start** once to initialize it.
    - Save your token in `.env`: `APIFY_TOKEN=...`
    - See [APIFY_SETUP.md](APIFY_SETUP.md) for details.

### Usage

1.  **Run the Data Pipeline**
    ```bash
    python3 process.py
    ```
    This fetches data from all sources, processes it, and updates `data/latest.json`.

2.  **Launch the Dashboard**
    ```bash
    python3 -m http.server
    ```
    Open `http://localhost:8000` in your browser.

## 🛠️ Architecture

- **`scrapers/`**: Individual scripts for each data source.
  - `bank_of_canada.py`: Fetches official CPI.
  - `grocery_apify.py`: Connects to Loblaws via Apify.
  - `food_statcan.py`: Downloads retail food prices.
- **`process.py`**: Main orchestrator. Aggregates quotes, handles outliers, and calculates the index.
- **`index.html`**: Zero-dependency dashboard (Chart.js + Vanilla JS).
- **`data/`**: JSON storage for latest and historical data (no database required).

## 📄 License
MIT
