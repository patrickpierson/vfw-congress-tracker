from flask import Flask, render_template
import aws_lambda_wsgi
import csv
import os

app = Flask(__name__)

# Assumes the CSV file is in the same directory as the app.py script.
CSV_FILE_PATH = os.path.join(os.path.dirname(__file__), 'vfw_bills.csv')

@app.route('/')
def home():
    """
    Reads the CSV data and renders the HTML template.
    """
    bills = []
    try:
        with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as csv_file:
            # Use DictReader to read each row as a dictionary
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                bills.append(row)
    except FileNotFoundError:
        return "Error: vfw_bills.csv not found. Please make sure the file is in the same directory.", 404

    # Pass the list of bills to the Jinja2 template for rendering
    return render_template('index.html', bills=bills)

def lambda_handler(event, context):
    return aws_lambda_wsgi.response(app, event, context)

if __name__ == '__main__':
    # To run the app, you will need to install Flask: pip install Flask
    # Then, run this script: python app.py
    # Access the app at http://127.0.0.1:5000/
    app.run(debug=True)
