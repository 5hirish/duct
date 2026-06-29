// Country names for the locations autocomplete — zero dependency, zero network.
//
// We inline only the ISO 3166-1 alpha-2 CODES (compact, ~250 two-letter strings)
// and let the browser's built-in `Intl.DisplayNames` turn them into localized
// names at runtime. Paired with a native <datalist>, that gives type-to-search
// country autocomplete with no library and no requests. Free-typed values still
// work (TikTok occasionally lists a region not in the set).

const CODES = (
  "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL " +
  "BM BN BO BQ BR BS BT BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW " +
  "CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE " +
  "GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HN HR HT HU ID IE IL IM IN IO " +
  "IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS " +
  "LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY " +
  "MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT " +
  "PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV " +
  "SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG US UY UZ VA VC " +
  "VE VG VI VN VU WF WS YE YT ZA ZM ZW"
).split(" ");

let _names = null;

/** Sorted list of localized country names (memoized). Falls back to raw codes
 *  if Intl.DisplayNames isn't available. */
export function countryNames() {
  if (_names) return _names;
  try {
    const dn = new Intl.DisplayNames(["en"], { type: "region" });
    _names = CODES
      .map((c) => {
        try { return dn.of(c) || c; } catch { return c; }
      })
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b));
  } catch {
    _names = [...CODES].sort();
  }
  return _names;
}
