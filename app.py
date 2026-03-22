"""
Villa Ranking Web App
- Paste Airbnb/Booking links → auto-scrape details
- Click-based 1-5 star voting
- Auto-sort by average rating
"""

from flask import Flask, render_template, request, jsonify
import json, os, re, time, hashlib
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

app = Flask(__name__, template_folder='templates', static_folder='static')

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')
VOTERS = ["Lorenz", "Jan", "Levent", "Grappe", "Nicola", "Rapha", "Flo", "Ferdi"]

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"villas": []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def scrape_airbnb(url):
    """Scrape Airbnb listing details."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'
        }
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        info = {
            "source": "airbnb",
            "name": "",
            "location": "",
            "guests": "",
            "bedrooms": "",
            "beds": "",
            "bathrooms": "",
            "price": "",
            "rating": "",
            "reviews": "",
            "amenities": [],
            "image": "",
            "checkin": "",
            "checkout": "",
        }
        
        # Parse URL params for dates
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        info["checkin"] = params.get("check_in", params.get("checkin", [""]))[0]
        info["checkout"] = params.get("check_out", params.get("checkout", [""]))[0]
        if "adults" in params:
            info["guests"] = params["adults"][0]
        
        # Try to find JSON-LD or meta tags
        title_tag = soup.find('title')
        if title_tag:
            info["name"] = title_tag.text.strip().split(' - ')[0].split('·')[0].strip()
        
        # Meta description often has details
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            desc = meta_desc.get('content', '')
            info["location"] = desc[:100] if desc else ""
            
            # Extract guest/bedroom info from description
            guest_match = re.search(r'(\d+)\s*(?:Gäste|guests|Personen)', desc, re.I)
            if guest_match:
                info["guests"] = guest_match.group(1)
            
            bed_match = re.search(r'(\d+)\s*(?:Schlafzimmer|bedrooms?)', desc, re.I)
            if bed_match:
                info["bedrooms"] = bed_match.group(1)
        
        # Try to find price in page
        price_match = re.search(r'[€$£CHF]\s*[\d,\.]+|[\d,\.]+\s*[€$£]', resp.text)
        if price_match:
            info["price"] = price_match.group(0)
        
        # OG image
        og_image = soup.find('meta', property='og:image')
        if og_image:
            info["image"] = og_image.get('content', '')
        
        # OG title (usually better)
        og_title = soup.find('meta', property='og:title')
        if og_title:
            info["name"] = og_title.get('content', '').split(' - ')[0].strip()
        
        # Try JSON-LD
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                ld = json.loads(script.string)
                if isinstance(ld, dict):
                    if 'name' in ld:
                        info["name"] = ld["name"]
                    if 'address' in ld:
                        addr = ld["address"]
                        if isinstance(addr, dict):
                            info["location"] = f"{addr.get('addressLocality', '')}, {addr.get('addressCountry', '')}"
                    if 'aggregateRating' in ld:
                        info["rating"] = str(ld["aggregateRating"].get("ratingValue", ""))
                        info["reviews"] = str(ld["aggregateRating"].get("reviewCount", ""))
                    if 'image' in ld:
                        imgs = ld["image"]
                        if isinstance(imgs, list) and imgs:
                            info["image"] = imgs[0]
                        elif isinstance(imgs, str):
                            info["image"] = imgs
            except:
                pass
        
        # Amenities from page text
        amenity_keywords = {
            "Pool": ["pool", "swimming"],
            "Fitness": ["gym", "fitness", "workout"],
            "Sauna": ["sauna"],
            "Strand": ["beach", "strand", "beachfront", "oceanfront"],
            "Küche": ["kitchen", "küche", "cooking"],
            "Parkplatz": ["parking", "parkplatz", "garage"],
            "WLAN": ["wifi", "wlan", "internet", "wi-fi"],
            "Klimaanlage": ["air conditioning", "klimaanlage", "AC", "a/c"],
            "Waschmaschine": ["washer", "washing", "waschmaschine"],
            "Jacuzzi": ["hot tub", "jacuzzi", "whirlpool"],
            "Grill": ["bbq", "grill", "barbecue"],
            "Meerblick": ["sea view", "ocean view", "meerblick"],
        }
        
        page_text = resp.text.lower()
        for amenity, keywords in amenity_keywords.items():
            for kw in keywords:
                if kw.lower() in page_text:
                    info["amenities"].append(amenity)
                    break
        
        return info
    except Exception as e:
        return {"source": "airbnb", "name": f"Fehler: {str(e)}", "error": True}

def scrape_booking(url):
    """Scrape Booking.com listing details."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'
        }
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        info = {
            "source": "booking",
            "name": "",
            "location": "",
            "guests": "",
            "bedrooms": "",
            "beds": "",
            "bathrooms": "",
            "price": "",
            "rating": "",
            "reviews": "",
            "amenities": [],
            "image": "",
            "checkin": "",
            "checkout": "",
        }
        
        # Parse URL params
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        info["checkin"] = params.get("checkin", [""])[0]
        info["checkout"] = params.get("checkout", [""])[0]
        adults = params.get("group_adults", [""])[0]
        if adults:
            info["guests"] = adults
        
        # Title
        title_tag = soup.find('title')
        if title_tag:
            info["name"] = title_tag.text.strip().split(',')[0].split('|')[0].strip()
        
        og_title = soup.find('meta', property='og:title')
        if og_title:
            info["name"] = og_title.get('content', '').split(',')[0].split('|')[0].strip()
        
        og_image = soup.find('meta', property='og:image')
        if og_image:
            info["image"] = og_image.get('content', '')
        
        # JSON-LD
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                ld = json.loads(script.string)
                if isinstance(ld, dict):
                    if 'name' in ld:
                        info["name"] = ld["name"]
                    if 'address' in ld:
                        addr = ld["address"]
                        if isinstance(addr, dict):
                            parts = [addr.get('streetAddress', ''), addr.get('addressLocality', ''), addr.get('addressCountry', '')]
                            info["location"] = ", ".join([p for p in parts if p])
                    if 'aggregateRating' in ld:
                        info["rating"] = str(ld["aggregateRating"].get("ratingValue", ""))
                        info["reviews"] = str(ld["aggregateRating"].get("reviewCount", ""))
                    if 'image' in ld:
                        imgs = ld["image"]
                        if isinstance(imgs, list) and imgs:
                            info["image"] = imgs[0]
                        elif isinstance(imgs, str):
                            info["image"] = imgs
            except:
                pass
        
        # Amenities
        amenity_keywords = {
            "Pool": ["pool", "swimming"],
            "Fitness": ["gym", "fitness"],
            "Sauna": ["sauna"],
            "Strand": ["beach", "strand", "beachfront"],
            "Küche": ["kitchen", "küche"],
            "Parkplatz": ["parking", "parkplatz"],
            "WLAN": ["wifi", "wlan", "wi-fi", "internet"],
            "Klimaanlage": ["air conditioning", "klimaanlage"],
            "Waschmaschine": ["washer", "washing"],
            "Jacuzzi": ["hot tub", "jacuzzi"],
            "Meerblick": ["sea view", "ocean view"],
        }
        
        page_text = resp.text.lower()
        for amenity, keywords in amenity_keywords.items():
            for kw in keywords:
                if kw.lower() in page_text:
                    info["amenities"].append(amenity)
                    break
        
        return info
    except Exception as e:
        return {"source": "booking", "name": f"Fehler: {str(e)}", "error": True}

def scrape_url(url):
    """Route to appropriate scraper."""
    if "airbnb" in url.lower():
        return scrape_airbnb(url)
    elif "booking.com" in url.lower():
        return scrape_booking(url)
    else:
        return {"source": "unknown", "name": "Unbekannte Plattform", "error": True}

@app.route('/')
def index():
    return render_template('index.html', voters=VOTERS)

@app.route('/api/villas', methods=['GET'])
def get_villas():
    data = load_data()
    # Sort by average score descending
    for v in data["villas"]:
        votes = [v["votes"].get(voter, 0) for voter in VOTERS if v["votes"].get(voter, 0) > 0]
        v["avg_score"] = round(sum(votes) / len(votes), 1) if votes else 0
        v["vote_count"] = len(votes)
    data["villas"].sort(key=lambda x: x["avg_score"], reverse=True)
    return jsonify(data)

@app.route('/api/add', methods=['POST'])
def add_villa():
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({"error": "Kein Link"}), 400
    
    # Scrape
    info = scrape_url(url)
    
    villa = {
        "id": hashlib.md5(url.encode()).hexdigest()[:8],
        "url": url,
        "info": info,
        "votes": {},
        "added_at": time.time(),
        "added_by": request.json.get('added_by', 'Anonym')
    }
    
    data = load_data()
    # Check duplicate
    for v in data["villas"]:
        if v["url"] == url:
            return jsonify({"error": "Link bereits vorhanden"}), 409
    
    data["villas"].append(villa)
    save_data(data)
    return jsonify(villa)

@app.route('/api/vote', methods=['POST'])
def vote():
    villa_id = request.json.get('villa_id')
    voter = request.json.get('voter')
    score = request.json.get('score')
    
    if voter not in VOTERS:
        return jsonify({"error": "Unbekannter Voter"}), 400
    if not (1 <= score <= 5):
        return jsonify({"error": "Score muss 1-5 sein"}), 400
    
    data = load_data()
    for v in data["villas"]:
        if v["id"] == villa_id:
            v["votes"][voter] = score
            save_data(data)
            return jsonify({"ok": True})
    
    return jsonify({"error": "Villa nicht gefunden"}), 404

@app.route('/api/delete', methods=['POST'])
def delete_villa():
    villa_id = request.json.get('villa_id')
    data = load_data()
    data["villas"] = [v for v in data["villas"] if v["id"] != villa_id]
    save_data(data)
    return jsonify({"ok": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8420, debug=False)
