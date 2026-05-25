import streamlit as st
import json
import re
import urllib.parse
import pandas as pd
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import plotly.express as px

st.set_page_config(page_title="PulseSEO Workspace", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    .stMetric { background-color: #161925; border: 1px solid #2A2E45; padding: 15px; border-radius: 10px; }
    div[data-testid="stExpander"] { background-color: #161925; border: 1px solid #2A2E45; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_ai_client():
    api_key = st.secrets.get("GEMINI_API_KEY", None)
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY missing in Streamlit Secrets setup.")
        st.stop()
    return genai.Client(api_key=api_key)

try:
    ai_client = get_ai_client()
except Exception as e:
    st.error(f"Authentication failed: {e}")
    st.stop()

def fetch_google_suggestions(seed_keyword: str) -> list:
    encoded = urllib.parse.quote_plus(seed_keyword)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={encoded}"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res.status_code == 200:
            return res.json()[1]
    except:
        pass
    return [seed_keyword, f"best {seed_keyword}", f"{seed_keyword} online", f"free {seed_keyword}"]

def fetch_serp_density(keyword: str) -> dict:
    encoded = urllib.parse.quote_plus(keyword)
    url = f"https://www.google.com/search?q={encoded}&hl=en"
    metrics = {"raw_text": "", "estimated_count": 50000}
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=7)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            stats = soup.find("div", id="result-stats")
            if stats:
                metrics["raw_text"] = stats.text
                nums = re.findall(r'[0-9,]+', stats.text)
                if nums:
                    metrics["estimated_count"] = int(nums[0].replace(",", ""))
            else:
                metrics["raw_text"] = " ".join([t.get_text() for t in soup.find_all(["h3", "span"])[:15]])
    except:
        pass
    return metrics

def scrape_competitor(target_url: str) -> dict:
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url
    extracted = {"title": "N/A", "description": "N/A", "headings": [], "text": ""}
    try:
        res = requests.get(target_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            extracted["title"] = soup.title.string.strip() if soup.title else "No Title"
            desc = soup.find("meta", attrs={"name": "description"})
            if desc and desc.get("content"):
                extracted["description"] = desc["content"].strip()
            extracted["headings"] = [h.get_text().strip() for h in soup.find_all(["h1", "h2"]) if h.get_text()][:10]
            extracted["text"] = " ".join(soup.get_text().split())[:2000]
    except Exception as e:
        extracted["title"] = f"Error reading page: {str(e)}"
    return extracted

def analyze_keywords_ai(seed: str, suggestions: list, serp: dict):
    sys_instruction = "You are an SEO analytics engine. Return your analysis EXCLUSIVELY as a valid JSON object matching the requested schema."
    prompt = f"""
    Analyze seed: {seed}, variations: {json.dumps(suggestions)}, and SERP stats: {json.dumps(serp)}.
    Return a JSON object with:
    1. "difficulty_score": integer 0-100
    2. "difficulty_justification": string
    3. "intent_distribution": {{"Informational": %, "Navigational": %, "Commercial": %, "Transactional": %}}
    4. "keyword_table": list of objects with keys: 
       - "keyword": the text variation string
       - "search_intent": one of 'Informational', 'Navigational', 'Commercial', 'Transactional'
       - "estimated_monthly_volume": integer value
       - "cpc_usd": float number
       - "keyword_difficulty_percent": integer from 0 to 100 representing individual difficulty for this specific variation term
       - "recommended_content_strategy": text summary
    """
    response = ai_client.models.generate_content(
        model='gemini-2.5-flash', contents=prompt,
        config=types.GenerateContentConfig(system_instruction=sys_instruction, temperature=0.2, response_mime_type="application/json")
    )
    return json.loads(response.text.strip())

def analyze_competitor_ai(url: str, data: dict):
    sys_instruction = "You are an SEO competitor strategist. Return analysis as a valid JSON object."
    prompt = f"Analyze URL: {url} with scraped data: {json.dumps(data)}. Return JSON with fields: 'primary_thematic_focus', 'estimated_seo_position', 'observed_tactics' (list), 'content_gaps_opportunities' (list), 'target_keywords_detected' (list)."
    response = ai_client.models.generate_content(
        model='gemini-2.5-flash', contents=prompt,
        config=types.GenerateContentConfig(system_instruction=sys_instruction, temperature=0.3, response_mime_type="application/json")
    )
    return json.loads(response.text.strip())

# --- USER INTERFACE ---
st.title("⚡ PulseSEO Personal Workspace")
tabs = st.tabs(["🔍 Keyword Planner", "🛡️ Competitor Audit", "📈 Trend Tracker"])

with tabs[0]:
    st.subheader("Keyword Expansion & Intent Analyzer")
    kw_input = st.text_input("Enter a keyword:", placeholder="e.g., organic coffee beans")
    if st.button("Analyze Keyword", type="primary"):
        with st.spinner("Analyzing market data..."):
            suggs = fetch_google_suggestions(kw_input)
            serp = fetch_serp_density(kw_input)
            res = analyze_keywords_ai(kw_input, suggs, serp)
            
            if res:
                kd = res.get("difficulty_score", 50)
                st.metric(label="Keyword Difficulty", value=f"{kd}%")
                st.info(f"**Justification:** {res.get('difficulty_justification')}")
                
                st.write("### 🎯 Intent Distribution")
                df_intent = pd.DataFrame(list(res.get("intent_distribution", {}).items()), columns=["Intent", "%"])
                st.plotly_chart(px.bar(df_intent, x="Intent", y="%"), use_container_width=True)
                
                st.write("### 📊 Keyword Variation Breakdown")
                df_table = pd.DataFrame(res.get("keyword_table", []))
                st.dataframe(df_table, use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Competitor Optimization Scanner")
    url_input = st.text_input("Enter competitor web link:")
    if st.button("Scan Competitor Site"):
        with st.spinner("Scraping and analyzing page structure..."):
            scraped = scrape_competitor(url_input)
            st.text_input("Page Title Tag Detected:", value=scraped["title"], disabled=True)
            
            comp_res = analyze_competitor_ai(url_input, scraped)
            if comp_res:
                st.write("---")
                st.markdown(f"**Thematic Focus:** {comp_res.get('primary_thematic_focus')}")
                st.markdown(f"**SEO Standing:** {comp_res.get('estimated_seo_position')}")
                
                c1, c2 = st.columns(2)
                with c1:
                    st.write("### 🛠️ Observed Tactics")
                    for t in comp_res.get("observed_tactics", []): st.write(f"- {t}")
                with c2:
                    st.write("### 🎯 Target Keywords Detected")
                    for k in comp_res.get("target_keywords_detected", []): st.write(f"`{k}`")
                    
                st.write("### 💡 Gaps & Weaknesses You Can Exploit")
                for g in comp_res.get("content_gaps_opportunities", []): st.write(f"🔥 {g}")

with tabs[2]:
    st.subheader("Live Market Trends Dashboard")
    if st.button("Load Live Breaking Trends"):
        with st.spinner("Connecting to trend monitors..."):
            try:
                res = requests.get("https://trends.google.com/trends/trendingsearches/daily/rss?geo=US", timeout=5)
                soup = BeautifulSoup(res.text, "xml")
                records = []
                for item in soup.find_all("item")[:10]:
                    records.append({
                        "Trending Topic": item.find("title").text if item.find("title") else "N/A",
                        "Search Volume": item.find("ht:approx_traffic").text if item.find("ht:approx_traffic") else "High",
                        "Summary Context": item.find("description").text if item.find("description") else "N/A"
                    })
                st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Could not reach trends interface: {e}")
