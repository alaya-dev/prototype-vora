"""
VORA — AI E-Commerce Intelligence
Backend FastAPI — Cohere API
"""

import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

COHERE_API_KEY = "clHVp28WX86zXh1DSaHnsV6o59aGdjOaktNUmSlc"

app = FastAPI(title="VORA API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_prompt(product: str) -> str:
    return f"""Tu es VORA, expert en e-commerce et import/export pour le marché tunisien.
Analyse ce produit : "{product}"

Réponds UNIQUEMENT avec un objet JSON valide. Commence par {{ et termine par }}. Zéro texte avant ou après. Zéro markdown.

Exemple pour "écouteurs Bluetooth" :
{{"demand_score":72,"trend":"+18% sur 6 mois","competition":"Moyenne","sell_price_low":89,"sell_price_high":149,"buy_fob_usd":14.5,"shipping_usd":9.0,"customs_rate":17,"customs_usd":3.99,"total_cost_usd":27.49,"net_margin_pct":47,"channels":["Jumia TN","Facebook Marketplace","Instagram Ads"],"suppliers":[{{"name":"Shenzhen TechGlobe Co.","platform":"Alibaba","moq":"50 pcs","price_range":"$12-18/u","rating":"4.8★"}},{{"name":"Guangzhou AudioPro","platform":"1688","moq":"100 pcs","price_range":"$10-14/u","rating":"4.6★"}}],"verdict":"GO","verdict_reason":"Forte demande 72%, marge nette 47%, concurrence modérée.","email":"Objet : Demande de tarification — écouteurs Bluetooth\\n\\nBonjour,\\nJe souhaite importer vos écouteurs Bluetooth en Tunisie.\\nMerci de m'envoyer vos prix FOB pour 50, 100, 200 pcs.\\nCordialement"}}

Génère le même JSON pour le produit "{product}".

Règles OBLIGATOIRES :
- Le nom complet du produit est : {product}
- Utilise TOUJOURS "{product}" (nom complet) dans les champs email et verdict_reason, jamais tronqué
- customs_usd = (buy_fob_usd + shipping_usd) * 0.17
- total_cost_usd = buy_fob_usd + shipping_usd + customs_usd
- Si demand_score >= 55 ET net_margin_pct >= 28 alors verdict = "GO", sinon verdict = "NO GO"
- Cette règle est ABSOLUE : 65% demande + 35% marge = GO obligatoire
- sell_price_low et sell_price_high en DT tunisien (nombres entiers)
- buy_fob_usd, shipping_usd, customs_usd, total_cost_usd en USD (nombres décimaux)
- Tous les champs doivent avoir des valeurs réelles, jamais 0 ou vide
- 3 fournisseurs minimum dans suppliers"""


class AnalyzeRequest(BaseModel):
    product: str


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    if not req.product.strip():
        raise HTTPException(status_code=400, detail="Le nom du produit est requis.")

    payload = {
    "model": "command-r-plus-08-2024",
    "messages": [{"role": "user", "content": build_prompt(req.product)}],
    "temperature": 0.3,
    "max_tokens": 2000,
    "response_format": {"type": "json_object"}
}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.cohere.com/v2/chat",
            json=payload,
            headers={
                "Authorization": f"Bearer {COHERE_API_KEY}",
                "Content-Type": "application/json"
            }
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Erreur Cohere API ({resp.status_code}): {resp.text}")

    data = resp.json()
    print("RAW:", json.dumps(data, indent=2))

    try:
        raw = data["message"]["content"][0]["text"]
    except Exception:
        raw = data.get("text", "")

    raw = raw.replace("```json", "").replace("```", "").strip()
    print("PARSED RAW:", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail=f"JSON invalide: {raw[:200]}")


app.mount("/", StaticFiles(directory="static", html=True), name="static")