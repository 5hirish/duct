/* demo-product.js — Product Intelligence variant config for demo.js */
(function () {
  var CFG = {
    min: 2,
    src: {
      Mixpanel:  'Mixpanel Events API',
      Intercom:  'Intercom Conversations API',
      Linear:    'Linear Issues API',
      FullStory: 'FullStory Session Replay API'
    },
    defs: {
      retention: { hero: 'D30 Retention',           fmt: 'p1', label: 'retention health',            bar: 'Retention by cohort',       ths: ['Segment','Active Users','Adoption','Trend','Action'],        hide: 'retention' },
      adoption:  { hero: 'Feature Activation Rate', fmt: 'p0', label: 'feature adoption',             bar: 'Adoption by feature',       ths: ['Feature','DAU','Adoption','Trend','Action'],                 hide: 'adoption'  },
      tickets:   { hero: 'Ticket Deflection Rate',  fmt: 'p0', label: 'support-to-product signals',   bar: 'Ticket volume by issue type', ths: ['Issue','Open Tickets','Affected Users','Trend','Action'],  hide: 'tickets'   }
    },
    cross: {
      retention: { level: 'yellow', pill: 'Cross-tool', title: 'Linear ticket velocity and Intercom escalations spiked before retention dropped.', body: 'Duct stitched the release window, support spike, and cohort decay into one narrative.', ownerName: 'Morgan Lee', assignee: 'Product + Eng', followUp: 'Compare the release window against churned cohorts' },
      adoption:  { level: 'yellow', pill: 'Cross-tool', title: 'Only 12% of activated users reach the aha moment.',                               body: 'Intercom churn notes and Mixpanel events point to setup-depth failure, not awareness.',                              ownerName: 'Avery Shah',  assignee: 'Growth PM',       followUp: 'Shorten the path from first use to third key event' },
      tickets:   { level: 'red',    pill: 'Cross-tool', title: 'Ticket volume spikes 48 hours after each cohort refresh.',                         body: 'The refresh is creating confusion instead of confidence.',                                                            ownerName: 'Jordan Cruz', assignee: 'Support + Product', followUp: 'Rewrite the refresh UX and add guidance before the next rollout' }
    },
    kpiKeys:        ['retention', 'dau', 'adoption', 'tickets'],
    kpiDefs:        { retention: { fmt: 'p1' }, dau: { fmt: 'k', sum: true }, adoption: { fmt: 'p0' }, tickets: { fmt: 'int', sum: true } },
    defaultMetric:  'retention',
    defaultPlatforms: ['Mixpanel', 'Intercom']
  };

  var D = {
    Mixpanel: {
      retention: {
        hero: [31.4, 'Down 4.2 pts vs goal', 'down', 'red'],
        k: { retention: [31.4,'Down 4.2 pts vs goal','down','red'], dau: [12600,'6% WoW','down','yellow'], adoption: [41,'8 pts below target','down','yellow'], tickets: [58,'18% WoW','up','yellow'] },
        r: [['New workspace owners',31.4,'31.4%','7.1K','42%','Down 6%','Fix onboarding handoff'],['Power users',58.7,'58.7%','1.6K','78%','Up 3%','Protect with SLA outreach']],
        s: [['red','Critical','New workspace retention is decaying faster after the April release.','The drop starts after the first collaboration event, which points to setup friction.','Jamie Patel','Product','Audit the first-team invite flow']],
        sp: [0.74,0.71,0.68,0.64,0.58,0.54,0.49],
        u: ['21%','1.8x','Needs work',' · 1.8x health score · fragile']
      },
      adoption: {
        hero: [41, '8 pts below target', 'down', 'yellow'],
        k: { retention: [33.8,'3.4 pts vs goal','down','yellow'], dau: [13200,'4% WoW','up','green'], adoption: [41,'8 pts below target','down','yellow'], tickets: [64,'12% WoW','up','yellow'] },
        r: [['Checklist builder',41,'41%','8.6K','41%','Down 5%','Shorten setup checklist'],['Auto-routing rules',57,'57%','5.4K','57%','Up 2%','Promote during week 1']],
        s: [['red','Critical','Checklist builder activation stalls after the first save.','Users start setup but do not complete the second key step.','Lena Ortiz','PM','Simplify step two of builder setup']],
        sp: [0.36,0.41,0.46,0.49,0.52,0.48,0.45],
        u: ['24%','2.1x','Healthy',' · 2.1x health score · promising']
      },
      tickets: {
        hero: [34, 'Below 40% target', 'down', 'yellow'],
        k: { retention: [30.2,'5.1 pts vs goal','down','red'], dau: [11800,'5% WoW','down','yellow'], adoption: [38,'11 pts below target','down','red'], tickets: [86,'21% WoW','up','red'] },
        r: [['Permissions confusion',86,'86','86','3.2K','Up 21%','Clarify role settings'],['Workspace refresh',54,'54','54','2.1K','Up 14%','Add release notes inline']],
        s: [['red','Critical','Permissions confusion now drives the largest support queue.','The spike is concentrated in multi-seat accounts, so expansion is now at risk.','Samir Gupta','Support','Ship role-permission copy updates']],
        sp: [0.32,0.38,0.41,0.47,0.55,0.61,0.68],
        u: ['19%','1.6x','Breakeven',' · 1.6x health score · watch closely']
      }
    },
    Intercom: {
      retention: {
        hero: [29.8, 'Support-led churn risk up', 'down', 'red'],
        k: { retention: [29.8,'Support-led churn risk up','down','red'], dau: [9800,'3% WoW','down','yellow'], adoption: [36,'10 pts below target','down','red'], tickets: [74,'16% WoW','up','red'] },
        r: [['Onboarding help requests',28.9,'28.9%','2.9K','34%','Down 8%','Rewrite setup guidance'],['Billing-related accounts',35.4,'35.4%','1.8K','39%','Flat','Escalate pricing objections']],
        s: [['red','Critical','Accounts opening 2+ onboarding chats churn at nearly double the baseline.','Threads point to teammate setup and ownership transfer confusion.','Rory Hall','Success','Create an onboarding rescue sequence']],
        sp: [0.69,0.67,0.63,0.59,0.56,0.52,0.50],
        u: ['20%','1.7x','Needs work',' · 1.7x health score · support-heavy']
      },
      adoption: {
        hero: [34, 'Support friction is suppressing setup', 'down', 'red'],
        k: { retention: [31.1,'4.9 pts vs goal','down','yellow'], dau: [10100,'2% WoW','up','grey'], adoption: [34,'Support friction is suppressing setup','down','red'], tickets: [79,'18% WoW','up','red'] },
        r: [['Guided setup bot',34,'34%','4.7K','34%','Down 7%','Reduce handoff confusion'],['Template gallery',48,'48%','3.3K','48%','Up 1%','Push as first-week nudge']],
        s: [['red','Critical','The guided setup bot creates more follow-up tickets than successful activations.','It behaves like a deflection layer, not an activation assist.','Ella Morris','Support PM','Cut steps from the setup bot']],
        sp: [0.28,0.31,0.34,0.39,0.45,0.42,0.40],
        u: ['22%','1.9x','Breakeven',' · 1.9x health score · recoverable']
      },
      tickets: {
        hero: [31, 'Deflection lagging target', 'down', 'red'],
        k: { retention: [28.7,'Churn risk elevated','down','red'], dau: [9400,'4% WoW','down','yellow'], adoption: [33,'12 pts below target','down','red'], tickets: [97,'24% WoW','up','red'] },
        r: [['Activation blockers',97,'97','97','3.6K','Up 24%','Patch onboarding docs'],['Refresh questions',61,'61','61','2.4K','Up 15%','Add contextual education']],
        s: [['red','Critical','Activation blockers now dominate ticket volume and expansion risk.','Most are not bugs; users are failing to understand setup requirements quickly enough.','Kira Benson','Support','Add proactive setup messaging']],
        sp: [0.34,0.40,0.44,0.49,0.55,0.63,0.71],
        u: ['18%','1.5x','Breakeven',' · 1.5x health score · brittle']
      }
    },
    Linear: {
      retention: {
        hero: [33.9, 'Release quality is stabilising', 'up', 'green'],
        k: { retention: [33.9,'Release quality is stabilising','up','green'], dau: [8700,'2% WoW','up','grey'], adoption: [44,'5 pts below target','down','yellow'], tickets: [41,'9% WoW','up','yellow'] },
        r: [['Release 4.2 impacted accounts',27.1,'27.1%','1.9K','31%','Down 9%','Hotfix the role bug'],['Post-hotfix cohorts',39.8,'39.8%','2.6K','47%','Up 4%','Expand rollout']],
        s: [['yellow','Watch','One release window explains most of the retention dip.','The Linear issue history shows the problem was contained and fixable.','Parker Long','Engineering','Backport the permissions fix']],
        sp: [0.58,0.56,0.53,0.49,0.50,0.55,0.61],
        u: ['25%','2.0x','Healthy',' · 2.0x health score · improving']
      },
      adoption: {
        hero: [46, 'Activation improving after fix', 'up', 'green'],
        k: { retention: [34.5,'3.8 pts vs goal','down','yellow'], dau: [9100,'3% WoW','up','green'], adoption: [46,'Activation improving after fix','up','green'], tickets: [37,'7% WoW','down','green'] },
        r: [['Collaborative templates',46,'46%','3.7K','46%','Up 5%','Roll into onboarding'],['Task routing',52,'52%','2.8K','52%','Up 3%','Promote in upgrades']],
        s: [['green','Win','Task routing rebounded quickly once the setup bug closed.','Demand was real; the leak was execution quality, not positioning.','Sasha Cole','PM','Feature task routing earlier']],
        sp: [0.33,0.36,0.39,0.43,0.48,0.53,0.57],
        u: ['26%','2.2x','Healthy',' · 2.2x health score · strong']
      },
      tickets: {
        hero: [43, 'Back near deflection target', 'up', 'green'],
        k: { retention: [32.2,'4.1 pts vs goal','down','yellow'], dau: [8800,'2% WoW','up','grey'], adoption: [41,'7 pts below target','down','yellow'], tickets: [52,'11% WoW','down','green'] },
        r: [['Role-permission regressions',52,'52','52','1.9K','Down 12%','Finish patch rollout'],['Template sync delays',26,'26','26','1.1K','Flat','Improve sync notice']],
        s: [['green','Win','Role-permission tickets are dropping after the patch landed.','Support noise was tied to a specific engineering issue, not a broad UX collapse.','Chris Vega','Engineering','Complete the rollout']],
        sp: [0.51,0.47,0.43,0.39,0.36,0.33,0.31],
        u: ['23%','2.0x','Healthy',' · 2.0x health score · steady']
      }
    },
    FullStory: {
      retention: {
        hero: [28.9, 'Replay friction rising in setup', 'down', 'red'],
        k: { retention: [28.9,'Replay friction rising in setup','down','red'], dau: [7200,'2% WoW','down','grey'], adoption: [37,'10 pts below target','down','red'], tickets: [46,'11% WoW','up','yellow'] },
        r: [['Invite flow stalls',28.9,'28.9%','1.8K','37%','Down 8%','Shorten teammate invite path'],['Recovered cohorts',36.8,'36.8%','1.2K','49%','Up 4%','Roll out simplified invite flow']],
        s: [['red','Critical','Session replay shows most retention loss starts inside teammate invite and role setup.','Users hesitate, backtrack, and abandon before reaching first-team activation.','Nina Park','Product Ops','Replay the top 20 failed invite sessions']],
        sp: [0.66,0.63,0.59,0.54,0.50,0.46,0.42],
        u: ['20%','1.7x','Needs work',' · 1.7x health score · replay-backed']
      },
      adoption: {
        hero: [35, 'Users discover value too late', 'down', 'red'],
        k: { retention: [30.6,'5.0 pts vs goal','down','yellow'], dau: [7600,'2% WoW','up','grey'], adoption: [35,'Users discover value too late','down','red'], tickets: [43,'9% WoW','up','yellow'] },
        r: [['Checklist builder replays',35,'35%','3.1K','35%','Down 6%','Reduce blank-state friction'],['Template-first path',49,'49%','2.2K','49%','Up 3%','Promote template-first onboarding']],
        s: [['red','Critical','Replay clusters show users opening the feature but failing to reach the second success moment.','The product explains capability too late, after confusion has already started.','Mia Chen','Growth PM','Move the aha moment earlier in onboarding']],
        sp: [0.34,0.37,0.39,0.43,0.47,0.44,0.41],
        u: ['21%','1.8x','Breakeven',' · 1.8x health score · fixable']
      },
      tickets: {
        hero: [33, 'Replay confirms support root cause', 'down', 'yellow'],
        k: { retention: [29.7,'5.6 pts vs goal','down','red'], dau: [7000,'3% WoW','down','yellow'], adoption: [36,'11 pts below target','down','red'], tickets: [62,'17% WoW','up','red'] },
        r: [['Role-permission confusion',62,'62','62','2.2K','Up 17%','Add inline invite guidance'],['Empty-state dead ends',38,'38','38','1.5K','Up 10%','Instrument the dead-end path']],
        s: [['yellow','Watch','Replay confirms that the highest-volume tickets begin in the same two dead-end screens.','Support is seeing the symptom; FullStory shows the exact moment users lose confidence.','Omar Lewis','Support PM','Pair ticket tags with replay segments weekly']],
        sp: [0.39,0.44,0.48,0.54,0.60,0.66,0.70],
        u: ['19%','1.6x','Breakeven',' · 1.6x health score · evidence-rich']
      }
    }
  };

  window.DUCT_DEMO_CONFIG = { cfg: CFG, data: D };
}());
