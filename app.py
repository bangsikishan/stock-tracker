import os
from datetime import datetime, timedelta, timezone
from itertools import groupby
from operator import itemgetter

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_supabase import Supabase

current_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(current_dir, ".env")
load_dotenv(dotenv_path=dotenv_path)

app = Flask(__name__)

app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
app.config["SUPABASE_KEY"] = os.getenv("SUPABASE_KEY")

supabase_ext = Supabase(app)


def get_today_timestamp():
    # Define your timezone UTC+05:45
    offset_minutes = 5 * 60 + 45
    tz = timezone(timedelta(minutes=offset_minutes))

    # Get current local datetime with timezone
    now = datetime.now(tz)

    # Convert to UTC and get Unix timestamp
    now_utc = now.astimezone(timezone.utc)
    return int(now_utc.timestamp())


@app.route("/")
def home():
    # Fetch all records
    response = supabase_ext.client.from_("stocks").select("*").execute()
    stocks_list = response.data or []

    # Transform each stock record: add `total_value` and parse `date`
    for stock in stocks_list:
        # Ensure keys exist and are valid
        stock["price"] = float(stock.get("price", 0))
        stock["quantity"] = int(stock.get("unit", 0))  # Convert 'units' -> 'quantity'
        stock["total_value"] = stock["price"] * stock["unit"]

        # Rename or default missing fields
        raw_date = stock.get("purchased_at")
        try:
            stock["date"] = datetime.strptime(raw_date, "%Y-%m-%d")
        except Exception:
            stock["date"] = datetime.now()

        stock["profit_loss"] = stock.get("profit_loss", None)
        stock["symbol"] = stock.get("symbol", "N/A")

    # Compute total value and total unique symbols
    total_value = sum(stock["price"] * stock["unit"] for stock in stocks_list)
    unique_symbols = {stock["symbol"] for stock in stocks_list if stock["symbol"]}
    total_stocks = len(unique_symbols)

    symbol_opening_prices = {}
    timestamp = get_today_timestamp()
    for symbol in unique_symbols:
        response = requests.get(
            f"https://merolagani.com/handlers/TechnicalChartHandler.ashx?type=get_advanced_chart&symbol={symbol}&resolution=1D&rangeStartDate=1719121913&rangeEndDate={timestamp}&from=&isAdjust=1&currencyCode=NPR",
        )

        try:
            symbol_opening_prices[symbol] = float(response.json().get("o")[-1])
        except (TypeError, IndexError, ValueError):
            symbol_opening_prices[symbol] = None

    for stock in stocks_list:
        opening_price = symbol_opening_prices.get(stock["symbol"])
        if opening_price is not None:
            stock["profit_loss"] = round(
                (opening_price - stock["price"]) * stock["quantity"], 2
            )

    # Sort and group by symbol
    stocks_list.sort(key=itemgetter("symbol"))
    grouped_stocks = {
        symbol: list(items)
        for symbol, items in groupby(stocks_list, key=itemgetter("symbol"))
    }

    return render_template(
        "index.html",
        grouped_stocks=grouped_stocks,
        total_stocks=total_stocks,
        total_value=total_value,
    )


@app.route("/add")
def add():
    return render_template("input-form.html")


@app.route("/submit_data", methods=["POST"])
def submit_data():
    if request.is_json:
        data = request.json

        record = {
            "symbol": data.get("symbol"),
            "price": data.get("price"),
            "unit": data.get("quantity"),
            "purchased_at": data.get("date"),
        }

        response = supabase_ext.client.from_("stocks").insert(record).execute()

        if response.data:
            return jsonify({"redirect_url": url_for("home")})
        else:
            return jsonify({"error": "Insert failed", "details": response.data}), 400
    else:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400


@app.route("/delete/<int:stock_id>", methods=["POST"])
def delete(stock_id):
    # Attempt to delete the stock with the given stock_id
    _ = supabase_ext.client.from_("stocks").delete().eq("id", stock_id).execute()

    # Redirect back to the home page after deletion
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
