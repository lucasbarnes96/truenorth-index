# Apify Loblaws Scraper Setup Guide

To get daily grocery prices from Loblaws (Superstore, No Frills) flowing into the TrueNorth Index, follow these steps:

## 1. Apify Account & Toxic
- **Log in** to [Apify Console](https://console.apify.com/).
- **Get your API Token**: Go to Settings > Integrations > API Token.
- **Save it**: Ensure your token is saved in the `.env` file in the project root:
  ```bash
  APIFY_TOKEN=your_token_here
  ```

## 2. Subscribe/Initialize the Actor
1. Go to the [Loblaws Grocery Scraper](https://apify.com/sunny_eternity/loblaws-grocery-scraper) page.
2. **IMPORTANT**: Click the green **Start** button once! You can stop it immediately after it starts.
   - *Why?* This "links" the actor to your account so the API can find it later. Without this step, you might see an "Actor not found" error.
3. You do **not** need to use the "API" dropdown menu (API clients, endpoints, etc.)—my Python script handles all that for you.

## 3. Configure the Scraper (Optional)
The current script (`scrapers/grocery_apify.py`) is configured to scrape the **Dairy & Eggs** category from **Real Canadian Superstore** to track basic staples.

If you want to change this:
1. Open `scrapers/grocery_apify.py`.
2. Update the `category_url` variable with a different category from [realcanadiansuperstore.ca](https://www.realcanadiansuperstore.ca/).
3. You can also change `maxItems` to control costs (currently set to 50 items per run).

## 4. Running it
The pipeline (`process.py`) automatically attempts to run the Apify scraper.
- **To test manually**:
  ```bash
  python3 -c "from scrapers.grocery_apify import scrape_grocery_apify; print(scrape_grocery_apify())"
  ```
- **Cost**: Each run costs a fraction of a cent. Monitor your usage in the Apify Console.

## Troubleshooting
- **"Actor not found"**: Make sure you have "rented" or added the actor to your account in the Apify console.
- **"Input is not valid"**: The actor requires a `categoryUrl`. If you change the input, ensure you provide a valid Loblaws category URL.
