/* NEXORA opportunity report renderer — overrides the prototype summary view
   with a full pre-study report (sourcing tables, landed cost, comparability,
   competition, profitability, potential scores, scoring detail, sources). */

const REPORT_COPY = {
  en: {
    stepProduct: "Product identification",
    stepSourcing: "International sourcing",
    stepSuppliers: "Supplier analysis",
    stepMarket: "Tunisia market",
    stepCompetition: "Competition",
    stepProfitability: "Profitability",
    stepPotential: "Commercial potential",
    stepAds: "Ads potential",
    stepScore: "Score computation",
    stepDecision: "GO / NO GO",
    stepReport: "Final report",
    targetMarketLabel: "Target market",
    targetMarketPlaceholder: "Tunisia",
    sourcingCountryLabel: "Sourcing priority",
    sourcingCountryPlaceholder: "China",
    execSummary: "Executive summary",
    productAnalyzed: "Product analyzed",
    requestedProduct: "Requested product",
    normalizedProduct: "Normalized product",
    marketAnalyzed: "Analyzed market",
    sourcingCountryCol: "Sourcing country",
    techSpecs: "Specifications",
    volumeUnit: "Volume / unit",
    notAvailable: "Not available",
    moqNotAvailable: "MOQ not available",
    sourcingInternational: "International sourcing",
    supplierCol: "Supplier",
    typeCol: "Type",
    trustCol: "Confidence",
    sourceLink: "Source",
    wholesalePrices: "Tunisia wholesale prices",
    noWholesalePrice: "No reliable public wholesale price was found.",
    landedCostTitle: "Landed cost in Tunisia",
    componentCol: "Component",
    valueCol: "Value",
    provenanceCol: "Data quality",
    partialEstimateNote: "Partial estimate — some import charges are not included.",
    tunisiaMarketTitle: "Tunisia market",
    retailPrices: "Retail prices",
    wholesalePricesShort: "Wholesale prices",
    sellerCol: "Seller",
    brandCol: "Brand",
    productCol: "Product",
    volumeCol: "Volume",
    priceCol: "Price",
    normalizedPrice: "Normalized price",
    availabilityCol: "Availability",
    cityCol: "City",
    priceTypeCol: "Price type",
    comparabilityTitle: "Comparability check",
    comparabilityHigh: "HIGH",
    comparabilityMedium: "MEDIUM",
    comparabilityLow: "LOW",
    indicativeMarginWarning: "Indicative margin only: the compared products are not sufficiently equivalent.",
    competitionTitle: "Competitive analysis",
    competitionLevelLabel: "Competition level",
    competitorsFound: "Competitors actually found",
    competitionJustification: "Justification",
    rentabilityTitle: "Profitability analysis",
    observedData: "Observed data",
    hypotheses: "Hypotheses",
    quantityAnalyzed: "Analyzed quantity",
    unitBuyPrice: "Unit purchase price",
    observedRetailPrice: "Observed retail price",
    recommendedSalePrice: "Recommended selling price",
    grossMarginUnit: "Gross margin per unit",
    marginPercent: "Margin %",
    grossProfitTotal: "Gross profit (scenario)",
    adsBudgetHypothetical: "Hypothetical ad budget",
    profitAfterAds: "Profit after ads (scenario)",
    formulaNote: "Gross margin = selling price − landed cost · Margin % = (selling price − landed cost) / selling price × 100",
    commercialPotentialTitle: "Commercial potential",
    adsPotentialTitle: "Ads / marketing potential",
    adsMeta: "Meta Ads",
    adsGoogle: "Google Search",
    adsQualitativeNote: "Qualitative analysis only — no real CPC, CPA, ROAS or search-volume data is available, so none are invented.",
    purchaseType: "Purchase type",
    customerBehavior: "Likely customer behavior",
    targetAudiences: "Potential audiences",
    adAngles: "Advertising angles",
    salesArguments: "Commercial arguments",
    acquisitionDifficulty: "Acquisition difficulty",
    repurchasePotential: "Repurchase potential",
    marketingRisks: "Marketing risks",
    risksTitle: "Main risks",
    scoringDetailTitle: "Detailed scoring",
    actionsTitle: "Recommended actions before investing",
    decisionJustificationTitle: "Decision justification",
    sourcesTitle: "Sources & evidence",
    sourcesIntro: "Every key figure above comes from the sources below or from calculations applied to them.",
    dataUsed: "Data used",
    dateCol: "Date",
    favorableFactors: "Favorable factors",
    unfavorableFactors: "Unfavorable factors"
  },
  fr: {
    stepProduct: "Identification du produit",
    stepSourcing: "Sourcing international",
    stepSuppliers: "Analyse fournisseurs",
    stepMarket: "Marché tunisien",
    stepCompetition: "Concurrence",
    stepProfitability: "Rentabilité",
    stepPotential: "Potentiel commercial",
    stepAds: "Potentiel Ads",
    stepScore: "Calcul du score",
    stepDecision: "GO / NO GO",
    stepReport: "Rapport final",
    targetMarketLabel: "Marché cible",
    targetMarketPlaceholder: "Tunisie",
    sourcingCountryLabel: "Sourcing prioritaire",
    sourcingCountryPlaceholder: "Chine",
    execSummary: "Résumé exécutif",
    productAnalyzed: "Produit analysé",
    requestedProduct: "Produit demandé",
    normalizedProduct: "Produit normalisé",
    marketAnalyzed: "Marché analysé",
    sourcingCountryCol: "Pays de sourcing",
    techSpecs: "Caractéristiques",
    volumeUnit: "Format / volume",
    notAvailable: "Non disponible",
    moqNotAvailable: "MOQ non disponible",
    sourcingInternational: "Sourcing international",
    supplierCol: "Fournisseur",
    typeCol: "Type",
    trustCol: "Confiance",
    sourceLink: "Source",
    wholesalePrices: "Prix gros Tunisie",
    noWholesalePrice: "Aucun prix de gros public fiable trouvé.",
    landedCostTitle: "Coût rendu en Tunisie",
    componentCol: "Composant",
    valueCol: "Valeur",
    provenanceCol: "Qualité de la donnée",
    partialEstimateNote: "Estimation partielle — certaines charges d'importation ne sont pas incluses.",
    tunisiaMarketTitle: "Marché tunisien",
    retailPrices: "Prix détail",
    wholesalePricesShort: "Prix gros",
    sellerCol: "Vendeur",
    brandCol: "Marque",
    productCol: "Produit",
    volumeCol: "Volume",
    priceCol: "Prix",
    normalizedPrice: "Prix normalisé",
    availabilityCol: "Disponibilité",
    cityCol: "Ville",
    priceTypeCol: "Type de prix",
    comparabilityTitle: "Vérification de comparabilité",
    comparabilityHigh: "HAUTE",
    comparabilityMedium: "MOYENNE",
    comparabilityLow: "FAIBLE",
    indicativeMarginWarning: "Marge indicative uniquement : les produits comparés ne sont pas suffisamment équivalents.",
    competitionTitle: "Analyse concurrentielle",
    competitionLevelLabel: "Niveau de concurrence",
    competitorsFound: "Concurrents réellement trouvés",
    competitionJustification: "Justification",
    rentabilityTitle: "Analyse de rentabilité",
    observedData: "Données observées",
    hypotheses: "Hypothèses",
    quantityAnalyzed: "Quantité analysée",
    unitBuyPrice: "Prix d'achat unitaire",
    observedRetailPrice: "Prix détail observé",
    recommendedSalePrice: "Prix de vente recommandé",
    grossMarginUnit: "Marge brute / unité",
    marginPercent: "Marge %",
    grossProfitTotal: "Profit brut (scénario)",
    adsBudgetHypothetical: "Budget publicitaire hypothétique",
    profitAfterAds: "Profit après Ads (scénario)",
    formulaNote: "Marge brute = prix de vente − coût rendu · Marge % = (prix de vente − coût rendu) / prix de vente × 100",
    commercialPotentialTitle: "Potentiel commercial",
    adsPotentialTitle: "Potentiel Ads / marketing",
    adsMeta: "Meta Ads",
    adsGoogle: "Google Search",
    adsQualitativeNote: "Analyse qualitative uniquement — aucune donnée réelle de CPC, CPA, ROAS ou volume de recherche n'est disponible, aucune valeur n'est inventée.",
    purchaseType: "Type d'achat",
    customerBehavior: "Comportement client probable",
    targetAudiences: "Audiences potentielles",
    adAngles: "Angles publicitaires",
    salesArguments: "Arguments commerciaux",
    acquisitionDifficulty: "Difficulté d'acquisition",
    repurchasePotential: "Potentiel de réachat",
    marketingRisks: "Risques marketing",
    risksTitle: "Risques principaux",
    scoringDetailTitle: "Scoring détaillé",
    actionsTitle: "Actions à effectuer avant investissement",
    decisionJustificationTitle: "Justification de la décision",
    sourcesTitle: "Sources & preuves",
    sourcesIntro: "Chaque donnée clé ci-dessus provient des sources listées ici ou d'un calcul appliqué à celles-ci.",
    dataUsed: "Donnée utilisée",
    dateCol: "Date",
    favorableFactors: "Facteurs favorables",
    unfavorableFactors: "Facteurs défavorables"
  }
};

Object.assign(copy.en, REPORT_COPY.en);
Object.assign(copy.fr, REPORT_COPY.fr);

function renderPrototypeResult(data) {
  productPhoto.innerHTML = renderProductImage(data);
  const labels = copy[currentLanguage];
  const retail = deriveRetailSummary(data.retail_market_summary || {});
  const profit = deriveProfitability(data);
  const quantityUnits = analysisQuantityUnits(data);
  const scores = normalizeDecisionScores(data.decision_scores || {});
  const recommendation = displayedRecommendation(data.recommendation || "investigate_more", scores);
  const productDescription = localizedText(
    data.localized_analysis,
    "product_description",
    data.product_description || labels.noDescription
  );
  const understanding = data.product_understanding || {};
  prototypeResult.innerHTML = `
    ${renderExecutiveSummary(data, scores, recommendation, profit)}
    ${renderProductIdentification(data, understanding, productDescription)}
    ${renderSourcingSection(data)}
    ${renderLandedCostSection(data)}
    ${renderTunisiaMarketSection(data, retail)}
    ${renderComparabilitySection(data)}
    ${renderCompetitionSection(data)}
    ${renderProfitabilitySection(data, profit, quantityUnits)}
    <div class="result-grid">
      ${renderCommercialPotentialSection(data)}
      ${renderAdsPotentialSection(data)}
    </div>
    ${renderRisksSection(data)}
    <section class="result-band wide">
      <h2>${labels.decisionTitle}</h2>
      ${renderDecisionIllustration(data)}
      ${renderDetailedScoring(data)}
      <div class="analysis-copy">
        <article>
          <h3>${labels.favorableFactors}</h3>
          <ul class="decision-factors">${(data.positive_signals || []).map((signal) => `<li>${escapeHtml(signal)}</li>`).join("") || `<li>—</li>`}</ul>
        </article>
        <article>
          <h3>${labels.unfavorableFactors}</h3>
          <ul class="decision-factors">${(data.risk_signals || []).map((signal) => `<li>${escapeHtml(signal)}</li>`).join("") || `<li>—</li>`}</ul>
        </article>
      </div>
      <div class="action-row decision-bar no-print">
        <button class="button-go" onclick="revealGo()">${labels.goButton}</button>
        <button class="button-nogo" onclick="showNoGo('${escapeAttribute(data.recommendation_reason || "")}')">${labels.noGoButton}</button>
      </div>
      <div id="decisionReveal" class="list"></div>
    </section>
    ${renderActionsSection(data)}
    ${renderSourcesSection(data)}
  `;
}

function provenanceBadge(provenance) {
  const map = {
    observed: { cls: "badge-observed", label: currentLanguage === "fr" ? "DONNÉE RÉELLE" : "OBSERVED" },
    computed: { cls: "badge-computed", label: currentLanguage === "fr" ? "CALCUL" : "COMPUTED" },
    estimate: { cls: "badge-estimate", label: currentLanguage === "fr" ? "ESTIMATION" : "ESTIMATE" },
    unavailable: { cls: "badge-unavailable", label: currentLanguage === "fr" ? "NON DISPONIBLE" : "NOT AVAILABLE" },
    source: { cls: "badge-source", label: "SOURCE" },
    deduction: { cls: "badge-deduction", label: currentLanguage === "fr" ? "DÉDUCTION" : "DEDUCTION" }
  };
  const item = map[provenance] || map.unavailable;
  return `<span class="badge ${item.cls}">${item.label}</span>`;
}

function confidenceInline(level) {
  const key = String(level || "low").toLowerCase();
  const values = currentLanguage === "fr"
    ? { high: "HAUTE", medium: "MOYENNE", low: "FAIBLE", unknown: "INCONNUE" }
    : { high: "HIGH", medium: "MEDIUM", low: "LOW", unknown: "UNKNOWN" };
  return `<span class="confidence-${key === "unknown" ? "low" : key}">${values[key] || values.low}</span>`;
}

function provenanceText(provenance) {
  const labels = {
    observed: currentLanguage === "fr" ? "DONNÉE RÉELLE" : "OBSERVED",
    computed: currentLanguage === "fr" ? "CALCUL" : "COMPUTED",
    estimate: currentLanguage === "fr" ? "ESTIMATION" : "ESTIMATE",
    unavailable: currentLanguage === "fr" ? "NON DISPONIBLE" : "NOT AVAILABLE",
  };
  return labels[provenance] || labels.unavailable;
}

function sectionConfidence(label, level, note) {
  return `<div class="section-confidence">${escapeHtml(label)} : ${confidenceInline(level)}${note ? ` <span>— ${escapeHtml(note)}</span>` : ""}</div>`;
}

function renderExecutiveSummary(data, scores, recommendation, profit) {
  const labels = copy[currentLanguage];
  const summaryText = localizedText(data.localized_analysis, "business_reading", data.decision_summary || data.recommendation_reason || "");
  const comparability = data.comparability || {};
  const landed = data.landed_cost || {};
  const retail = data.retail_market_summary || {};
  const locale = currentLanguage === "fr" ? "fr-FR" : "en-GB";
  const contextLine = currentLanguage === "fr"
    ? `${data.target_market || "Tunisie"} · Sourcing : ${data.sourcing_country || "Chine"} · ${new Date().toLocaleDateString(locale)}`
    : `${data.target_market || "Tunisia"} · Sourcing: ${data.sourcing_country || "China"} · ${new Date().toLocaleDateString(locale)}`;
  return `
    <section class="result-band wide report-cover">
      <div class="report-header">
          <div>
          <img class="report-cover-logo" src="/logo/Nexora_logo_transparent_clean_cropped.png" alt="NEXORA">
          <div class="eyebrow">${currentLanguage === "fr" ? "Rapport d'opportunité produit" : "Product opportunity report"}</div>
          <p class="report-tagline">INTELLIGENT SOURCING. SMARTER GROWTH.</p>
          <h2>${escapeHtml(data.product_understanding?.normalized_product || data.product_description || labels.product)}</h2>
          <p>${escapeHtml(contextLine)}</p>
        </div>
        <img class="report-cover-image" src="${escapeAttribute(data.product_image_url || fallbackProductImage(data.product_understanding?.normalized_product || labels.product))}" alt="${escapeAttribute(data.product_understanding?.normalized_product || labels.product)}" onerror="handleProductImageError(this, '${escapeAttribute(data.product_understanding?.normalized_product || labels.product)}')">
        <span class="pill">${recommendationText(recommendation)} · ${scores.go_percent}/100</span>
      </div>
      <h3>${labels.execSummary}</h3>
      <p>${escapeHtml(summaryText)}</p>
      <div class="metric-grid">
        ${metric(labels.landedCost, tnd(landed.total_tnd ?? profit.estimated_landed_cost_per_unit_tnd))}
        ${metric(labels.averagePrice, tnd(retail.retail_avg_tnd))}
        ${metric(labels.grossMarginPerUnit, tnd(profit.gross_margin_per_unit_before_marketing_tnd))}
        ${metric(labels.decisionConfidence, confidenceText(scores.confidence))}
      </div>
      ${comparability.margin_is_indicative_only ? `<div class="margin-warning">${labels.indicativeMarginWarning}</div>` : ""}
    </section>
  `;
}

function renderProductIdentification(data, understanding, productDescription) {
  const labels = copy[currentLanguage];
  const specs = Array.isArray(understanding.technical_specs) ? understanding.technical_specs : [];
  return `
    <section class="result-band wide">
      <div class="section-head">
        <h2>${labels.productAnalyzed}</h2>
        ${sectionConfidence(labels.productAnalyzed, "medium", "")}
      </div>
      <div class="metric-grid">
        ${metric(labels.requestedProduct, understanding.original_product || labels.notAvailable)}
        ${metric(labels.normalizedProduct, understanding.normalized_product || labels.notAvailable)}
        ${metric(labels.category, understanding.product_category || labels.notAvailable)}
        ${metric(labels.brandCol, understanding.brand_or_model || labels.notAvailable)}
        ${specs.length ? metric(labels.techSpecs, specs.join(" · ")) : ""}
        ${metric(labels.volumeUnit, detectVolumeText(understanding))}
        ${metric(labels.marketAnalyzed, data.target_market || "Tunisia")}
        ${metric(labels.sourcingCountryCol, data.sourcing_country || "China")}
      </div>
      <p>${escapeHtml(productDescription)}</p>
    </section>
  `;
}

function detectVolumeText(understanding) {
  const text = [understanding.normalized_product, understanding.original_product, ...(understanding.technical_specs || [])].join(" ");
  const match = text.match(/(\d+(?:[.,]\d+)?)\s*(ml|l|kg|g)\b/i);
  if (!match) return copy[currentLanguage].notAvailable;
  const unit = match[2].toLowerCase();
  return `${match[1]} ${unit === "l" ? "L" : unit === "ml" ? "ml" : unit.toUpperCase()}`;
}

function offerPriceRange(offer, currency) {
  const min = offer.price_min;
  const max = offer.price_max;
  if (min !== null && min !== undefined) {
    if (max !== null && max !== undefined && max !== min) {
      return `${formatNumber(min)}–${formatNumber(max)} ${currency}`;
    }
    return `${formatNumber(min)} ${currency}`;
  }
  return offer.price_text || copy[currentLanguage].notAvailable;
}

function renderSourcingSection(data) {
  const labels = copy[currentLanguage];
  const offers = data.china_offers || [];
  const confidence = offers.some((offer) => offer.confidence === "high")
    ? "high"
    : offers.length ? "medium" : "low";
  const rows = offers.map((offer) => `<tr>
      <td><strong>${escapeHtml(offer.name || "-")}</strong><br><span class="hidden-note">${escapeHtml(offer.supplier_type || "")}</span></td>
      <td>${escapeHtml(offer.product_title || "-")}</td>
      <td>${escapeHtml(data.sourcing_country || "China")}</td>
      <td>${escapeHtml(offerPriceRange(offer, offer.currency || "USD"))}</td>
      <td>${escapeHtml(tndRangeOrNA(offer.price_min_tnd, offer.price_max_tnd))}</td>
      <td>${escapeHtml(offer.moq || labels.moqNotAvailable)}</td>
      <td>${offer.source_url ? `<a href="${escapeAttribute(offer.source_url)}" target="_blank" rel="noopener noreferrer">${labels.sourceLink}</a>` : labels.notAvailable}</td>
      <td>${confidenceInline(offer.confidence)}</td>
    </tr>`).join("");
  const wholesaleOffers = data.tunisia_wholesale_offers || [];
  const wholesaleRows = wholesaleOffers.map((offer) => `<tr>
    <td><strong>${escapeHtml(offer.name || "-")}</strong><br><span class="hidden-note">${escapeHtml(offer.supplier_type || "")}</span></td>
    <td>${escapeHtml(offer.product_title || "-")}</td>
    <td>${escapeHtml(tndRangeOrNA(offer.price_min_tnd, offer.price_max_tnd) !== labels.notAvailable
      ? tndRangeOrNA(offer.price_min_tnd, offer.price_max_tnd)
      : (offer.price_text || labels.notAvailable))}</td>
    <td>${offer.source_url ? `<a href="${escapeAttribute(offer.source_url)}" target="_blank" rel="noopener noreferrer">${labels.sourceLink}</a>` : labels.notAvailable}</td>
    <td>${confidenceInline(offer.confidence)}</td>
  </tr>`).join("");
  return `
    <section class="result-band wide">
      <div class="section-head">
        <h2>${labels.sourcingInternational}</h2>
        ${sectionConfidence(labels.sourcingInternational, confidence, currentLanguage === "fr"
          ? (offers.length ? `${offers.length} fournisseur(s) trouvé(s) mais coût logistique incomplet.` : "aucun fournisseur trouvé")
          : (offers.length ? `${offers.length} supplier(s) found but logistics cost incomplete.` : "no supplier found"))}
      </div>
      ${offers.length ? `<table class="report-table">
        <thead><tr><th>${labels.supplierCol}</th><th>${labels.productCol}</th><th>${currentLanguage === "fr" ? "Pays" : "Country"}</th><th>${currentLanguage === "fr" ? "Prix min–max" : "Min–max price"}</th><th>${currentLanguage === "fr" ? "Conversion TND" : "TND conversion"}</th><th>${labels.moq}</th><th>${labels.sourceLink}</th><th>${labels.trustCol}</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>` : `<p>${currentLanguage === "fr" ? "Aucun fournisseur avec prix exploitable n'a été trouvé." : "No supplier with usable pricing was found."}</p>`}
      <h3>${labels.wholesalePrices}</h3>
      ${wholesaleRows ? `<table class="report-table">
        <thead><tr><th>${labels.supplierCol}</th><th>${labels.productCol}</th><th>${currentLanguage === "fr" ? "Prix gros" : "Wholesale price"}</th><th>${labels.sourceLink}</th><th>${labels.trustCol}</th></tr></thead>
        <tbody>${wholesaleRows}</tbody>
      </table>` : `<p>${labels.noWholesalePrice}</p>`}
    </section>
  `;
}

function tndRangeOrNA(min, max) {
  const labels = copy[currentLanguage];
  if (min === null || min === undefined) return labels.notAvailable;
  if (max === null || max === undefined || max === min) return `${formatNumber(min)} TND`;
  return `${formatNumber(min)}–${formatNumber(max)} TND`;
}

function normalizedPriceText(offer) {
  const labels = copy[currentLanguage];
  const text = offer.normalized_price_text || "";
  if (text) return text;
  const value = offer.normalized_price_per_unit_tnd;
  if (value !== null && value !== undefined) {
    return `${formatNumber(value)} TND/${currentLanguage === "fr" ? "unité" : "unit"}`;
  }
  return labels.notAvailable;
}

function renderLandedCostSection(data) {
  const labels = copy[currentLanguage];
  const landed = data.landed_cost || {};
  const components = landed.components || [];
  const componentLabels = {
    supplier_price: currentLanguage === "fr" ? "Prix fournisseur" : "Supplier price",
    shipping: currentLanguage === "fr" ? "Transport estimé" : "Estimated shipping",
    customs: currentLanguage === "fr" ? "Droits / taxes d'import" : "Import duties / taxes",
    handling: currentLanguage === "fr" ? "Manutention" : "Handling",
    misc: currentLanguage === "fr" ? "Autres charges" : "Other charges"
  };
  const rows = components.map((component) => `<tr>
      <td>${escapeHtml(componentLabels[component.label_key] || component.label_key)}</td>
      <td>${component.value_tnd !== null && component.value_tnd !== undefined ? `${formatNumber(component.value_tnd)} TND` : labels.notAvailable}</td>
      <td>${provenanceBadge(component.provenance)}</td>
    </tr>`).join("");
  const totalRow = `<tr>
      <td><strong>${currentLanguage === "fr" ? "COÛT RENDU ESTIMÉ" : "ESTIMATED LANDED COST"}</strong></td>
      <td><strong>${landed.total_tnd !== null && landed.total_tnd !== undefined ? `${formatNumber(landed.total_tnd)} TND` : labels.notAvailable}</strong></td>
      <td>${provenanceBadge(landed.partial_estimate ? "estimate" : "computed")}</td>
    </tr>`;
  return `
    <section class="result-band wide">
      <div class="section-head">
        <h2>${labels.landedCostTitle}</h2>
        ${sectionConfidence(labels.landedCostTitle, landed.total_tnd != null ? "medium" : "low", landed.partial_estimate ? labels.partialEstimateNote : "")}
      </div>
      <table class="report-table">
        <thead><tr><th>${labels.componentCol}</th><th>${labels.valueCol}</th><th>${labels.provenanceCol}</th></tr></thead>
        <tbody>${rows}${totalRow}</tbody>
      </table>
      ${landed.partial_estimate && landed.total_tnd != null ? `<p class="hidden-note">${labels.partialEstimateNote}</p>` : ""}
      ${landed.note ? `<p class="hidden-note">${escapeHtml(landed.note)}</p>` : ""}
    </section>
  `;
}

function renderTunisiaMarketSection(data, retail) {
  const labels = copy[currentLanguage];
  const retailOffers = data.retail_offers || [];
  const wholesaleOffers = data.tunisia_wholesale_offers || [];
  const hasWholesale = wholesaleOffers.some(
    (offer) => (offer.price_min_tnd !== null && offer.price_min_tnd !== undefined) || offer.price_text
  );
  const confidenceLevel = retailOffers.length >= 3 ? "high" : retailOffers.length ? "medium" : "low";
  const rows = retailOffers.map((offer) => `<tr>
      <td><strong>${escapeHtml(offer.seller_name || "-")}</strong>${offer.city ? `<br><span class="hidden-note">${escapeHtml(offer.city)}</span>` : ""}</td>
      <td>${escapeHtml(offer.brand || "-")}</td>
      <td>${escapeHtml(offer.product_title || "-")}</td>
      <td>${escapeHtml(offer.volume_text || "-")}</td>
      <td>${escapeHtml(offer.price_range_tnd || (offer.price_tnd !== null && offer.price_tnd !== undefined ? `${formatNumber(offer.price_tnd)} TND` : labels.notAvailable))}</td>
      <td>${escapeHtml(normalizedPriceText(offer))}</td>
      <td>${escapeHtml(offer.availability || labels.notAvailable)}</td>
      <td>${escapeHtml(offer.city || labels.notAvailable)}</td>
      <td>${offer.page_type === "category_or_listing" ? (currentLanguage === "fr" ? "Page catégorie" : "Listing page") : (currentLanguage === "fr" ? "Page produit" : "Product page")}</td>
      <td>${offer.source_url ? `<a href="${escapeAttribute(offer.source_url)}" target="_blank" rel="noopener noreferrer">${labels.sourceLink}</a>` : "-"}</td>
    </tr>`).join("");
  const wholesaleRows = wholesaleOffers.map((offer) => `<tr>
      <td>${escapeHtml(offer.name || labels.notAvailable)}</td>
      <td>${escapeHtml(offer.product_title || labels.notAvailable)}</td>
      <td>${escapeHtml(tndRangeOrNA(offer.price_min_tnd, offer.price_max_tnd))}</td>
      <td>${offer.source_url ? `<a href="${escapeAttribute(offer.source_url)}" target="_blank" rel="noopener noreferrer">${labels.sourceLink}</a>` : labels.notAvailable}</td>
      <td>${confidenceInline(offer.confidence)}</td>
    </tr>`).join("");
  const wholesaleNotice = hasWholesale ? `<table class="report-table">
      <thead><tr><th>${labels.supplierCol}</th><th>${labels.productCol}</th><th>${labels.priceCol}</th><th>${labels.sourceLink}</th><th>${labels.trustCol}</th></tr></thead>
      <tbody>${wholesaleRows}</tbody>
    </table>` : `<p>${labels.noWholesalePrice}</p>`;
  return `
    <section class="result-band wide">
      <div class="section-head">
        <h2>${labels.tunisiaMarketTitle}</h2>
        ${sectionConfidence(`${labels.retailPrices}`, confidenceLevel, currentLanguage === "fr"
          ? `${retailOffers.length} vendeur(s) comparable(s) trouvé(s)`
          : `${retailOffers.length} comparable seller(s) found`)}
      </div>
      <h3>${labels.retailPrices}</h3>
      ${rows ? `<table class="report-table">
        <thead><tr><th>${labels.sellerCol}</th><th>${labels.brandCol}</th><th>${labels.productCol}</th><th>${labels.volumeCol}</th><th>${labels.priceCol}</th><th>${labels.normalizedPrice}</th><th>${labels.availabilityCol}</th><th>${labels.cityCol}</th><th>${labels.priceTypeCol}</th><th>${labels.sourceLink}</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>` : `<table class="report-table"><thead><tr><th>${labels.sellerCol}</th><th>${labels.brandCol}</th><th>${labels.productCol}</th><th>${labels.volumeCol}</th><th>${labels.priceCol}</th><th>${labels.normalizedPrice}</th><th>${labels.priceTypeCol}</th><th>${labels.sourceLink}</th></tr></thead><tbody></tbody></table><p>${currentLanguage === "fr" ? "Aucune offre détail trouvée." : "No retail offer found."}</p>`}
      <div class="metric-grid">
        ${metric(copy[currentLanguage].minPrice, tnd(retail.retail_min_tnd))}
        ${metric(copy[currentLanguage].maxPrice, tnd(retail.retail_max_tnd))}
        ${metric(copy[currentLanguage].averagePrice, tnd(retail.retail_avg_tnd))}
      </div>
      <h3>${labels.wholesalePricesShort}</h3>
      ${wholesaleNotice}
      ${retail.competition_notes ? `<p class="hidden-note">${escapeHtml(retail.competition_notes)}</p>` : ""}
    </section>
  `;
}

function renderComparabilitySection(data) {
  const labels = copy[currentLanguage];
  const comparability = data.comparability || {};
  const levels = { high: labels.comparabilityHigh, medium: labels.comparabilityMedium, low: labels.comparabilityLow, unknown: labels.comparabilityLow };
  const levelKey = comparability.level || "unknown";
  return `
    <section class="result-band wide">
      <div class="section-head">
        <h2>${labels.comparabilityTitle}</h2>
        <span class="pill">Comparabilité : ${levels[levelKey] || levels.unknown}</span>
      </div>
      <div class="comparability-banner comparability-${levelKey}">
        ${(comparability.reasons || []).map((reason) => `<span>${escapeHtml(reason)}</span>`).join("")}
        ${comparability.normalization_note ? `<span class="hidden-note">${escapeHtml(comparability.normalization_note)}</span>` : ""}
      </div>
      ${comparability.margin_is_indicative_only ? `<div class="margin-warning">${labels.indicativeMarginWarning}</div>` : ""}
    </section>
  `;
}

function renderCompetitionSection(data) {
  const labels = copy[currentLanguage];
  const retailOffers = data.retail_offers || [];
  const brands = [...new Set(retailOffers.map((offer) => offer.brand).filter(Boolean))];
  const sellers = [...new Set(retailOffers.map((offer) => offer.seller_name).filter(Boolean))];
  const level = data.competition_level || "unknown";
  const levelLabels = currentLanguage === "fr"
    ? { low: "FAIBLE", medium: "MOYEN", high: "FORT", unknown: "INCONNUE" }
    : { low: "LOW", medium: "MEDIUM", high: "HIGH", unknown: "UNKNOWN" };
  const justification = currentLanguage === "fr"
    ? {
        low: "Peu de vendeurs et de marques établies ont été trouvés sur ce produit.",
        medium: "Plusieurs vendeurs et marques se partagent le marché, avec une pression prix modérée.",
        high: "De nombreux vendeurs et marques internationales établies sont déjà présents : la pression prix est forte.",
        unknown: "Les données collectées ne permettent pas d'évaluer l'intensité concurrentielle."
      }[level]
    : {
        low: "Few established sellers and brands were found for this product.",
        medium: "Several sellers and brands share the market with moderate price pressure.",
        high: "Many established international sellers and brands are present: price pressure is strong.",
        unknown: "Collected data does not allow assessing competitive intensity."
      }[level];
  return `
    <section class="result-band wide">
      <div class="section-head">
        <h2>${labels.competitionTitle}</h2>
        <span class="pill">${labels.competitionLevelLabel} : ${levelLabels[level] || levelLabels.unknown}</span>
      </div>
      <h3>${labels.competitorsFound}</h3>
      ${brands.length || sellers.length ? `<div class="metric-grid">
        ${brands.length ? metric(currentLanguage === "fr" ? "Marques trouvées" : "Brands found", brands.join(", ")) : ""}
        ${sellers.length ? metric(currentLanguage === "fr" ? "Vendeurs trouvés" : "Sellers found", sellers.slice(0, 8).join(", ")) : ""}
      </div>` : `<p>${currentLanguage === "fr" ? "Aucune marque ou vendeur identifié dans les données collectées." : "No brand or seller identified in the collected data."}</p>`}
      <h3>${labels.competitionJustification}</h3>
      <p>${escapeHtml(justification)}</p>
    </section>
  `;
}

function renderProfitabilitySection(data, profit, quantityUnits) {
  const labels = copy[currentLanguage];
  const margin = profit.gross_margin_per_unit_before_marketing_tnd;
  const selling = profit.estimated_selling_price_tnd;
  const landed = (data.landed_cost || {}).total_tnd ?? profit.estimated_landed_cost_per_unit_tnd;
  let marginPercent = null;
  if (margin !== null && margin !== undefined && selling) {
    marginPercent = Math.round(margin / selling * 1000) / 10;
  }
  const netAfterAds = profit.net_profit_for_1000_after_marketing_tnd ?? profit.estimated_profit_for_1000_units_tnd;
  return `
    <section class="result-band wide">
      <div class="section-head">
        <h2>${labels.rentabilityTitle}</h2>
        <span class="pill">${labels.hypotheses}</span>
      </div>
      <div class="detail-columns">
        <section class="detail-section">
          <h3>${labels.observedData}</h3>
          <div class="detail-pairs">
            ${detailPair(labels.unitBuyPrice, tnd(profit.source_unit_price_tnd))}
            ${detailPair(labels.observedRetailPrice, tnd(selling))}
            ${detailPair(labels.grossMarginUnit, tnd(margin))}
          </div>
        </section>
        <section class="detail-section">
          <h3>${labels.hypotheses}</h3>
          <div class="detail-pairs">
            ${detailPair(labels.landedCost, landed != null ? `${tnd(landed)} (${provenanceText("estimate")})` : tnd(null))}
            ${detailPair(labels.adsBudgetHypothetical, `${digitalAdvertisingBudgetRange(data)} (${provenanceText("estimate")})`)}
            ${detailPair(labels.quantityAnalyzed, `${quantityUnits} ${currentLanguage === "fr" ? "unités" : "units"}`)}
          </div>
        </section>
      </div>
      <table class="report-table">
        <thead><tr><th>${labels.metricColumn}</th><th>${labels.valueCol}</th></tr></thead>
        <tbody>
          ${reportRow(labels.recommendedSalePrice, tnd(selling))}
          ${reportRow(labels.landedCost, tnd(landed))}
          ${reportRow(labels.grossMarginUnit, tnd(margin))}
          ${reportRow(labels.marginPercent, marginPercent !== null ? `${marginPercent}%` : labels.notAvailable)}
          ${reportRow(labels.grossProfitTotal, tnd(margin !== null && margin !== undefined ? margin * quantityUnits : null))}
          ${reportRow(labels.adsBudgetHypothetical, digitalAdvertisingBudgetRange(data))}
          ${reportRow(labels.profitAfterAds, tnd(netAfterAds !== null && netAfterAds !== undefined ? netAfterAds : (profit.net_profit_for_1000_after_advertising_min_tnd)))}
        </tbody>
      </table>
      <p class="hidden-note">${labels.formulaNote}</p>
      ${profit.pricing_basis ? `<p class="hidden-note">${escapeHtml(profit.pricing_basis)}</p>` : ""}
      ${(profit.assumptions || []).length ? `<details><summary>${labels.hypotheses}</summary><ul class="decision-factors">${profit.assumptions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></details>` : ""}
    </section>
  `;
}

function scoreBar(label, value, max) {
  const percent = max > 0 ? Math.max(0, Math.min(100, Math.round(value / max * 100))) : 0;
  return `<div class="score-bar-row">
    <span>${escapeHtml(label)}</span>
    <div class="score-bar-track"><div class="score-bar-fill" style="width:${percent}%"></div></div>
    <strong>${value}/${max}</strong>
  </div>`;
}

function criterionLabel(key) {
  const labels = copy[currentLanguage];
  const map = {
    market_demand: currentLanguage === "fr" ? "Demande marché" : "Market demand",
    margin: currentLanguage === "fr" ? "Marge" : "Margin",
    sourcing: currentLanguage === "fr" ? "Sourcing" : "Sourcing",
    competition: currentLanguage === "fr" ? "Concurrence" : "Competition",
    ads_potential: currentLanguage === "fr" ? "Potentiel Ads" : "Ads potential",
    recurrence: currentLanguage === "fr" ? "Récurrence" : "Recurrence",
    differentiation: currentLanguage === "fr" ? "Différenciation" : "Differentiation",
    risk: currentLanguage === "fr" ? "Risque" : "Risk"
  };
  return map[key] || key;
}

function renderDetailedScoring(data) {
  const labels = copy[currentLanguage];
  const scoring = data.detailed_scoring || {};
  const criteria = scoring.criteria || [];
  if (!criteria.length) return "";
  return `
    <div class="detail-section">
      <h3>${labels.scoringDetailTitle}</h3>
      ${criteria.map((criterion) => `
        ${scoreBar(criterionLabel(criterion.key), Number(criterion.score) || 0, Number(criterion.max_score) || 0)}
        <p class="hidden-note" style="margin-top:-4px">${escapeHtml(criterion.justification || "")}</p>
      `).join("")}
      <p><strong>${currentLanguage === "fr" ? "TOTAL" : "TOTAL"} : ${Number(scoring.total) || 0}/100</strong></p>
    </div>
  `;
}

function renderCommercialPotentialSection(data) {
  const labels = copy[currentLanguage];
  const score = Number(data.commercial_potential_score) || 0;
  const scoring = data.detailed_scoring || {};
  const criteria = scoring.criteria || [];
  const demand = criteria.find((criterion) => criterion.key === "market_demand");
  const recurrence = criteria.find((criterion) => criterion.key === "recurrence");
  const audiences = currentLanguage === "fr"
    ? "Particuliers, garages, mécaniciens, centres auto, revendeurs, grossistes — selon la catégorie analysée."
    : "Individuals, garages, mechanics, auto centers, resellers, wholesalers — depending on the analyzed category.";
  return `
    <section class="result-band">
      <div class="section-head">
        <h2>${labels.commercialPotentialTitle}</h2>
        <span class="pill">${score} / 100</span>
      </div>
      <p>${audiences}</p>
      ${demand ? `<p class="hidden-note">${escapeHtml(demand.justification)}</p>` : ""}
      ${recurrence ? `<p class="hidden-note">${escapeHtml(recurrence.justification)}</p>` : ""}
    </section>
  `;
}

function renderAdsPotentialSection(data) {
  const labels = copy[currentLanguage];
  const score = Number(data.ads_potential_score) || 0;
  const level = score >= 60 ? (currentLanguage === "fr" ? "FORT" : "HIGH") : score >= 35 ? (currentLanguage === "fr" ? "MOYEN" : "MEDIUM") : (currentLanguage === "fr" ? "FAIBLE" : "LOW");
  const behavior = currentLanguage === "fr"
    ? "Achat utilitaire et de remplacement : le client cherche un produit précis, compare les prix puis achète en ligne ou en magasin."
    : "Utility and replacement purchase: the buyer searches for a specific product, compares prices, then buys online or in-store.";
  const angles = currentLanguage === "fr"
    ? "Compatibilité précise, rapport qualité/prix, disponibilité locale, livraison rapide."
    : "Precise compatibility, value for money, local availability, fast delivery.";
  return `
    <section class="result-band">
      <div class="section-head">
        <h2>${labels.adsPotentialTitle}</h2>
        <span class="pill">Ads : ${score} / 100</span>
      </div>
      <div class="metric-grid">
        ${metric(labels.adsMeta, level)}
        ${metric(labels.adsGoogle, level)}
        ${metric(labels.purchaseType, currentLanguage === "fr" ? "Achat réfléchi / renouvellement" : "Considered / renewal purchase")}
        ${metric(labels.acquisitionDifficulty, level === "HIGH" || level === "FORT" ? (currentLanguage === "fr" ? "Élevée (concurrence ads)" : "High (ads competition)") : currentLanguage === "fr" ? "Modérée" : "Moderate")}
        ${metric(labels.repurchasePotential, currentLanguage === "fr" ? "À confirmer selon la récurrence produit" : "To confirm based on product recurrence")}
      </div>
      <p class="hidden-note"><strong>${labels.customerBehavior} :</strong> ${escapeHtml(behavior)}</p>
      <p class="hidden-note"><strong>${labels.adAngles} :</strong> ${escapeHtml(angles)}</p>
      <p class="hidden-note">${labels.adsQualitativeNote}</p>
    </section>
  `;
}

function renderRisksSection(data) {
  const labels = copy[currentLanguage];
  const risks = [
    ...(Array.isArray(data.profitability_estimate?.risks) ? data.profitability_estimate.risks : []),
    ...(Array.isArray(data.warnings) ? data.warnings : [])
  ].filter(Boolean);
  const unique = [...new Set(risks)];
  return `
    <section class="result-band wide">
      <h2>${labels.risksTitle}</h2>
      ${unique.length ? `<ul class="decision-factors">${unique.map((risk) => `<li>${escapeHtml(risk)}</li>`).join("")}</ul>` : `<p>${currentLanguage === "fr" ? "Aucun risque majeur identifié dans les données." : "No major risk identified in the data."}</p>`}
    </section>
  `;
}

function renderActionsSection(data) {
  const labels = copy[currentLanguage];
  const actions = decisionChangeActions(data, normalizeDecisionScores(data.decision_scores || {}), displayedRecommendation(
    data.recommendation || "investigate_more",
    normalizeDecisionScores(data.decision_scores || {})
  ));
  return `
    <section class="result-band wide">
      <h2>${labels.actionsTitle}</h2>
      <ol class="decision-factors" style="padding-left:18px">${actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ol>
      <h3>${labels.decisionJustificationTitle}</h3>
      <p>${escapeHtml(decisionScoreExplanation(data, normalizeDecisionScores(data.decision_scores || {}), displayedRecommendation(data.recommendation || "investigate_more", normalizeDecisionScores(data.decision_scores || {}))))}</p>
    </section>
  `;
}

function renderSourcesSection(data) {
  const labels = copy[currentLanguage];
  const sources = data.sources || [];
  const typeLabels = {
    china_sourcing: currentLanguage === "fr" ? "Sourcing Chine" : "China sourcing",
    tunisia_sourcing: currentLanguage === "fr" ? "Gros Tunisie" : "Tunisia wholesale",
    tunisia_retail: currentLanguage === "fr" ? "Détail Tunisie" : "Tunisia retail"
  };
  const rows = sources.map((source) => `<tr>
      <td style="max-width:280px">${source.url ? `<a href="${escapeAttribute(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title || source.url)}</a>` : escapeHtml(source.title)}</td>
      <td>${escapeHtml(typeLabels[source.type] || source.type || "-")}</td>
      <td>${escapeHtml(source.data_used || labels.notAvailable)}</td>
      <td>${escapeHtml(source.date || labels.notAvailable)}</td>
      <td>${provenanceBadge("source")} ${confidenceInline(source.confidence)}</td>
    </tr>`).join("");
  return `
    <section class="result-band wide">
      <div class="section-head">
        <h2>${labels.sourcesTitle}</h2>
        <span class="pill">${sources.length}</span>
      </div>
      <p>${labels.sourcesIntro}</p>
      ${rows ? `<table class="report-table">
        <thead><tr><th>${labels.sourceLink}</th><th>${currentLanguage === "fr" ? "Type" : "Type"}</th><th>${labels.dataUsed}</th><th>${labels.dateCol}</th><th>${labels.trustCol}</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>` : `<p>${labels.notAvailable}</p>`}
    </section>
  `;
}
