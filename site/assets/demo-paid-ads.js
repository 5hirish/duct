/* demo-paid-ads.js — Paid Ads demo variant config + data
   Loaded before demo.js. Provides DUCT_DEMO_CONFIG.fill (Engine A)
   which handles its own aggregation and report population.
   All innerHTML uses esc() on static data constants, never user input. */
(function () {
  var PLATFORM_QUALITY = {
    'Google Ads':   1.0,
    'Meta':         0.8,
    'Twitter / X':  0.5,
    'LinkedIn Ads': 1.2
  };

  var CROSS_PLATFORM_SIGNALS = {
    cac: {
      level: 'yellow', pill: '\uD83D\uDFE1 Cross-channel',
      title: '~34% estimated audience overlap between Google and Meta \u2014 paying twice to reach the same people',
      body: 'Excluding existing Google converters from Meta Prospecting audiences could cut Meta CPL by roughly $28. Upload your Google Ads conversion list as an exclusion audience in Meta.',
      ownerName: 'Sofia Alvarez', assignee: 'Paid media', followUp: 'Upload Google converter list as exclusion in Meta Ads'
    },
    roas: {
      level: 'yellow', pill: '\uD83D\uDFE1 Cross-channel',
      title: 'Meta brand-awareness impressions precede 38% of Google Brand conversions \u2014 channels are interdependent',
      body: 'Cutting Meta budget to fix blended ROAS would likely suppress Google Brand ROAS within 3 weeks. Model the halo effect before reallocating across channels.',
      ownerName: 'Daniel Kim', assignee: 'Paid media + Analytics', followUp: 'Model Meta halo impact before cutting Meta spend'
    },
    pipeline: {
      level: 'green', pill: '\uD83D\uDFE2 Cross-channel',
      title: 'Sequential exposure pattern cuts days-to-close by 6 days \u2014 you\u2019re not replicating it intentionally',
      body: 'Leads that touch search intent first, then see a social retarget ad, close 6 days faster. Build a deliberate cross-channel retargeting sequence to replicate this pattern at scale.',
      ownerName: 'Nina Park', assignee: 'Marketing ops', followUp: 'Build retargeting sequence across selected channels'
    }
  };

  var PLATFORM_DATA = {
    'Google Ads': {
      cac: {
        campaigns: [
          { name: 'Google \u00B7 Search \u00B7 Brand (exact match)',        spend: '$8,200',  spendRaw: 8200,  cpa: '$98',  roas: '4.2x', roasRaw: 4.2, conversions: 84, revenue: 34440, status: 'Scale \u2191', cls: 'camp-status-scale'   },
          { name: 'Google \u00B7 Search \u00B7 Competitor conquest',        spend: '$3,600',  spendRaw: 3600,  cpa: '$241', roas: '1.3x', roasRaw: 1.3, conversions: 15, revenue:  4680, status: 'Monitor',       cls: 'camp-status-monitor' }
        ],
        signals: [
          { level: 'red',   pill: '\uD83D\uDD34 Critical', title: 'Competitor keyword CPA at $241 \u2014 2.3\u00D7 your $98 brand CPA',            body: 'Quality scores averaging 4/10 on three high-volume competitor terms. Adding exact-match negatives to the brand campaign and aligning ad copy to landing pages could halve CPL within 2 weeks.', ownerName: 'Marcus Chen', assignee: 'Paid media', followUp: 'Add exact-match negatives; fix quality scores on top 3 competitor terms' },
          { level: 'green', pill: '\uD83D\uDFE2 Win',      title: 'Brand Search CPA $98 \u2014 best performer in the mix, room to scale',         body: 'Brand campaign is budget-capped, not performance-capped. Increasing budget 20% could add 15\u201320 conversions at current efficiency with no creative change needed.',                    ownerName: 'Elena Voss',  assignee: 'Paid media', followUp: 'Increase Google Brand budget ~20%' }
        ],
        spendRaw: 11800, conversions: 99, revenue: 39120, sparkline: [0.28, 0.32, 0.36, 0.40, 0.45, 0.50, 0.56]
      },
      roas: {
        campaigns: [
          { name: 'Google \u00B7 Search \u00B7 Brand (exact match)',         spend: '$8,200', spendRaw: 8200,  cpa: '$98',  roas: '4.2x', roasRaw: 4.2, conversions: 84, revenue: 34440, status: 'Scale \u2191', cls: 'camp-status-scale'   },
          { name: 'Google \u00B7 Display \u00B7 In-market SaaS (tCPA $150)', spend: '$4,100', spendRaw: 4100,  cpa: '$201', roas: '1.2x', roasRaw: 1.2, conversions: 20, revenue:  4920, status: 'Monitor',       cls: 'camp-status-monitor' }
        ],
        signals: [
          { level: 'red',   pill: '\uD83D\uDD34 Critical', title: 'Google Display ROAS 1.2x \u2014 impressions up 80%, conversions flat',          body: 'Auto-applied audience expansion is broadening reach without improving conversion quality. Disable audience expansion and tighten in-market segments before scaling further.',                                ownerName: 'Sofia Alvarez', assignee: 'Paid media', followUp: 'Disable audience expansion; review Display targeting' },
          { level: 'green', pill: '\uD83D\uDFE2 Win',      title: 'Google Brand ROAS 4.2x \u2014 budget-capped, not performance-capped',           body: 'Reallocating $2K from Display to Brand would improve blended ROAS to ~2.8x immediately. Brand campaign has headroom at current bid efficiency.',                                                   ownerName: 'Daniel Kim',   assignee: 'Paid media', followUp: 'Shift ~$2K from Display to Brand campaign' }
        ],
        spendRaw: 12300, conversions: 104, revenue: 39360, sparkline: [0.60, 0.62, 0.65, 0.58, 0.52, 0.47, 0.43]
      },
      pipeline: {
        campaigns: [
          { name: 'Google \u00B7 Search \u00B7 Brand + competitor conquest',  spend: '$8,200', spendRaw: 8200, cpa: '$98',  roas: '4.2x', roasRaw: 4.2, conversions: 84, revenue: 34440, status: 'Scale \u2191', cls: 'camp-status-scale'   },
          { name: 'Google \u00B7 Search \u00B7 BOFU (demo & trial intent)',    spend: '$5,400', spendRaw: 5400, cpa: '$144', roas: '2.9x', roasRaw: 2.9, conversions: 37, revenue: 15660, status: 'Monitor',       cls: 'camp-status-monitor' }
        ],
        signals: [
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch', title: 'BOFU keyword MQL\u2192deal rate falling 38%\u219222% \u2014 broad match mixing intent', body: 'Broad match expansion is pulling in informational queries (how does, what is, pricing comparison) that MQL but don\u2019t convert. Check the search term report and add negatives for informational head terms.', ownerName: 'Marcus Chen', assignee: 'Paid media', followUp: 'Add negatives for informational terms in BOFU campaign' },
          { level: 'green',  pill: '\uD83D\uDFE2 Win',   title: 'Brand keywords driving 32% deal rate \u2014 highest of all Google campaigns',          body: 'Brand keywords convert MQLs to deals 2\u00D7 faster than BOFU keywords. Budget is $8.2K vs $5.4K on BOFU (22% deal rate). Reallocating $2K to Brand would improve deal throughput.',                     ownerName: 'Elena Voss',  assignee: 'Paid media', followUp: 'Rebalance $2K from BOFU to Brand campaign' }
        ],
        spendRaw: 13600, conversions: 121, revenue: 57120, sparkline: [0.42, 0.44, 0.46, 0.43, 0.40, 0.38, 0.36]
      }
    },
    'Meta': {
      cac: {
        campaigns: [
          { name: 'Meta \u00B7 Prospecting \u00B7 Advantage+ (US 25\u201354)',   spend: '$11,400', spendRaw: 11400, cpa: '$312', roas: '0.8x', roasRaw: 0.8, conversions: 37, revenue:  9120, status: 'Pause',       cls: 'camp-status-pause'  },
          { name: 'Meta \u00B7 Retargeting \u00B7 30d site visitors',            spend: '$3,200',  spendRaw:  3200, cpa: '$89',  roas: '3.6x', roasRaw: 3.6, conversions: 36, revenue: 11520, status: 'Scale \u2191', cls: 'camp-status-scale'  }
        ],
        signals: [
          { level: 'red',   pill: '\uD83D\uDD34 Critical', title: 'Meta Prospecting CAC $312 \u2014 43% over your $218 target',                  body: 'Spend up 38% MoM but conversions fell 8%. Pause or cut Meta Prospecting 30% until creative is refreshed. Retargeting (CPA $89) should absorb the reallocated budget.', ownerName: 'James Okonkwo', assignee: 'Paid media', followUp: 'Pause or trim Meta Prospecting; shift budget to Retargeting' },
          { level: 'green', pill: '\uD83D\uDFE2 Win',      title: 'Meta Retargeting CPA $89 \u2014 3.6x ROAS, clear headroom to scale',          body: 'Retargeting audiences (site visitors + email list) converting at $89 vs $312 for cold prospecting. Increasing retargeting budget $2K would add ~22 conversions at current efficiency.',        ownerName: 'Priya Shah',   assignee: 'Paid media', followUp: 'Increase Meta Retargeting budget ~$2K' }
        ],
        spendRaw: 14600, conversions: 73, revenue: 20640, sparkline: [0.18, 0.25, 0.35, 0.48, 0.62, 0.75, 0.92]
      },
      roas: {
        campaigns: [
          { name: 'Meta \u00B7 Prospecting \u00B7 LAL 1% \u00B7 180d high-AOV buyers', spend: '$12,500', spendRaw: 12500, cpa: '$312', roas: '0.8x', roasRaw: 0.8, conversions: 40, revenue: 10000, status: 'Pause',       cls: 'camp-status-pause'  },
          { name: 'Meta \u00B7 Retargeting \u00B7 Video 75% + email list',              spend: '$3,800',  spendRaw:  3800, cpa: '$94',  roas: '3.4x', roasRaw: 3.4, conversions: 40, revenue: 12920, status: 'Scale \u2191', cls: 'camp-status-scale'  }
        ],
        signals: [
          { level: 'red',   pill: '\uD83D\uDD34 Critical', title: 'Meta Prospecting ROAS 0.8x \u2014 losing $1.25 for every $1 spent',            body: 'This campaign alone is pulling blended ROAS from 3.1x to 2.1x. Pause immediately or shift budget to Retargeting (3.4x). Do not wait for the next review cycle.',                     ownerName: 'James Okonkwo', assignee: 'Paid media', followUp: 'Pause Meta Prospecting or reallocate to Retargeting this week' },
          { level: 'green', pill: '\uD83D\uDFE2 Win',      title: 'Meta Retargeting ROAS 3.4x \u2014 23% of spend, 58% of Meta revenue',          body: 'Retargeting audiences dramatically outperform cold prospecting. Increasing budget by $3K would recapture ~$10K in revenue at current efficiency.',                                                ownerName: 'Priya Shah',   assignee: 'Paid media', followUp: 'Increase Meta Retargeting budget ~$3K' }
        ],
        spendRaw: 16300, conversions: 80, revenue: 22920, sparkline: [0.70, 0.68, 0.72, 0.60, 0.54, 0.48, 0.44]
      },
      pipeline: {
        campaigns: [
          { name: 'Meta \u00B7 Retargeting \u00B7 30d site + video 75% viewers', spend: '$4,800', spendRaw:  4800, cpa: '$68',  roas: '3.8x', roasRaw: 3.8, conversions: 70, revenue: 18240, status: 'Scale \u2191', cls: 'camp-status-scale'   },
          { name: 'Meta \u00B7 Prospecting \u00B7 Advantage+ (B2B job titles)',   spend: '$7,600', spendRaw:  7600, cpa: '$287', roas: '1.1x', roasRaw: 1.1, conversions: 26, revenue:  8360, status: 'Monitor',       cls: 'camp-status-monitor' }
        ],
        signals: [
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch', title: 'Meta Prospecting MQL quality low \u2014 11% deal rate vs 28% company average', body: 'B2B job-title targeting isn\u2019t filtering by company size or seniority. Adding company revenue ($10M+) and seniority level could lift deal rate to 20%+ within 2 weeks without reducing volume significantly.', ownerName: 'Amara Osei',  assignee: 'Marketing + Paid media', followUp: 'Add company revenue and seniority filters to Meta Prospecting' },
          { level: 'green',  pill: '\uD83D\uDFE2 Win',   title: 'Meta Retargeting driving 3\u00D7 more pipeline per dollar than cold prospecting', body: 'Retargeting converting at $68 CPL vs $287 cold prospecting. Increasing retargeting budget $2K would add ~29 MQLs at current efficiency.',                                                             ownerName: 'Alex Rivera', assignee: 'Paid media',              followUp: 'Increase Meta Retargeting budget ~$2K' }
        ],
        spendRaw: 12400, conversions: 96, revenue: 26600, sparkline: [0.52, 0.56, 0.50, 0.54, 0.46, 0.42, 0.38]
      }
    },
    'LinkedIn Ads': {
      cac: {
        campaigns: [
          { name: 'LinkedIn \u00B7 Sponsored content \u00B7 ABM retargeting',   spend: '$5,200', spendRaw: 5200, cpa: '$187', roas: '1.9x', roasRaw: 1.9, conversions: 28, revenue:  9880, status: 'Monitor', cls: 'camp-status-monitor' },
          { name: 'LinkedIn \u00B7 Lead gen \u00B7 Decision-maker ICP (NA)',     spend: '$3,800', spendRaw: 3800, cpa: '$228', roas: '1.6x', roasRaw: 1.6, conversions: 17, revenue:  6080, status: 'Monitor', cls: 'camp-status-monitor' }
        ],
        signals: [
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch', title: 'LinkedIn CTR down 38% WoW \u2014 creative fatigue setting in',             body: 'Top 3 LinkedIn ads have been running 6+ weeks. Frequency rising above 4.2. Refresh creative before CTR decline compounds into CPA rise \u2014 lead time is 1\u20132 weeks.',    ownerName: 'Priya Shah', assignee: 'Creative',   followUp: 'Next sprint \u2014 refresh top 3 LinkedIn ad creatives' },
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch', title: 'Lead Gen CPA $228 \u2014 5% over $218 target, slipping further',           body: 'Adding company revenue ($10M+) and seniority level to ICP targeting could improve CPA to ~$185 within 2 weeks without reducing volume significantly.',                  ownerName: 'Nina Park',  assignee: 'Paid media', followUp: 'Tighten LinkedIn ICP: add company revenue + seniority level filters' }
        ],
        spendRaw: 9000, conversions: 45, revenue: 15960, sparkline: [0.50, 0.48, 0.46, 0.44, 0.42, 0.40, 0.38]
      },
      roas: {
        campaigns: [
          { name: 'LinkedIn \u00B7 Sponsored content \u00B7 Product demo (ABM)', spend: '$5,200', spendRaw: 5200, cpa: '$187', roas: '1.9x', roasRaw: 1.9, conversions: 28, revenue:  9880, status: 'Monitor', cls: 'camp-status-monitor' },
          { name: 'LinkedIn \u00B7 Conversation ads \u00B7 VP & Director ICP',   spend: '$2,800', spendRaw: 2800, cpa: '$164', roas: '2.1x', roasRaw: 2.1, conversions: 17, revenue:  5880, status: 'Monitor', cls: 'camp-status-monitor' }
        ],
        signals: [
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch', title: 'LinkedIn blended ROAS 1.9x \u2014 positive but below 2.5x target',          body: 'Strong pipeline quality but volume is insufficient to drive blended ROAS above target on its own. Consider tracking LinkedIn primarily by pipeline quality, not ROAS.',          ownerName: 'Daniel Kim',    assignee: 'Paid media + Leadership', followUp: 'Reframe LinkedIn KPI from ROAS to pipeline quality' },
          { level: 'green',  pill: '\uD83D\uDFE2 Win',   title: 'Conversation Ads ROAS 2.1x \u2014 outperforming Sponsored Content',         body: 'VP/Director-targeted Conversation Ads converting better than broader ABM. Shifting $1K from Sponsored to Conversation would add ~6 conversions at higher ROAS.',              ownerName: 'Sofia Alvarez', assignee: 'Paid media',              followUp: 'Shift $1K from Sponsored Content to Conversation Ads' }
        ],
        spendRaw: 8000, conversions: 45, revenue: 15760, sparkline: [0.52, 0.50, 0.48, 0.47, 0.46, 0.45, 0.44]
      },
      pipeline: {
        campaigns: [
          { name: 'LinkedIn \u00B7 Lead gen \u00B7 Demo requests (NA English)',   spend: '$11,800', spendRaw: 11800, cpa: '$287', roas: '1.1x', roasRaw: 1.1, conversions: 41, revenue: 12980, status: 'Monitor',       cls: 'camp-status-monitor' },
          { name: 'LinkedIn \u00B7 Sponsored content \u00B7 Case study (VP/Dir)', spend: '$4,200',  spendRaw:  4200, cpa: '$198', roas: '1.7x', roasRaw: 1.7, conversions: 21, revenue:  7140, status: 'Scale \u2191',   cls: 'camp-status-scale'   }
        ],
        signals: [
          { level: 'red',   pill: '\uD83D\uDD34 Critical', title: 'LinkedIn ad-attributed deals stalled \u2014 0 new deals in 14 days',         body: 'LinkedIn is generating MQLs but none are progressing past the initial call. Review ICP alignment on targeting, check sales follow-up cadence, and confirm offer-to-ICP fit with the sales team.', ownerName: 'Amara Osei', assignee: 'Marketing + Sales', followUp: 'This week \u2014 align ICP, check targeting filters and sales follow-up cadence' },
          { level: 'green', pill: '\uD83D\uDFE2 Win',      title: 'LinkedIn Case Study ads \u2014 32% deal rate, best paid pipeline channel',    body: 'VP/Director case study content converts MQLs to Opportunity stage 2\u00D7 faster than lead gen forms. Increasing budget $2K would add ~10 high-quality MQLs.',                                    ownerName: 'Nina Park',   assignee: 'Paid media',        followUp: 'Increase Case Study ad budget ~$2K' }
        ],
        spendRaw: 16000, conversions: 62, revenue: 20120, sparkline: [0.62, 0.60, 0.57, 0.54, 0.50, 0.47, 0.44]
      }
    },
    'Twitter / X': {
      cac: {
        campaigns: [{ name: 'X (Twitter) \u00B7 Promoted posts \u00B7 SaaS pain point copy', spend: '$2,800', spendRaw: 2800, cpa: '$342', roas: '0.7x', roasRaw: 0.7, conversions: 8, revenue: 1960, status: 'Pause', cls: 'camp-status-pause' }],
        signals: [
          { level: 'red',    pill: '\uD83D\uDD34 Critical', title: 'X Ads CPA $342 \u2014 57% above $218 target, weakest performer in the mix', body: 'Promoted posts are driving clicks but not bottom-funnel action. Pause for 2 weeks, test a new hook-led creative, then re-evaluate. Consider shifting budget to retargeting on higher-intent channels.', ownerName: 'Alex Rivera',  assignee: 'Paid media', followUp: 'Pause X Promoted posts; test new hook-led creative' },
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch',    title: 'X CPM $4.20 \u2014 cheap reach, but no retargeting list built yet',          body: 'Awareness impressions are cost-efficient but without pixel-based retargeting, engaged users are not being re-engaged. Add a retargeting campaign to convert X engagement into pipeline.',   ownerName: 'Marcus Chen', assignee: 'Paid media', followUp: 'Set up X pixel retargeting for engaged users' }
        ],
        spendRaw: 2800, conversions: 8, revenue: 1960, sparkline: [0.44, 0.42, 0.40, 0.38, 0.36, 0.34, 0.32]
      },
      roas: {
        campaigns: [{ name: 'X (Twitter) \u00B7 Promoted posts \u00B7 B2B SaaS messaging', spend: '$2,800', spendRaw: 2800, cpa: '$342', roas: '0.7x', roasRaw: 0.7, conversions: 8, revenue: 1960, status: 'Pause', cls: 'camp-status-pause' }],
        signals: [
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch', title: 'X Ads ROAS 0.7x \u2014 below breakeven, users arriving with informational intent', body: 'Test shifting the campaign objective to brand awareness and measure assisted conversions via multi-touch attribution over 30 days before cutting budget entirely.',                          ownerName: 'James Okonkwo', assignee: 'Paid media', followUp: 'Switch X objective to brand awareness; measure assisted conversions' },
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch', title: 'X creative CTR 0.21% \u2014 industry average is 0.40%',                           body: 'Plain-text posts with a bold claim are outperforming image ads in A/B data. Refresh creative with a direct hook and a stat-led headline. Test at least 3 variants.',                   ownerName: 'Priya Shah',    assignee: 'Creative',   followUp: 'Refresh X creative: stat-led plain-text variants' }
        ],
        spendRaw: 2800, conversions: 8, revenue: 1960, sparkline: [0.48, 0.45, 0.42, 0.38, 0.34, 0.30, 0.28]
      },
      pipeline: {
        campaigns: [{ name: 'X (Twitter) \u00B7 Brand awareness \u00B7 B2B thought leadership', spend: '$2,400', spendRaw: 2400, cpa: '$380', roas: '0.6x', roasRaw: 0.6, conversions: 6, revenue: 1440, status: 'Monitor', cls: 'camp-status-monitor' }],
        signals: [
          { level: 'yellow', pill: '\uD83D\uDFE1 Watch', title: 'X Ads MQL rate 4% \u2014 lowest of all selected channels',                            body: 'X drives awareness touchpoints but rarely converts last-click. Attribute correctly in a multi-touch model before cutting budget \u2014 it may be assisting higher-intent conversions downstream.', ownerName: 'Nina Park',  assignee: 'Analytics', followUp: 'Review X contribution in multi-touch attribution model' },
          { level: 'green',  pill: '\uD83D\uDFE2 Win',   title: '340 engaged X users this week not yet retargeted \u2014 missed pipeline opportunity', body: 'Adding pixel-based retargeting to users who engaged with posts (likes, link clicks, video views 50%+) could generate 8\u201312 MQLs at an estimated $85 CPL based on comparable retargeting pools.',   ownerName: 'Alex Rivera', assignee: 'Paid media', followUp: 'Set up X pixel retargeting for engaged users' }
        ],
        spendRaw: 2400, conversions: 6, revenue: 1440, sparkline: [0.38, 0.36, 0.34, 0.32, 0.30, 0.28, 0.26]
      }
    }
  };

  /* --- Engine A helper functions (used by fillPaidAds closure) --- */
  function fmtDollarsK(n) { return n >= 1000 ? '$' + (n / 1000).toFixed(1) + 'K' : '$' + Math.round(n); }

  function aggregateCampaigns(metricKey, platforms) {
    var result = [];
    for (var i = 0; i < platforms.length; i++) {
      var pd = PLATFORM_DATA[platforms[i]];
      if (pd && pd[metricKey]) { result = result.concat(pd[metricKey].campaigns); }
    }
    return result;
  }
  function aggregateSignals(metricKey, platforms) {
    var all = [];
    for (var i = 0; i < platforms.length; i++) {
      var pd = PLATFORM_DATA[platforms[i]];
      if (pd && pd[metricKey]) { all = all.concat(pd[metricKey].signals); }
    }
    var pri = { red: 0, yellow: 1, green: 2 };
    all.sort(function (a, b) { return (pri[a.level] || 0) - (pri[b.level] || 0); });
    var top2 = all.slice(0, 2);
    if (platforms.length >= 2 && CROSS_PLATFORM_SIGNALS[metricKey]) {
      return top2.concat([CROSS_PLATFORM_SIGNALS[metricKey]]);
    }
    return all.slice(0, 3);
  }
  function aggregateSparkline(metricKey, platforms) {
    var sums = [0, 0, 0, 0, 0, 0, 0], count = 0;
    for (var i = 0; i < platforms.length; i++) {
      var pd = PLATFORM_DATA[platforms[i]];
      if (pd && pd[metricKey] && pd[metricKey].sparkline) {
        var sp = pd[metricKey].sparkline;
        for (var j = 0; j < 7 && j < sp.length; j++) { sums[j] += sp[j]; }
        count++;
      }
    }
    if (count === 0) { return [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]; }
    var mn = Math.min.apply(null, sums), mx = Math.max.apply(null, sums), rng = mx - mn || 1;
    var result = [];
    for (var k = 0; k < 7; k++) { result.push(parseFloat(((sums[k] - mn) / rng).toFixed(3))); }
    return result;
  }
  function aggregateKPIs(metricKey, platforms) {
    var totalSpend = 0, totalConv = 0, totalRevenue = 0;
    for (var i = 0; i < platforms.length; i++) {
      var pd = PLATFORM_DATA[platforms[i]];
      if (pd && pd[metricKey]) {
        totalSpend   += pd[metricKey].spendRaw    || 0;
        totalConv    += pd[metricKey].conversions || 0;
        totalRevenue += pd[metricKey].revenue     || 0;
      }
    }
    var actualCAC   = totalConv  > 0 ? Math.round(totalSpend / totalConv) : 0;
    var blendedROAS = totalSpend > 0 ? parseFloat((totalRevenue / totalSpend).toFixed(1)) : 0;
    var cacTarget   = 218;
    var cacDiff     = actualCAC - cacTarget;
    var cacPct      = Math.abs(Math.round(cacDiff / cacTarget * 100));
    var cacDot      = cacDiff >  cacTarget * 0.05 ? 'red'   : cacDiff < -cacTarget * 0.05 ? 'green' : 'yellow';
    var cacTrend    = cacDiff > 0 ? 'down' : 'up';
    var cacDelta    = cacDiff > 0 ? cacPct + '% vs $' + cacTarget + ' target' : cacPct + '% below $' + cacTarget + ' target';
    var roasDot     = blendedROAS >= 2.5 ? 'green' : blendedROAS >= 1.5 ? 'yellow' : 'red';
    var roasTrend   = blendedROAS >= 2.5 ? 'up' : 'down';
    var roasDelta   = { cac: '12% WoW', roas: '18% WoW', pipeline: '4% WoW' }[metricKey] || '\u2014';
    var convLabel   = metricKey === 'pipeline' ? totalConv + ' MQLs' : String(totalConv);
    return {
      totalSpend: totalSpend, totalConv: totalConv,
      kpis: {
        cac:   { val: '$' + actualCAC,              delta: cacDelta,  dot: cacDot,  trend: cacTrend  },
        roas:  { val: blendedROAS.toFixed(1) + 'x', delta: roasDelta, dot: roasDot, trend: roasTrend },
        spend: { val: fmtDollarsK(totalSpend),       delta: '42% MoM', dot: 'grey',  trend: 'up'      },
        conv:  { val: convLabel,                     delta: '8% WoW',  dot: 'red',   trend: 'down'    }
      }
    };
  }
  function deriveVerdict(signals) {
    if (!signals || !signals.length) { return { verdictClass: 'grey', verdictText: 'No signals available' }; }
    var top   = signals[0];
    var emoji = { red: '\uD83D\uDD34', yellow: '\uD83D\uDFE1', green: '\uD83D\uDFE2' };
    return { verdictClass: top.level, verdictText: (emoji[top.level] || '') + ' ' + top.title };
  }
  function deriveUnitEcon(metricKey, platforms) {
    var weightedQ = 0, spent = 0;
    for (var i = 0; i < platforms.length; i++) {
      var p  = platforms[i];
      var pd = PLATFORM_DATA[p];
      if (pd && pd[metricKey]) {
        var s = pd[metricKey].spendRaw || 0;
        weightedQ += s * (PLATFORM_QUALITY[p] || 1.0);
        spent     += s;
      }
    }
    var q      = spent > 0 ? weightedQ / spent : 1.0;
    var ltvNum = parseFloat((q * 2.0).toFixed(1));
    var ltv    = ltvNum.toFixed(1) + 'x';
    var verdict = ltvNum >= 2.0 ? '\uD83D\uDFE2 Healthy' : ltvNum >= 1.5 ? '\uD83D\uDFE1 Breakeven' : '\uD83D\uDD34 Losing money';
    var short   = ltvNum >= 2.0 ? 'healthy'              : ltvNum >= 1.5 ? 'breakeven'               : 'losing money';
    return { cps: '$218', ltv: ltv, verdict: verdict, summary: ' \u00B7 ' + ltv + ' LTV:CAC \u00B7 ' + short };
  }
  function formatReportDate() {
    var now = new Date(), end = new Date(now), start = new Date(now);
    start.setDate(start.getDate() - 6);
    var dow = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return dow[start.getDay()] + ', ' + months[start.getMonth()] + ' ' + start.getDate() +
      ' \u2013 ' + dow[end.getDay()] + ', ' + months[end.getMonth()] + ' ' + end.getDate() + ', ' + end.getFullYear() + ' \u00B7 7-day window';
  }

  /* Shared KPI trend SVGs */
  var KPI_SVG_UP   = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="m18 15-6-6-6 6"/></svg>';
  var KPI_SVG_DOWN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>';
  var KPI_SVG_FLAT = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 12h14"/></svg>';

  function applyKpiTrend(el, k) {
    if (!el || !k) { return; }
    var tone = k.dot || 'grey', tr = k.trend || 'flat';
    el.className = 'kpi-trend tone-' + tone;
    el.innerHTML = tr === 'up' ? KPI_SVG_UP : tr === 'down' ? KPI_SVG_DOWN : KPI_SVG_FLAT; /* static SVG */
  }
  function buildSparkSVGPaidAds(points) {
    var w = 130, h = 44, px = 4, py = 6;
    var mn  = Math.min.apply(null, points), mx  = Math.max.apply(null, points), rng = mx - mn || 1;
    var linePts = [];
    for (var j = 0; j < points.length; j++) {
      var x = px + (j / (points.length - 1)) * (w - 2 * px);
      var y = h - py - ((points[j] - mn) / rng) * (h - 2 * py);
      linePts.push(x.toFixed(1) + ',' + y.toFixed(1));
    }
    var line = linePts.join(' ');
    var first = linePts[0].split(','), last = linePts[points.length - 1].split(',');
    var dFill = 'M ' + linePts[0];
    for (j = 1; j < linePts.length; j++) { dFill += ' L ' + linePts[j]; }
    dFill += ' L ' + last[0] + ',' + (h - py) + ' L ' + first[0] + ',' + (h - py) + ' Z';
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">' +
      '<defs><linearGradient id="sparkGradModal" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="#2563eb" stop-opacity="0.4"/>' +
      '<stop offset="100%" stop-color="#2563eb" stop-opacity="0"/></linearGradient></defs>' +
      '<path class="spark-fill" d="' + dFill + '" fill="url(#sparkGradModal)"/>' +
      '<polyline class="spark-line" points="' + line + '"/></svg>';
  }
  function setKPIChips(idPrefix, kpis) {
    var keys = ['cac', 'roas', 'spend', 'conv'];
    var accentCls = ['kpi-chip--accent-red', 'kpi-chip--accent-yellow', 'kpi-chip--accent-green', 'kpi-chip--accent-grey'];
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i], k = kpis[key], base = idPrefix + key;
      var valEl = document.getElementById(base + '-val');
      if (!valEl) { continue; }
      valEl.textContent = k.val;
      document.getElementById(base + '-delta').textContent = k.delta;
      applyKpiTrend(document.getElementById(base + '-trend'), k);
      var chip = valEl.closest('.kpi-chip');
      if (chip) {
        for (var ac = 0; ac < accentCls.length; ac++) { chip.classList.remove(accentCls[ac]); }
        chip.classList.add('kpi-chip--accent-' + k.dot);
      }
    }
  }

  /* Engine A fill -- all HTML built from static PLATFORM_DATA, all strings escaped */
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }

  function signalActionHTML(s) {
    if (s.assignee && s.followUp) {
      var displayName = esc(s.ownerName || s.assignee);
      var roleLine    = s.ownerName ? esc(s.assignee) : '';
      var ownerRow = '<div class="signal-owner-block">' +
        '<img class="signal-owner-avatar" src="https://api.dicebear.com/9.x/notionists/svg?seed=' + encodeURIComponent(s.ownerName || s.assignee || 'Duct') + '" width="40" height="40" alt="" loading="lazy" decoding="async"/>' +
        '<div class="signal-owner-text"><span class="signal-owner-name">' + displayName + '</span>';
      if (roleLine) { ownerRow += '<span class="signal-owner-role">' + roleLine + '</span>'; }
      ownerRow += '</div></div>';
      return '<div class="signal-action"><div class="signal-action-row">' +
        '<div class="signal-action-cell"><span class="signal-action-label">Who owns it</span>' + ownerRow + '</div>' +
        '<div class="signal-action-cell"><span class="signal-action-label">Follow-up</span>' +
        '<span class="signal-action-value">' + esc(s.followUp) + '</span></div></div></div>';
    }
    if (s.owner) { return '<div class="signal-action"><p class="signal-owner-legacy">' + esc(s.owner) + '</p></div>'; }
    return '';
  }
  function signalBlockHTML(s) {
    return '<div class="signal-block signal-level-' + esc(s.level) + '">' +
      '<span class="signal-pill ' + esc(s.level) + '">' + esc(s.pill) + '</span>' +
      '<p class="signal-title">' + esc(s.title) + '</p>' +
      '<p class="signal-body">' + esc(s.body) + '</p>' +
      signalActionHTML(s) + '</div>';
  }
  function buildSignalsHTML(signals) {
    var html = '', i;
    for (i = 0; i < signals.length && i < 2; i++) { html += signalBlockHTML(signals[i]); }
    if (signals.length > 2) {
      html += '<div id="modal-signal-extra" class="rpt-signal-extra-wrap" hidden>' + signalBlockHTML(signals[2]) + '</div>';
      html += '<button type="button" class="rpt-show-more-signals" id="modal-signal-more">Show 1 more signal</button>';
    }
    return html;
  }
  function buildRoasBarsHTML(campaigns) {
    var nums = [], i;
    for (i = 0; i < campaigns.length; i++) { nums.push(parseFloat(String(campaigns[i].roas).replace(/x/gi, '').trim()) || 0); }
    var maxR = Math.max.apply(null, nums) || 1;
    var html = '';
    for (i = 0; i < campaigns.length; i++) {
      var pct = Math.round((nums[i] / maxR) * 100);
      html += '<div class="rpt-bar-row">' +
        '<div class="rpt-bar-top"><span class="rpt-bar-name">' + esc(campaigns[i].name) + '</span>' +
        '<span class="rpt-bar-val">' + esc(campaigns[i].roas) + '</span></div>' +
        '<div class="rpt-bar-track"><div class="rpt-bar-fill" style="width:' + pct + '%"></div></div></div>';
    }
    return html;
  }
  function buildCampRowsHTML(campaigns) {
    var html = '';
    for (var i = 0; i < campaigns.length; i++) {
      var c = campaigns[i];
      html += '<tr class="camp-row' + (i % 2 === 1 ? ' camp-row--alt' : '') + '">' +
        '<td>' + esc(c.name) + '</td><td>' + esc(c.spend) + '</td>' +
        '<td>' + esc(c.cpa) + '</td><td>' + esc(c.roas) + '</td>' +
        '<td class="' + esc(c.cls) + '">' + esc(c.status) + '</td></tr>';
    }
    return html;
  }

  function fillPaidAds(S) {
    var metricKey  = S.metric || 'cac';
    var campaigns  = aggregateCampaigns(metricKey, S.platforms);
    var signals    = aggregateSignals(metricKey, S.platforms);
    var sparkline  = aggregateSparkline(metricKey, S.platforms);
    var aggKPIs    = aggregateKPIs(metricKey, S.platforms);
    var verdict    = deriveVerdict(signals);
    var unitEcon   = deriveUnitEcon(metricKey, S.platforms);
    var platList   = S.platforms.join(' \u00B7 ');
    var metricLabel = { cac: 'lower CAC', roas: 'higher ROAS', pipeline: 'more pipeline' }[metricKey];
    var dateRange  = formatReportDate();
    var today = (function () {
      var now = new Date(), months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      return months[now.getMonth()] + ' ' + now.getDate() + ', ' + now.getFullYear();
    })();
    var sourceMap  = { 'Google Ads': 'Google Ads API', 'Meta': 'Meta Ads Manager', 'Twitter / X': 'X Ads API', 'LinkedIn Ads': 'LinkedIn Campaign Manager' };
    var sourceParts = [];
    for (var si = 0; si < S.platforms.length; si++) { sourceParts.push(sourceMap[S.platforms[si]] || S.platforms[si]); }
    var meta    = dateRange + ' \u00B7 ' + platList;
    var sources = 'Data: ' + sourceParts.join(' \u00B7 ') + ' \u00B7 as of ' + today + ' \u00B7 Optimised for ' + metricLabel;

    document.getElementById('wt-brief-sub').textContent = 'Optimised for ' + metricLabel + ' \u00B7 ' + platList;

    var kpiHintEl = document.getElementById('rpt-kpi-hint');
    if (kpiHintEl) {
      kpiHintEl.textContent = metricKey === 'pipeline'
        ? 'Cross-platform snapshot plus CRM funnel (example data). WoW = this 7-day window vs the prior week; MoM = calendar month.'
        : 'Cross-platform snapshot from your connected accounts. WoW = this 7-day window vs the prior week; MoM = calendar month.';
    }
    document.getElementById('rpt-meta').textContent = meta;
    var v = document.getElementById('rpt-verdict');
    v.className  = 'rpt-verdict rpt-verdict--modal ' + verdict.verdictClass;
    v.textContent = verdict.verdictText;

    var heroKpiKey = { cac: 'cac', roas: 'roas', pipeline: 'conv' }[metricKey];
    var heroKpi    = aggKPIs.kpis[heroKpiKey];
    var heroLabels = { cac: 'CAC', roas: 'ROAS', spend: 'Spend', conv: 'Conversions' };
    document.getElementById('rpt-hero-label').textContent = heroLabels[heroKpiKey];
    document.getElementById('rpt-hero-val').textContent   = heroKpi.val;
    var heroDelta = document.getElementById('rpt-hero-delta-row');
    heroDelta.innerHTML = ''; /* cleared then repopulated with DOM nodes */
    var heroTrend = document.createElement('span'); applyKpiTrend(heroTrend, heroKpi); heroDelta.appendChild(heroTrend);
    var heroDeltaText = document.createElement('span'); heroDeltaText.textContent = heroKpi.delta; heroDelta.appendChild(heroDeltaText);

    document.getElementById('rpt-sparkline').innerHTML = buildSparkSVGPaidAds(sparkline); /* static SVG */
    document.getElementById('rpt-roas-bars').innerHTML = buildRoasBarsHTML(campaigns);    /* esc() on all values */

    setKPIChips('rpt-kpi-', aggKPIs.kpis);
    var chips = document.querySelectorAll('#duct-report-root .kpi-chip[data-kpi-key]');
    for (var ci = 0; ci < chips.length; ci++) {
      chips[ci].classList.remove('kpi-chip--modal-hidden');
      if (chips[ci].getAttribute('data-kpi-key') === heroKpiKey) { chips[ci].classList.add('kpi-chip--modal-hidden'); }
    }

    document.getElementById('rpt-signals').innerHTML   = buildSignalsHTML(signals);    /* esc() on all values */
    var smb = document.getElementById('modal-signal-more'), sme = document.getElementById('modal-signal-extra');
    if (smb && sme) {
      sme.setAttribute('hidden', ''); smb.textContent = 'Show 1 more signal';
      smb.onclick = function () {
        if (sme.hasAttribute('hidden')) { sme.removeAttribute('hidden'); smb.textContent = 'Show less'; }
        else { sme.setAttribute('hidden', ''); smb.textContent = 'Show 1 more signal'; }
      };
    }
    document.getElementById('rpt-camp-tbody').innerHTML  = buildCampRowsHTML(campaigns); /* esc() on all values */
    document.getElementById('rpt-camp-meta').textContent = ' \u00B7 ' + campaigns.length + ' campaigns';
    document.getElementById('rpt-ue-cps').textContent     = unitEcon.cps;
    document.getElementById('rpt-ue-ltv').textContent     = unitEcon.ltv;
    document.getElementById('rpt-ue-verdict').textContent = unitEcon.verdict;
    document.getElementById('rpt-ue-summary').textContent = unitEcon.summary || '';
    document.getElementById('rpt-footer-sources').textContent = sources;

    var cp = document.getElementById('rpt-camp-panel'), ct = document.getElementById('rpt-camp-toggle');
    var up = document.getElementById('rpt-ue-panel'),   ut = document.getElementById('rpt-ue-toggle');
    if (cp) { cp.setAttribute('hidden', ''); } if (ct) { ct.setAttribute('aria-expanded', 'false'); }
    if (up) { up.setAttribute('hidden', ''); } if (ut) { ut.setAttribute('aria-expanded', 'false'); }
  }

  window.DUCT_DEMO_CONFIG = {
    cfg: { min: 1 },
    minHint: 2,
    fill: fillPaidAds
  };
})();
