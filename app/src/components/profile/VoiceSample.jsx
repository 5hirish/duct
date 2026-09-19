"use client";

/**
 * The same finding, written the way the chosen preset would write it.
 *
 * A profile page is a list of words that describe words, which is the worst
 * possible way to choose between them: "Practitioner" means nothing until it
 * sits next to "Executive" on the same sentence. So the page shows the
 * sentence.
 *
 * Canned, not generated. A live rewrite is a model call per click on a settings
 * page, paid by the user, to render a preview of prose they have not asked for
 * yet. The strings are real output shapes from the insights agent, trimmed.
 *
 * The language switch shows a translated sample for the languages we can write
 * one for, and falls back to English with a note for the rest — which is the
 * honest thing to show, since the agent will still write in the chosen
 * language and only this preview cannot.
 */

import { Trans } from "@lingui/react/macro";

// Not in the interface catalogue on purpose. These are what the *agent* writes,
// in the communication language chosen above — a different axis from the
// interface language (see "Three language fields" in AGENTS.md). Routing the
// English fallback through the catalogue would show a German-interface user a
// German sample under a note that says "Shown in English".
const SAMPLES = {
  executive: {
    English: "Paid search wasted $1,840 last month. Three terms, no conversions. Cutting them pays for the quarter's tooling.",
    Spanish: "La búsqueda de pago desperdició 1.840 $ el mes pasado. Tres términos, cero conversiones. Eliminarlos paga las herramientas del trimestre.",
    French: "Le référencement payant a gaspillé 1 840 $ le mois dernier. Trois termes, aucune conversion. Les couper finance les outils du trimestre.",
    German: "Bezahlte Suche verschwendete letzten Monat 1.840 $. Drei Begriffe, keine Conversions. Sie zu streichen finanziert die Tools des Quartals.",
    Portuguese: "A busca paga desperdiçou 1.840 $ no mês passado. Três termos, nenhuma conversão. Cortá-los paga as ferramentas do trimestre.",
  },
  practitioner: {
    English: "Three search terms took 18% of spend and converted nobody: \"free crm template\", \"crm tutorial\", \"duct tape\". Add them as negatives on the Search campaign.",
    Spanish: "Tres términos de búsqueda se llevaron el 18% del gasto sin ninguna conversión: «free crm template», «crm tutorial», «duct tape». Añádelos como negativos en la campaña de Search.",
    French: "Trois requêtes ont pris 18 % du budget sans convertir : « free crm template », « crm tutorial », « duct tape ». Ajoutez-les en mots-clés négatifs sur la campagne Search.",
    German: "Drei Suchbegriffe nahmen 18 % der Ausgaben und konvertierten niemanden: „free crm template“, „crm tutorial“, „duct tape“. Als auszuschließende Keywords in der Search-Kampagne hinzufügen.",
    Portuguese: "Três termos de pesquisa levaram 18% do investimento e não converteram ninguém: «free crm template», «crm tutorial», «duct tape». Adicione-os como negativos na campanha de Search.",
  },
  technical: {
    English: "customer_acquisition_search: 18.4% of 30d spend on 3 terms, 0 conversions attributed (GA4 key event purchase, 30d window). Broad match on \"crm\" is the leak. Add exact negatives, then re-check search terms in 7 days.",
    Spanish: "customer_acquisition_search: 18,4% del gasto de 30 días en 3 términos, 0 conversiones atribuidas (evento clave de GA4 «purchase», ventana de 30 días). La concordancia amplia en «crm» es la fuga. Añade negativos exactos y revisa los términos en 7 días.",
    French: "customer_acquisition_search : 18,4 % des dépenses sur 30 j pour 3 requêtes, 0 conversion attribuée (événement clé GA4 « purchase », fenêtre 30 j). Le requête large sur « crm » est la fuite. Ajoutez des négatifs exacts, puis revérifiez sous 7 jours.",
    German: "customer_acquisition_search: 18,4 % der 30-Tage-Ausgaben auf 3 Begriffe, 0 zugeordnete Conversions (GA4-Schlüsselereignis „purchase“, 30-Tage-Fenster). Broad Match auf „crm“ ist das Leck. Exakte Negative hinzufügen, in 7 Tagen erneut prüfen.",
    Portuguese: "customer_acquisition_search: 18,4% do investimento de 30 dias em 3 termos, 0 conversões atribuídas (evento-chave do GA4 «purchase», janela de 30 dias). A correspondência ampla em «crm» é a fuga. Adicione negativas exatas e reveja em 7 dias.",
  },
};

const FALLBACK_LANGUAGE = "English";

export default function VoiceSample({ preset = "practitioner", language = "" }) {
  const byLanguage = SAMPLES[preset] || SAMPLES.practitioner;
  const wanted = language || FALLBACK_LANGUAGE;
  const text = byLanguage[wanted] || byLanguage[FALLBACK_LANGUAGE];
  const untranslated = Boolean(language) && !byLanguage[language];

  return (
    <figure className="pf-sample">
      <figcaption className="pf-sample-cap"><Trans>A finding, written for you</Trans></figcaption>
      {/* aria-live so a screen reader hears the rewrite the sighted user sees;
          without it the sample is a silent change on a control that appears to
          do nothing. */}
      <blockquote className="pf-sample-text" aria-live="polite">
        {text}
      </blockquote>
      {untranslated && (
        <p className="pf-sample-note">
          <Trans>Shown in English. Duct still writes to you in {language}; only this preview does not.</Trans>
        </p>
      )}
    </figure>
  );
}
