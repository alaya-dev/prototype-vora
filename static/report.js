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
if (typeof applyStaticTranslations === "function") applyStaticTranslations();

function renderPrototypeResult(data) {
  productPhoto.innerHTML = renderProductImage(data);
  const labels = copy[currentLanguage];
  const retail = deriveRetailSummary(data.retail_market_summary || {});
  const profit = deriveProfitability(data);
  const quantityUnits = analysisQuantityUnits(data);
  const scores = normalizeDecisionScores(data.decision_scores || {});
  const recommendation = displayedRecommendation(data.recommendation || "investigate_more", scores, data);
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
    <section id="finalDecision" data-report-section="final-decision" class="result-band wide">
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
    observed: { cls: "badge-observed", label: "OBSERVED" },
    computed: { cls: "badge-computed", label: "CALCULATED" },
    estimate: { cls: "badge-estimate", label: "ESTIMATE" },
    unavailable: { cls: "badge-unavailable", label: "INSUFFICIENT DATA" },
    assumption: { cls: "badge-estimate", label: "ASSUMPTION" },
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
    observed: "OBSERVED",
    computed: "CALCULATED",
    estimate: "ESTIMATE",
    unavailable: "INSUFFICIENT DATA",
    assumption: "ASSUMPTION",
  };
  return labels[provenance] || labels.unavailable;
}

function sectionConfidence(label, level, note) {
  return `<div class="section-confidence">${escapeHtml(label)} : ${confidenceInline(level)}${note ? ` <span>— ${escapeHtml(note)}</span>` : ""}</div>`;
}

function renderExecutiveSummary(data, scores, recommendation, profit) {
  const labels = copy[currentLanguage];
  const summaryText = executiveSummaryText(data, scores, recommendation, profit);
  const overallScore = reportOverallScore(data, scores);
  const productName = frenchProductName(data);
  const comparability = data.comparability || {};
  const landed = data.landed_cost || {};
  const retail = data.retail_market_summary || {};
  const locale = currentLanguage === "fr" ? "fr-FR" : "en-GB";
  const contextLine = currentLanguage === "fr"
    ? `${data.target_market || "Tunisie"} · Sourcing : ${data.sourcing_country || "Chine"} · ${new Date().toLocaleDateString(locale)}`
    : `${data.target_market || "Tunisia"} · Sourcing: ${data.sourcing_country || "China"} · ${new Date().toLocaleDateString(locale)}`;
  return `
    <section id="executiveSummary" data-report-section="executive-summary" class="result-band wide report-cover">
      <div class="report-header">
          <div>
          <img class="report-cover-logo" src="/logo/Nexora_logo_transparent_clean_cropped.png" alt="NEXORA">
          <div class="eyebrow">${currentLanguage === "fr" ? "Rapport d'opportunité produit" : "Product opportunity report"}</div>
          <p class="report-tagline">INTELLIGENT SOURCING. SMARTER GROWTH.</p>
          <h2>${escapeHtml(productName)}</h2>
          <p>${escapeHtml(contextLine)}</p>
        </div>
        <img class="report-cover-image" src="${escapeAttribute(data.product_image_url || fallbackProductImage(productName))}" alt="${escapeAttribute(productName)}" onerror="handleProductImageError(this, '${escapeAttribute(productName)}')">
        <span class="pill">${recommendationText(recommendation)} · ${overallScore}/100</span>
      </div>
      <div class="metric-grid report-header-facts">
        ${metric(labels.marketAnalyzed, data.target_market || labels.notAvailable)}
        ${metric(labels.sourcingCountryCol, data.sourcing_country || labels.notAvailable)}
        ${metric("Date", new Date().toLocaleDateString(locale))}
        ${metric(labels.decisionConfidence, confidenceText(scores.confidence))}
        ${metric(currentLanguage === "fr" ? "Score d'opportunité" : "Opportunity score", `${overallScore}/100`)}
        ${metric(currentLanguage === "fr" ? "Décision finale" : "Final decision", recommendationText(recommendation))}
      </div>
      <h3>${labels.execSummary}</h3>
      <p>${escapeHtml(summaryText)}</p>
      <div class="metric-grid">
        ${metric(labels.landedCost, tnd(landed.total_tnd ?? profit.estimated_landed_cost_per_unit_tnd))}
        ${metric(labels.averagePrice, tnd(profit.estimated_selling_price_tnd ?? retail.retail_avg_tnd))}
        ${metric(labels.grossMarginPerUnit, tnd(profit.gross_margin_per_unit_before_marketing_tnd))}
        ${metric(labels.decisionConfidence, confidenceText(scores.confidence))}
      </div>
      ${comparability.margin_is_indicative_only ? `<div class="margin-warning">${labels.indicativeMarginWarning}</div>` : ""}
    </section>
  `;
}

function reportOverallScore(data, scores) {
  const score = Number(displayScoring(data).total);
  return Number.isFinite(score) ? Math.max(0, Math.min(100, Math.round(score))) : scores.go_percent;
}

function displayScoring(data) {
  const source = data?.detailed_scoring || {};
  const criteria = (source.criteria || []).map((criterion) => ({ ...criterion }));
  const profit = deriveProfitability(data);
  const selling = finiteOrNull(profit.estimated_selling_price_tnd);
  const margin = finiteOrNull(profit.gross_margin_per_unit_before_marketing_tnd);
  const marginCriterion = criteria.find((criterion) => criterion.key === "margin");
  if (marginCriterion) {
    if (selling === null || margin === null) {
      marginCriterion.score = 0;
      marginCriterion.justification = currentLanguage === "fr"
        ? "Marge non calculable : l’unité du prix fournisseur n’est pas confirmée."
        : "Margin cannot be calculated: the supplier price unit is not confirmed.";
    } else {
      const marginPercent = selling > 0 ? margin / selling * 100 : 0;
      const baseScore = marginPercent >= 30 ? 20 : marginPercent >= 20 ? 15 : marginPercent >= 10 ? 10 : marginPercent > 0 ? 5 : 0;
      const selected = (data.china_offers || []).filter((offer) => offer.source_url).sort((a, b) => Number(a.price_min_tnd || Infinity) - Number(b.price_min_tnd || Infinity))[0];
      let penalty = selected?.confidence === "low" ? 2 : 0;
      if (data.landed_cost?.partial_estimate) penalty += 1;
      if (!(data.tunisia_wholesale_offers || []).length) penalty += 1;
      if (String(data.decision_scores?.confidence || "").toLowerCase() === "low") penalty += 1;
      penalty = Math.min(penalty, baseScore);
      marginCriterion.score = baseScore - penalty;
      marginCriterion.justification = currentLanguage === "fr"
        ? `Marge brute d’environ ${marginPercent.toFixed(1)} %. Pénalité de fiabilité des données : -${penalty} point(s).`
        : `Gross margin is about ${marginPercent.toFixed(1)}%. Economic score was adjusted by a data reliability penalty of -${penalty} point(s).`;
    }
  }
  return {
    ...source,
    criteria,
    total: Math.min(100, criteria.reduce((sum, criterion) => sum + (Number(criterion.score) || 0), 0)),
  };
}

function executiveSummaryText(data, scores, recommendation, profit) {
  const market = finiteOrNull(profit.estimated_selling_price_tnd);
  const landed = finiteOrNull(profit.estimated_landed_cost_per_unit_tnd);
  const margin = finiteOrNull(profit.gross_margin_per_unit_before_marketing_tnd);
  const score = reportOverallScore(data, scores);
  const decision = recommendationText(recommendation);
  if (market === null || landed === null || margin === null) {
    return currentLanguage === "fr"
      ? `La décision finale est ${decision} avec un score de ${score}/100. La marge ne peut pas être calculée de manière fiable avec les données disponibles.`
      : `The final decision is ${decision} with a score of ${score}/100. Gross margin cannot be calculated reliably from the available data.`;
  }
  const marginPercent = market > 0 ? (margin / market) * 100 : 0;
  const profitability = marginPercent >= 40
    ? (currentLanguage === "fr" ? "La rentabilité théorique apparaît attractive" : "Theoretical profitability appears attractive")
    : (currentLanguage === "fr" ? "La rentabilité théorique reste à confirmer" : "Theoretical profitability remains to be confirmed");
  if (currentLanguage === "fr") {
    return `${profitability} sur la base des données disponibles. Le prix marché comparable est de ${formatNumber(market)} TND, contre un coût rendu estimé de ${formatNumber(landed)} TND et une marge brute de ${formatNumber(margin)} TND (${marginPercent.toFixed(1)}%). La décision ${decision} reste conditionnelle à la confirmation du devis fournisseur, des coûts logistiques et douaniers, de la qualité et de la demande tunisienne.`;
  }
  return `${profitability} based on the available data. The comparable market price is ${formatNumber(market)} TND, against an estimated landed cost of ${formatNumber(landed)} TND and a gross margin of ${formatNumber(margin)} TND (${marginPercent.toFixed(1)}%). The ${decision} decision remains conditional on confirming the supplier quote, logistics and customs costs, product quality, and Tunisian demand.`;
}

function renderProductIdentification(data, understanding, productDescription) {
  const labels = copy[currentLanguage];
  const specs = Array.isArray(understanding.technical_specs) ? understanding.technical_specs : [];
  return `
    <section id="productAnalyzed" data-report-section="product-analyzed" class="result-band wide">
      <div class="section-head">
        <h2>${labels.productAnalyzed}</h2>
        ${sectionConfidence(labels.productAnalyzed, "medium", "")}
      </div>
      <div class="metric-grid">
        ${metric(labels.requestedProduct, understanding.original_product || labels.notAvailable)}
        ${metric(labels.normalizedProduct, frenchProductName(data))}
        ${metric(labels.category, frenchCategoryName(understanding.product_category))}
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

function frenchProductName(data) {
  const product = data?.product_understanding || {};
  return product.french_search_name || product.original_product || product.normalized_product || copy.fr.product;
}

function frenchCategoryName(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "automotive fluids" || normalized === "automotive fluid") return "Fluides automobiles";
  return value || copy.fr.notAvailable;
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
  const coverageWarning = offers.length < 3
    ? `<div class="coverage-warning"><strong>${currentLanguage === "fr" ? "Couverture sourcing limitée" : "Limited sourcing coverage"}</strong><span>${currentLanguage === "fr" ? "Moins de trois fournisseurs fiables avec prix produit ont été retenus." : "Fewer than three reliable suppliers with product-level pricing were retained."}</span></div>`
    : "";
  return `
    <section id="internationalSourcing" data-report-section="international-sourcing" class="result-band wide">
      <div class="section-head">
        <h2>${labels.sourcingInternational}</h2>
        ${sectionConfidence(labels.sourcingInternational, confidence, currentLanguage === "fr"
          ? (offers.length ? `${offers.length} fournisseur(s) trouvé(s) mais coût logistique incomplet.` : "aucun fournisseur trouvé")
          : (offers.length ? `${offers.length} supplier(s) found but logistics cost incomplete.` : "no supplier found"))}
      </div>
      ${coverageWarning}
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

function targetPackageText(data) {
  const product = data?.product_understanding || {};
  const parsed = parseVolume([
    product.normalized_product,
    product.original_product,
    ...(Array.isArray(product.technical_specs) ? product.technical_specs : [])
  ].filter(Boolean).join(" "));
  if (!parsed) return copy[currentLanguage].notAvailable;
  return `${formatNumber(parsed.value)} ${parsed.unit}`;
}

function supplierUnitPriceText(data) {
  const offers = Array.isArray(data?.china_offers) ? data.china_offers : [];
  const offer = offers
    .filter((item) => finiteOrNull(item.price_min_tnd) !== null)
    .sort((a, b) => finiteOrNull(a.price_min_tnd) - finiteOrNull(b.price_min_tnd))[0];
  if (!offer) return copy[currentLanguage].notAvailable;
  const unit = String(offer.price_unit || "").toLowerCase();
  const unitLabel = /liter|litre|\bper\s*l\b|\/\s*l\b|\bl\b/.test(unit)
    ? "L"
    : /kilogram|\bper\s*kg\b|\/\s*kg\b/.test(unit)
      ? "kg"
      : /piece|unit|pcs|bottle|bidon|package/.test(unit)
        ? (currentLanguage === "fr" ? "unité" : "unit")
        : (offer.price_unit || (currentLanguage === "fr" ? "unité" : "unit"));
  return `${formatNumber(Number(offer.price_min_tnd))} TND/${unitLabel}`;
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
    supplier_price: currentLanguage === "fr" ? "Coût fournisseur équivalent au format analysé" : "Supplier cost equivalent to analyzed package",
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
  const targetPackage = targetPackageText(data);
  const supplierUnit = supplierUnitPriceText(data);
  const supplierComponent = components.find((component) => component.label_key === "supplier_price");
  return `
    <section id="landedCost" data-report-section="landed-cost" class="result-band wide">
      <div class="section-head">
        <h2>${labels.landedCostTitle}</h2>
        ${sectionConfidence(labels.landedCostTitle, landed.total_tnd != null ? "medium" : "low", landed.partial_estimate ? labels.partialEstimateNote : "")}
      </div>
      <div class="metric-grid">
        ${metric(currentLanguage === "fr" ? "Format analysé" : "Analyzed package", targetPackage)}
        ${metric(currentLanguage === "fr" ? "Prix source observé" : "Observed source price", supplierUnit)}
        ${metric(currentLanguage === "fr" ? "Coût produit équivalent" : "Equivalent product cost", supplierComponent?.value_tnd != null ? tnd(supplierComponent.value_tnd) : labels.notAvailable)}
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
  const comparableReference = comparableRetailReference(data);
  return `
    <section id="tunisiaMarket" data-report-section="tunisia-market" class="result-band wide">
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
        ${metric(currentLanguage === "fr" ? "Fourchette retail retenue" : "Retained retail price range", retail.retail_price_range_tnd || labels.notAvailable)}
        ${metric(currentLanguage === "fr" ? "Référence marché comparable" : "Comparable market price", tnd(comparableReference))}
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
    <section id="comparability" data-report-section="comparability" class="result-band wide">
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
  const level = sellers.length < 3 && brands.length < 3 ? "unknown" : (data.competition_level || "unknown");
  const levelLabels = currentLanguage === "fr"
    ? { low: "FAIBLE", medium: "MOYEN", high: "FORT", unknown: "DONNÉES INSUFFISANTES" }
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
    <section id="competitionAnalysis" data-report-section="competition" class="result-band wide">
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
  const marketReference = comparableRetailReference(data) ?? selling;
  const landed = (data.landed_cost || {}).total_tnd ?? profit.estimated_landed_cost_per_unit_tnd;
  let marginPercent = null;
  if (margin !== null && margin !== undefined && selling) {
    marginPercent = Math.round(margin / selling * 1000) / 10;
  }
  const netAfterAds = profit.net_profit_for_1000_after_marketing_tnd ?? profit.estimated_profit_for_1000_units_tnd;
  const targetPackage = targetPackageText(data);
  const supplierUnit = supplierUnitPriceText(data);
  const equivalentProductCost = profit.source_unit_price_tnd;
  return `
    <section id="profitability" data-report-section="profitability" class="result-band wide">
      <div class="section-head">
        <h2>${labels.rentabilityTitle}</h2>
        <span class="pill">${labels.hypotheses}</span>
      </div>
      <p class="data-quality-line">${provenanceBadge("assumption")} ${escapeHtml(currentLanguage === "fr" ? "Le transport, les droits et la publicité sont des hypothèses administratives quand aucune preuve source n'est disponible." : "Shipping, duties, and advertising are administrative assumptions when no source evidence is available.")}</p>
      <div class="detail-columns">
        <section class="detail-section">
          <h3>${labels.observedData}</h3>
          <div class="detail-pairs">
            ${detailPair(labels.unitBuyPrice, `${supplierUnit} · ${targetPackage}`)}
            ${detailPair(currentLanguage === "fr" ? "Coût produit équivalent" : "Equivalent product cost", tnd(equivalentProductCost))}
            ${detailPair(labels.observedRetailPrice, tnd(marketReference))}
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
          ${reportRow(currentLanguage === "fr" ? "Référence marché comparable" : "Comparable market reference", tnd(marketReference))}
          ${reportRow(currentLanguage === "fr" ? "Prix source observé" : "Observed source price", supplierUnit)}
          ${reportRow(currentLanguage === "fr" ? "Format analysé" : "Analyzed package", targetPackage)}
          ${reportRow(currentLanguage === "fr" ? "Coût produit équivalent" : "Equivalent product cost", tnd(equivalentProductCost))}
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
  const scoring = displayScoring(data);
  const criteria = scoring.criteria || [];
  if (!criteria.length) return "";
  return `
    <div id="detailedScoring" data-report-section="detailed-scoring" class="detail-section">
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
  const retailCount = Array.isArray(data.retail_offers) ? data.retail_offers.length : 0;
  const evidence = retailCount
    ? (currentLanguage === "fr" ? `${retailCount} référence(s) retail tunisienne(s) retenue(s).` : `${retailCount} retained Tunisia retail reference(s).`)
    : (currentLanguage === "fr" ? "Aucune référence retail tunisienne retenue." : "No Tunisia retail reference retained.");
  return `
    <section id="commercialPotential" data-report-section="commercial-potential" class="result-band">
      <div class="section-head">
        <h2>${labels.commercialPotentialTitle}</h2>
        <span class="pill">${score} / 100</span>
      </div>
      <p>${escapeHtml(currentLanguage === "fr" ? "Évaluation qualitative fondée uniquement sur les références et signaux retenus." : "Qualitative assessment based only on retained references and signals.")}</p>
      <p class="hidden-note">${escapeHtml(evidence)}</p>
      ${demand ? `<p class="hidden-note">${escapeHtml(demand.justification)}</p>` : ""}
      ${recurrence ? `<p class="hidden-note">${escapeHtml(recurrence.justification)}</p>` : ""}
    </section>
  `;
}

function renderAdsPotentialSection(data) {
  const labels = copy[currentLanguage];
  const score = Number(data.ads_potential_score) || 0;
  const level = score >= 60 ? (currentLanguage === "fr" ? "FORT" : "HIGH") : score >= 35 ? (currentLanguage === "fr" ? "MOYEN" : "MEDIUM") : (currentLanguage === "fr" ? "FAIBLE" : "LOW");
  const adsCriterion = (data.detailed_scoring?.criteria || []).find((criterion) => criterion.key === "ads_potential");
  return `
    <section id="adsPotential" data-report-section="ads-potential" class="result-band">
      <div class="section-head">
        <h2>${labels.adsPotentialTitle}</h2>
        <span class="pill">Ads : ${score} / 100</span>
      </div>
      <div class="metric-grid">
        ${metric(labels.adsMeta, level)}
        ${metric(labels.adsGoogle, level)}
        ${metric(labels.purchaseType, currentLanguage === "fr" ? "Non confirmé par des données comportementales." : "Not confirmed by behavioral data.")}
        ${metric(labels.acquisitionDifficulty, currentLanguage === "fr" ? "Non disponible" : "Not available")}
        ${metric(labels.repurchasePotential, currentLanguage === "fr" ? "Non confirmé" : "Not confirmed")}
      </div>
      ${adsCriterion ? `<p class="hidden-note">${escapeHtml(adsCriterion.justification || "")}</p>` : ""}
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
  if ((data.china_offers || []).length < 3) risks.push(currentLanguage === "fr" ? "Couverture fournisseurs Chine limitée." : "Limited China supplier coverage.");
  if (!(data.tunisia_wholesale_offers || []).length) risks.push(currentLanguage === "fr" ? "Aucun prix de gros tunisien public fiable." : "No reliable public Tunisia wholesale price.");
  if ((data.retail_offers || []).length < 3) risks.push(currentLanguage === "fr" ? "Couverture retail tunisienne limitée." : "Limited Tunisia retail coverage.");
  if (data.landed_cost?.partial_estimate) risks.push(currentLanguage === "fr" ? "Les coûts logistiques et d'importation restent des estimations." : "Logistics and import costs remain estimates.");
  const unique = [...new Set(risks)];
  return `
    <section id="mainRisks" data-report-section="risks" class="result-band wide">
      <h2>${labels.risksTitle}</h2>
      ${unique.length ? `<ul class="decision-factors">${unique.map((risk) => `<li>${escapeHtml(risk)}</li>`).join("")}</ul>` : `<p>${currentLanguage === "fr" ? "Aucun risque majeur identifié dans les données." : "No major risk identified in the data."}</p>`}
    </section>
  `;
}

function renderActionsSection(data) {
  const labels = copy[currentLanguage];
  const actions = decisionChangeActions(data, normalizeDecisionScores(data.decision_scores || {}), displayedRecommendation(
    data.recommendation || "investigate_more",
    normalizeDecisionScores(data.decision_scores || {}),
    data
  ));
  return `
    <section id="recommendedActions" data-report-section="recommended-actions" class="result-band wide">
      <h2>${labels.actionsTitle}</h2>
      <ol class="decision-factors" style="padding-left:18px">${actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ol>
      <h3>${labels.decisionJustificationTitle}</h3>
      <p>${escapeHtml(decisionScoreExplanation(data, normalizeDecisionScores(data.decision_scores || {}), displayedRecommendation(data.recommendation || "investigate_more", normalizeDecisionScores(data.decision_scores || {}), data)))}</p>
    </section>
  `;
}

function renderSourcesSection(data) {
  const labels = copy[currentLanguage];
  const sources = (data.sources || []).filter((source) => source && source.url && !String(source.data_used || "").toLowerCase().startsWith("context evidence"));
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
    <section id="sourcesEvidence" data-report-section="sources-evidence" class="result-band wide">
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
