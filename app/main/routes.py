from flask import Blueprint, render_template, url_for, request, jsonify
import requests
import wikipedia

main = Blueprint("main", __name__)

# ---- Home Page ----
@main.route("/")
def home():
    logo_url = url_for("static", filename="assets/loogo.jpg")  # fixed typo
    return render_template("index.html", logo=logo_url)


@main.route("/privacy")
def privacy():
    logo_url = url_for("static", filename="assets/loogo.jpg")  # fixed typo
    return render_template("privacy.html", logo=logo_url)


# ---- Helpers ----
def get_json(url):
    headers = {"User-Agent": "WikidataSmartSummary/1.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def commons_image_url(filename, width=600):
    if not filename:
        return None
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{requests.utils.quote(filename)}?width={width}"

def parse_time(wb_time):
    if not wb_time or "time" not in wb_time:
        return None
    return wb_time["time"].lstrip("+")[:10]

def format_fallback_summary(label, description, birth_date, death_date, occupations):
    life = f" ({birth_date or '…'} – {death_date or ''})" if birth_date or death_date else ""
    occ = f" {', '.join(occupations)}." if occupations else ""
    return f"<p><strong>{label}</strong>{life}{' — ' + description if description else ''}</p>" + \
           (f"<p><strong>Occupation:</strong> {', '.join(occupations)}</p>" if occupations else "")

def resolve_labels(ids, lang):
    if not ids:
        return {}
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&origin=*&ids={'|'.join(ids)}&languages={lang}|en"
    data = get_json(url)
    return {
        id_: data["entities"].get(id_, {}).get("labels", {}).get(lang, {}).get("value") or
             data["entities"].get(id_, {}).get("labels", {}).get("en", {}).get("value") or id_
        for id_ in ids
    }

# ---- Core Wikidata + Wikipedia ----
def fetch_entity_by_search(term, lang):
    s_url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&language={lang}&origin=*&search={requests.utils.quote(term)}"
    s_data = get_json(s_url)
    if not s_data.get("search"):
        raise ValueError("No results in Wikidata")

    top = s_data["search"][0]
    qid = top["id"]

    e_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    e_data = get_json(e_url)
    entity = e_data["entities"][qid]

    label = entity.get("labels", {}).get(lang, {}).get("value") or \
            entity.get("labels", {}).get("en", {}).get("value") or \
            top.get("label") or qid
    description = entity.get("descriptions", {}).get(lang, {}).get("value") or \
                  entity.get("descriptions", {}).get("en", {}).get("value") or \
                  top.get("description") or ""

    claims = entity.get("claims", {})
    birth_date = parse_time(claims.get("P569", [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value"))
    death_date = parse_time(claims.get("P570", [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value"))
    occupation_ids = [c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") for c in claims.get("P106", []) if c.get("mainsnak")]
    image_filename = claims.get("P18", [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value")

    occupations = [resolve_labels(occupation_ids, lang).get(id_) for id_ in occupation_ids if id_]

    site_title = entity.get("sitelinks", {}).get(f"{lang}wiki", {}).get("title") or \
                 entity.get("sitelinks", {}).get("enwiki", {}).get("title")
    wikipedia_url = f"https://{lang}.wikipedia.org/wiki/{requests.utils.quote(site_title)}" if site_title else None

    wiki_extract = ""
    thumb = commons_image_url(image_filename, 800) if image_filename else None

    if site_title:
        try:
            sum_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(site_title)}"
            sum_data = get_json(sum_url)
            wiki_extract = sum_data.get("extract", "")
            if not thumb and sum_data.get("thumbnail", {}).get("source"):
                thumb = sum_data["thumbnail"]["source"]
        except Exception:
            pass

    summary_html = "".join(f"<p>{p}</p>" for p in wiki_extract.split("\n\n")) if wiki_extract else \
                   format_fallback_summary(label, description, birth_date, death_date, occupations)

    return {
        "qid": qid,
        "label": label,
        "description": description,
        "image": thumb,
        "birthDate": birth_date,
        "deathDate": death_date,
        "occupations": occupations,
        "wikipediaUrl": wikipedia_url,
        "language": lang,
        "contentHtml": summary_html,
        "siteTitle": site_title
    }

# ---- Routes ----
@main.route("/api/search")
def search():
    try:
        q = request.args.get("q", "").strip()
        lang = request.args.get("lang", "en")
        if not q:
            return jsonify({"error": "Missing q"}), 400
        result = fetch_entity_by_search(q, lang)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@main.route("/api/article/<lang>/<title>")
def article(lang, title):
    try:
        url = f"https://{lang}.wikipedia.org/w/api.php?action=query&format=json&origin=*&prop=extracts&explaintext=true&exintro=false&redirects=1&titles={requests.utils.quote(title)}"
        data = get_json(url)
        pages = data.get("query", {}).get("pages", {})
        page_id = next(iter(pages))
        if page_id == "-1":
            raise ValueError("No page text")
        extract = pages[page_id].get("extract", "")
        content_html = "".join(f"<p>{p.strip()}</p>" for p in extract.split("\n\n"))
        return jsonify({"ok": True, "title": pages[page_id]["title"], "contentHtml": content_html})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# @main.route("/api/summarize", methods=["POST"])
# def summarize():
#     try:
#         data = request.get_json() or {}
#         text = data.get("text", "")
#         language = data.get("language", "en")
#         if not text or len(text) < 40:
#             return jsonify({"ok": False, "error": "Insufficient text to summarize"}), 400

#         key = os.getenv("GROQ_API_KEY")
#         model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

#         if not key:
#             first = " ".join(filter(None, text.split("\n"))[:3])
#             return jsonify({"ok": True, "summary": f"Summary (offline): {first[:600]}{'…' if len(first) > 600 else ''}"})

#         response = requests.post(
#             "https://api.groq.com/openai/v1/chat/completions",
#             headers={
#                 "Authorization": f"Bearer {key}",
#                 "Content-Type": "application/json"
#             },
#             json={
#                 "model": model,
#                 "temperature": 0.5,
#                 "messages": [
#                     {"role": "system", "content": "You are a summarizer that produces clear, concise 3–5 paragraph summaries."},
#                     {"role": "user", "content": f"Language: {language}\n\nSummarize:\n\n{text}"}
#                 ]
#             }
#         )
#         j = response.json()
#         if not response.ok or "error" in j:
#             raise ValueError(j.get("error", {}).get("message", "Groq request failed"))
#         summary = j["choices"][0]["message"]["content"].strip()
#         return jsonify({"ok": True, "summary": summary})
#     except Exception as e:
#         return jsonify({"ok": False, "error": str(e)}), 