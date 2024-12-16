import pandas as pd
import requests
import re
import boto3
from bs4 import BeautifulSoup
from io import StringIO

# Define your OMDB API Key and S3 bucket name directly in the code
OMDB_API_KEY = ""  # Replace with your actual OMDB API key
S3_BUCKET_NAME = ""  # Replace with your actual S3 bucket name

# Step 1: Scrape Marvel Movie Titles
def scrape_marvel_movies():
    url = "https://en.wikipedia.org/wiki/List_of_Marvel_Cinematic_Universe_films"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    tables = soup.find_all('table', class_='wikitable')
    
    all_data = []
    for i, table in enumerate(tables[:7]):  # Phases 1-6 tables
        headers = [header.text.strip() for header in table.find_all('th')]
        rows = table.find_all('tr')
        data = []
        columns = ['film', 'release_date', 'director', 'writer', 'producer', "status"]
        
        for row in rows:
            cols = row.find_all(['td', 'th'])
            cols = [ele.text.strip() for ele in cols]
            if len(cols) < len(columns):
                cols.extend([None] * (len(columns) - len(cols)))
            elif len(cols) > len(columns):
                cols = cols[:len(columns)]
            data.append(cols)
        
        df = pd.DataFrame(data[1:], columns=columns)  
        df['phase'] = f"Phase {i+1}"
        all_data.append(df)
    
    return pd.concat(all_data, ignore_index=True)


# Step 2: Clean Movie Data
def clean_movie_data(movies_df):
    movies_df['producer'] = movies_df['producer'].fillna(method='ffill')
    movies_df['status'] = movies_df['status'].fillna(method='ffill')
    
    def remove_references(text):
        return re.sub(r'\s*\[\s*\d+\s*\]', '', text)
    
    movies_df_cleaned = movies_df.applymap(lambda cell: remove_references(cell) if isinstance(cell, str) else cell)
    
    movies_df_cleaned['release_date'] = pd.to_datetime(
        movies_df_cleaned['release_date'].str.extract(r'\((.*?)\)')[0], errors='coerce'
    )
    movies_df_cleaned['release_date'] = movies_df_cleaned['release_date'].dt.strftime('%Y-%m-%d')
    
    return movies_df_cleaned


# Step 3 : Scrape Character Data
def fetch_omdb_data(film_name):
    url = f'http://www.omdbapi.com/?t={film_name}&apikey={OMDB_API_KEY}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return {"Title": film_name, "Error": "Data not found"}

# Step 4: Scrape Characters Data
def scrape_characters_data():
    url = "https://en.wikipedia.org/wiki/List_of_Marvel_Cinematic_Universe_films"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    table = None
    
    for tbl in soup.find_all('table', class_='wikitable'):
        caption = tbl.find('caption')
        if caption and "Recurring cast and characters of Marvel Cinematic Universe films" in caption.get_text():
            table = tbl
            break

    if table:
        headers = [th.get_text(strip=True) for th in table.find_all('tr')[0].find_all('th')]
        rows = []
        
        for tr in table.find_all('tr')[1:]:
            row = []
            for td in tr.find_all(['th', 'td']):
                colspan = td.get('colspan')
                if colspan:
                    colspan = int(colspan)
                    row.extend([td.get_text(separator=" ", strip=True)] * colspan)
                else:
                    row.append(td.get_text(separator=" ", strip=True))

            while len(row) < len(headers):
                row.append(None)

            if len(row) > len(headers):
                row = row[:len(headers)]  # Truncate to match header length
            
            rows.append(row)

        return pd.DataFrame(rows, columns=headers)
    else:
        print("Table with specified caption not found.")
        return pd.DataFrame()



# Step 4: Fetch Movie Data from OMDB API

def fetch_omdb_data(film_name):
    url = f'http://www.omdbapi.com/?t={film_name}&apikey={OMDB_API_KEY}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return {"Title": film_name, "Error": "Data not found"}


# Step 5: Upload DataFrames to S3 with specific folder paths
def upload_to_s3(df, file_name):
    s3 = boto3.client('s3')
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    s3.put_object(Bucket=S3_BUCKET_NAME, Key=f"{file_name}", Body=csv_buffer.getvalue())

# Lambda handler function to call each step
def lambda_handler(event, context):
    # Step 1: Scrape movie titles from Wikipedia
    movies_df = scrape_marvel_movies()
    
    # Step 2: Clean the scraped movie data
    movies_df_cleaned = clean_movie_data(movies_df)
    
    # Step 3: Fetch additional movie data from OMDB API
    omdb_results = []
    for film in movies_df_cleaned['film']:
        omdb_data = fetch_omdb_data(film)
        omdb_results.append(omdb_data)
    
    # Convert OMDB results to DataFrame
    omdb_df = pd.DataFrame(omdb_results)

    # Step 4: Scrape characters data
    characters_df = scrape_characters_data()

    # Upload DataFrames to S3 with specified folder paths
    upload_to_s3(movies_df_cleaned, 'movies.csv')
    upload_to_s3(omdb_df, 'omdb.csv')
    upload_to_s3(characters_df, 'characters.csv')
    
    return {
        'statusCode': 200,
        'body': 'Data uploaded successfully!'
    }
