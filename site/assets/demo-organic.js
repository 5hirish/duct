/* demo-organic.js — Organic Growth variant config for demo.js */
(function () {
  var CFG = {
    min: 2,
    sparkColor: '#16a34a',
    src: {
      GSC:     'Google Search Console',
      Clarity: 'Microsoft Clarity',
      GA4:     'GA4',
      Mixpanel: 'Mixpanel Events API'
    },
    defs: {
      rankings: { hero: 'Avg Position',              fmt: 'n1', label: 'ranking growth',         bar: 'Traffic by keyword cluster',   ths: ['Cluster','Position','Sessions','Action','Priority'],  hide: 'position' },
      signups:  { hero: 'Trial Signups from Organic', fmt: 'int', label: 'organic signups',        bar: 'Trials by content cluster',    ths: ['Cluster','Trials','Sessions','CVR','Action'],         hide: 'signups'  },
      clusters: { hero: 'Cluster Coverage %',         fmt: 'p0', label: 'topic cluster ownership', bar: 'Coverage by topic cluster',    ths: ['Cluster','Coverage','Keywords','Gap','Action'],       hide: 'keywords' }
    },
    cross: {
      rankings: ['yellow', 'Cross-tool', 'Six pages in positions 4\u20138 have zero internal links from authority pages.', 'You are one link away from page one on multiple high-intent terms.', 'Maya Reed', 'SEO Lead', 'Add internal links from authority pages'],
      signups:  ['yellow', 'Cross-tool', 'Your top-traffic cluster drives most sessions but only a sliver of trials.', 'The intent on those posts does not match the CTA path.', 'Owen Park', 'Growth', 'Rewrite CTAs on tutorial-heavy pages'],
      clusters: ['red',    'Cross-tool', 'A competitor owns four topic clusters you still have zero coverage on.', 'All four have manageable difficulty and meaningful search volume.', 'Ivy Stone', 'Content', 'Commission briefs for the missing clusters this sprint']
    },
    kpiKeys:          ['sessions', 'signups', 'position', 'keywords'],
    kpiDefs:          { sessions: { fmt: 'k', sum: true }, signups: { fmt: 'int', sum: true }, position: { fmt: 'n1' }, keywords: { fmt: 'int', sum: true } },
    defaultMetric:    'rankings',
    defaultPlatforms: ['GSC', 'GA4']
  };

  function mk(hero, k, rows, sig, sp, u) {
    return { hero: hero, k: k, r: rows, s: [sig], sp: sp, u: u };
  }

  var D = {
    GSC: {
      rankings: mk(
        [11.8, 'Up from 13.1 last month', 'up', 'green'],
        { sessions: [18400,'9% WoW','up','green'], signups: [42,'3% WoW','up','grey'], position: [11.8,'Ranking gains on priority terms','up','green'], keywords: [186,'14 net new','up','green'] },
        [['AI reporting tools',11.8,'11.8','5.8K','Refresh comparison page','High'],['Product analytics alternatives',8.4,'8.4','4.1K','Add internal links','High']],
        ['yellow','Watch','Priority terms are climbing, but several pages still stall just outside the top 10.','They need stronger internal linking and fresher examples to break through.','Maya Reed','SEO Lead','Refresh examples and add links'],
        [0.38,0.42,0.47,0.51,0.55,0.60,0.64],
        ['$148','3.2x','Healthy',' · 3.2x ROI · scalable']
      ),
      signups: mk(
        [42, 'Blog-to-trial CVR improving', 'up', 'green'],
        { sessions: [19200,'8% WoW','up','green'], signups: [42,'Blog-to-trial CVR improving','up','green'], position: [12.1,'Pages climbing','up','green'], keywords: [181,'11 net new','up','green'] },
        [['Comparison pages',16,'16','2.4%','Expand buying-intent posts','High'],['Template guides',11,'11','1.6%','Tighten CTA path','Medium']],
        ['green','Win','Comparison pages now convert better than every other content cluster.','They are your clearest bridge between search intent and trial intent.','Ava Lin','Growth','Double down on BOFU comparison content'],
        [0.31,0.35,0.39,0.42,0.48,0.53,0.58],
        ['$132','3.6x','Healthy',' · 3.6x ROI · compounding']
      ),
      clusters: mk(
        [62, 'Coverage improving in core categories', 'up', 'green'],
        { sessions: [17600,'7% WoW','up','green'], signups: [34,'2% WoW','up','grey'], position: [13.2,'Steady gains','up','green'], keywords: [186,'14 net new','up','green'] },
        [['Product analytics',62,'62%','48','Build cluster hub','High'],['Product ops',41,'41%','29','Backfill missing TOFU posts','High']],
        ['yellow','Watch','Coverage is strong in core analytics topics but thin in product-ops adjacencies.','That leaves authority gains on the table.','Ivy Stone','Content','Backfill adjacent cluster pages'],
        [0.29,0.33,0.38,0.43,0.49,0.54,0.59],
        ['$166','2.9x','Healthy',' · 2.9x ROI · expanding']
      )
    },
    Clarity: {
      rankings: mk(
        [13.4, 'Keyword difficulty mix improved', 'up', 'green'],
        { sessions: [9600,'5% WoW','up','grey'], signups: [21,'Flat','flat','grey'], position: [13.4,'Keyword mix improved','up','green'], keywords: [132,'8 net new','up','green'] },
        [['Low-KD opportunities',13.4,'13.4','3.2K','Ship quick-win updates','High'],['Competitor gaps',17.1,'17.1','2.6K','Create challenger pages','Medium']],
        ['yellow','Watch','A cluster of low-KD terms is sitting within striking distance of page one.','Refreshes should move it quickly.','Owen Park','Growth','Refresh titles and sections on quick-win pages'],
        [0.34,0.36,0.40,0.44,0.47,0.51,0.55],
        ['$154','3.0x','Healthy',' · 3.0x ROI · efficient']
      ),
      signups: mk(
        [18, 'Assisted signups stable', 'flat', 'grey'],
        { sessions: [9100,'4% WoW','up','grey'], signups: [18,'Assisted signups stable','flat','grey'], position: [14.0,'Softer than GSC','down','yellow'], keywords: [126,'6 net new','up','green'] },
        [['BOFU keyword gaps',9,'9','1.9%','Create commercial landing pages','High'],['Tutorial library',6,'6','0.8%','Retool CTA modules','Medium']],
        ['yellow','Watch','Tutorial traffic still outpaces its conversion contribution.','The cluster attracts broad intent that needs a better CTA handoff.','Rhea Cole','Content','Retool CTA modules on tutorial pages'],
        [0.27,0.29,0.32,0.35,0.37,0.40,0.42],
        ['$171','2.5x','Breakeven',' · 2.5x ROI · acceptable']
      ),
      clusters: mk(
        [54, 'Competitor gaps mapped', 'up', 'green'],
        { sessions: [8800,'4% WoW','up','grey'], signups: [17,'Flat','flat','grey'], position: [14.8,'Gradual climb','up','grey'], keywords: [132,'8 net new','up','green'] },
        [['Experimental reporting',54,'54%','22','Publish cornerstone guide','High'],['Product dashboards',38,'38%','18','Fill MOFU gap','Medium']],
        ['red','Critical','Competitor-owned gaps remain concentrated in high-value clusters.','Without new cornerstone pages, authority growth will stall.','Ivy Stone','Content','Commission cornerstone pages for the top gap clusters'],
        [0.24,0.28,0.31,0.35,0.39,0.43,0.46],
        ['$182','2.3x','Breakeven',' · 2.3x ROI · exposed']
      )
    },
    GA4: {
      rankings: mk(
        [12.6, 'Traffic quality holding', 'up', 'grey'],
        { sessions: [14300,'6% WoW','up','green'], signups: [29,'4% WoW','up','green'], position: [12.6,'Traffic quality holding','up','grey'], keywords: [118,'5 net new','up','grey'] },
        [['Solution pages',12.6,'12.6','4.9K','Add comparison CTAs','High'],['Webinar recap posts',19.3,'19.3','1.8K','Trim low-intent sections','Low']],
        ['green','Win','Solution pages are holding traffic quality while rankings improve.','They are the safest place to invest new SEO effort.','Ava Lin','Growth','Expand the best-performing solution page patterns'],
        [0.33,0.37,0.41,0.46,0.50,0.54,0.57],
        ['$141','3.4x','Healthy',' · 3.4x ROI · strong']
      ),
      signups: mk(
        [29, 'Organic signups are trending up', 'up', 'green'],
        { sessions: [14900,'6% WoW','up','green'], signups: [29,'Organic signups are trending up','up','green'], position: [12.9,'Steady','up','grey'], keywords: [119,'5 net new','up','grey'] },
        [['Solution pages',29,'29','2.3%','Scale commercial pages','High'],['Template posts',11,'11','0.9%','Rewrite CTA modules','Medium']],
        ['green','Win','Solution pages convert at more than double the sitewide blog average.','This is the clearest path from SEO to revenue.','Maya Reed','SEO Lead','Scale solution-page production'],
        [0.30,0.33,0.37,0.41,0.46,0.49,0.53],
        ['$127','3.8x','Healthy',' · 3.8x ROI · strong']
      ),
      clusters: mk(
        [48, 'Coverage light outside the core funnel', 'down', 'yellow'],
        { sessions: [13800,'5% WoW','up','green'], signups: [22,'2% WoW','up','grey'], position: [13.3,'Steady','up','grey'], keywords: [119,'5 net new','up','grey'] },
        [['Bottom-funnel cluster',48,'48%','17','Expand supporting pages','High'],['How-to cluster',66,'66%','33','Keep, but de-prioritise','Low']],
        ['yellow','Watch','How-to content drives volume, but bottom-funnel coverage is still too thin.','The cluster mix is unbalanced for a signup goal.','Owen Park','Growth','Expand supporting BOFU pages'],
        [0.25,0.28,0.31,0.35,0.39,0.41,0.44],
        ['$159','2.7x','Healthy',' · 2.7x ROI · room to improve']
      )
    },
    Mixpanel: {
      rankings: mk(
        [14.2, 'Competitor pressure still visible', 'down', 'yellow'],
        { sessions: [7900,'3% WoW','up','grey'], signups: [15,'Flat','flat','grey'], position: [14.2,'Competitor pressure still visible','down','yellow'], keywords: [104,'4 net new','up','grey'] },
        [['Competitor overlap pages',14.2,'14.2','2.2K','Sharpen page angle','High'],['Cluster support posts',18.8,'18.8','1.4K','Update stale examples','Medium']],
        ['yellow','Watch','Competitor overlap pages are rising, but not fast enough to outrun rival updates.','Your page angle is still too generic on several target terms.','Rhea Cole','Content','Sharpen differentiation on overlap pages'],
        [0.26,0.29,0.33,0.36,0.39,0.42,0.45],
        ['$173','2.6x','Breakeven',' · 2.6x ROI · needs focus']
      ),
      signups: mk(
        [15, 'Commercial intent under-monetised', 'down', 'yellow'],
        { sessions: [7600,'3% WoW','up','grey'], signups: [15,'Commercial intent under-monetised','down','yellow'], position: [14.9,'Stuck mid-page','flat','grey'], keywords: [103,'4 net new','up','grey'] },
        [['Alternative pages',15,'15','1.7%','Add stronger proof sections','High'],['List posts',5,'5','0.6%','Reduce low-intent CTAs','Low']],
        ['yellow','Watch','Alternative pages attract the right intent but still under-convert.','They need sharper proof and clearer CTA placement.','Ava Lin','Growth','Add social proof and comparison modules'],
        [0.22,0.24,0.27,0.30,0.32,0.35,0.37],
        ['$184','2.2x','Breakeven',' · 2.2x ROI · fragile']
      ),
      clusters: mk(
        [43, 'Coverage gaps remain open', 'down', 'yellow'],
        { sessions: [7200,'2% WoW','up','grey'], signups: [13,'Flat','flat','grey'], position: [15.4,'Below target','down','yellow'], keywords: [104,'4 net new','up','grey'] },
        [['Competitor-owned gaps',43,'43%','19','Publish challenger pages','High'],['Supporting glossary',57,'57%','24','Keep cadence steady','Low']],
        ['red','Critical','Coverage gaps remain open in clusters competitors already dominate.','Without challenger pages, authority accumulation will lag.','Ivy Stone','Content','Publish challenger pages for the top overlap clusters'],
        [0.20,0.23,0.25,0.28,0.31,0.34,0.36],
        ['$191','2.1x','Breakeven',' · 2.1x ROI · exposed']
      )
    }
  };

  window.DUCT_DEMO_CONFIG = { cfg: CFG, data: D };
}());
