# Ranking the professions: meaning, unpleasantness and the barriers to entry

The haggling round (`policy.wage_reset`, docs/REVIEW.md §6) sets each profession's pay at what it takes for
enough people to do it once the payment lets them refuse. What it takes depends on three things the model holds
per profession in `PROFESSION_TRAITS` (src/ubisim/abm/params.py). All three are currently judgements:

* **disamenity:** how unpleasant the work is;
* **meaning:** how useful or interesting the people doing it find it;
* **minimum education:** 0, 1 or 2.

This note sets out how to replace those judgements with evidence. It also says what else belongs in the ranking.

## What the evidence says about the mechanism

* **People value working conditions, and value them a lot.** Maestas et al. (2023, *AER*) ran stated-preference
  experiments, validated against real job choices. Working conditions vary widely and make up a large part of
  what a job pays. Counting them widens measured inequality, because the best-paid jobs also tend to have the best
  conditions.
* **Some conditions carry large sums.** Mas and Pallais (2017, *AER*) found that the average applicant would give up
  about 20% of pay to avoid a schedule the employer sets at a week's notice, mostly to avoid evening and weekend
  work, and about 8% to work from home.
* **Today, those preferences barely show up in pay.** Bonhomme and Jolivet (2009, *J. Applied Econometrics*)
  estimated strong preferences for job security and the type of work in eight European countries, yet found almost
  no compensating wage differentials. The reason is frictions: people cannot afford to refuse work and search on.
  Lavetti (2023, *JEP*) reviews why the cross-section so often shows the wrong sign.

That third finding is the reform's argument in the literature's own terms. Unpleasant work does not command a
premium today because people cannot easily turn it down. A payment that lets them turn it down lowers that
friction, and the premium should start to appear. How large it becomes is what the round must estimate, which is
why the traits matter.

## Ingredients of the ranking

| Dimension | Why it matters in the round | Measure |
|---|---|---|
| Meaning | People accept less pay for work they find useful or interesting | Agreement with "my job is useful to society", "I can help other people", "my job is interesting" |
| Physical strain and danger | Raises the pay needed | "How often do you do hard physical work"; unhealthy or dangerous conditions |
| Stress and workload | Raises the pay needed; in the model it also grows with shortages (`workload_disamenity`) | "How often do you find your work stressful" |
| Unsocial hours | Mas and Pallais: about 20% of pay | Share working evenings, nights and weekends |
| Autonomy | Valued, and comes with managerial and professional work | "I can work independently" |
| Status and wanting to run things | Can lower pay where many want the role, as with managers | Preference for self-employment; desire to lead |
| Qualification barrier | Caps how fast supply can answer pay, so scarcity rents last for years | Years of training, licensing, entry quotas |

The last row is the main remaining force against the free market the reform intends. An Icelandic doctor needs
about six years of study plus internship and specialisation, much of it abroad. Since 2008 teachers need a
five-year master's degree. Nurses need four years, lawyers five plus the bar exam, and the trades an
apprenticeship. Where the barrier is high, the round finds high pay that cannot be competed away within the
model's horizon. Where it is low, the profession's pay is set by people moving in from elsewhere.

## The data

1. **ISSP 2015, Work Orientations IV** (GESIS ZA6770, doi:10.4232/1.12848). Iceland took part: 1,126
   respondents, May to August 2016. The survey asks every item in the first five rows of the table, along with
   occupation coded to ISCO-08 and pay. It gives an Icelandic ranking of meaning and strain for the model's 27
   professions. The data are free but need a GESIS account, which the author has to download with. The 2025 round
   (Work Orientations V) should be used when it is released.
2. **Dur and van Lent (2019, *Industrial Relations*), "Socially useless jobs".** They use the same ISSP item across
   37 countries: 8% of workers call their job useless and 17% are unsure, and the share varies strongly by
   occupation. This gives a cross-check, and occupation-level shares where the Icelandic sample is thin.
3. **European Working Conditions Survey.** Eurofound's indices of job quality (physical environment, work intensity,
   working-time quality, skills and discretion, prospects) are published by occupation. Iceland is not in the
   sample. Norway is, and serves as the Nordic stand-in for strain and hours.
4. **UK Annual Population Survey, wellbeing by occupation** (What Works Centre for Wellbeing, 2023). It reports
   "worthwhile" and life-satisfaction scores for 369 occupations. Caring, leisure and other services, and health,
   welfare and teaching, report the most worthwhile work; sales the least. This is a second check on meaning.
5. **Qualification barriers.** Years of training and licensing for each profession come from Iceland's own rules
   (the Education Act for teachers, the Medical Directorate's licensing, the bar, and the trades' journeyman
   examinations). Entry quotas, such as the medical faculty's numerus clausus, set the fastest rate at which supply
   can grow.

## Turning ratings into the model's traits

* Average the ISSP items by profession and survey-weight them, shrinking small cells towards the major ISCO group.
  Scale the result to 0-1 to replace `disamenity` and `meaning`.
* Fix the money value of a step on each scale from the willingness-to-pay estimates above. For example, one step of
  unsocial hours is worth about 20% of pay.
* Calibrate the remaining free scale on today's market. With today's frictions, the traits must reproduce today's
  small differentials (Bonhomme and Jolivet). The round then shows what they become once frictions fall.
* Replace the 0-1-2 education rule with years of training and an entry rate per profession.

## The survey's ranking (2.1)

`scripts/job_traits.py` builds the ranking from ISSP 2015. It uses the Icelandic sample (907 respondents with a
coded occupation) and the other four Nordic samples (about 4,500 more). Each ISCO-08 code is mapped to one of the
model's 27 professions.

* **Meaning** is the mean of four answers: "my job is interesting", "I can help other people", "my job is useful
  to society" and "I am proud of the type of work I do".
* **Unpleasantness** is the mean of four parts:
  * hard physical work;
  * stress;
  * the job's demands getting in the way of family life;
  * unsocial hours, which is itself the mean of weekend work and a schedule that changes or is set at short
    notice.

Iceland's figure for each profession is shrunk towards the Nordic one. Thin Nordic cells are shrunk in turn
towards their ISCO major group: refuse collectors, for example, have two respondents. The result is put on the
mean and spread of the old judgements, so the preference weights fitted to those still apply.

What it shows:

* **Meaning matches the judgements closely** (correlation 0.82), and it tracks job satisfaction (0.71). Care,
  health and teaching are at the top. Fish processing, refuse collection, elementary work and waiting tables are
  at the bottom.
* **Unpleasantness does not match well** (0.46). People in professional jobs report a lot of stress and pressure
  on family life: nurses, care assistants, pilots and air-traffic controllers rank among the most strained,
  doctors are above the middle, and cleaners are near the middle. Waiters rank as the most strained of all,
  through weekends, irregular hours and physical work. The judgements had counted physical work almost alone. The
  survey counts the strain of demanding work as well, which is closer to what the reform argues.
* Barely any of this shows in today's pay (Bonhomme and Jolivet). Survey satisfaction is only weakly lower where
  the work is more strained (-0.23).

The survey's figures are in `data/processed/job_traits.json`, with each profession's sample sizes and its
Icelandic weight.

## The round with a choice of profession (built 2026-10-30)

The first build of the round inverted the pay structure. It let everyone decide again whether to
work, but not which profession to work in. Two causes were found:

* **The pay search, not only the missing choice.** The yearly solver gives a profession whose gap does not seem
  to answer its pay its whole remaining push at once. With the round's 400 rounds and wide window, that threw
  professions from one bound to the other: lawyers went from 2.7 to 0.02 times today's rate, waiters to 10 times.
  In the round each profession now keeps a bracket. The bracket's low end is the highest rate found short of
  workers, and its high end the lowest rate found with too many. A step that would leave the bracket goes to its
  middle instead. The yearly solve is unchanged.
* **No choice of profession.** `src/ubisim/abm/sorting.py` adds one.
  * Each person chooses among the professions their education allows. Licensed professions (doctors, nurses,
    teachers, lawyers, pilots and controllers) keep or lose their people but take no newcomers.
  * A profession is weighed by the surplus a job there adds over doing without one, at its pay, meaning and
    strain, taken as a log.
  * Constants per education level and profession reproduce today's mix under today's rules and pay.
  * A switching cost is set so that 4% would move in a round where nothing changed. A scale is set so that a
    profession's headcount answers its relative pay with elasticity 1. Both are estimates and levers.
  * Pay is cleared, people choose at that pay, and pay is cleared again, up to eight times (below). With
    nothing changed nobody moves.
  * A first version added the constants to the worth instead of scaling a log surplus. A payment shrinks every
    job's money advantage, and the constants then pulled people towards today's low-paid professions whatever
    they paid.

### The second build: a round without time, a state that bargains, work that gets lighter

The author asked for three changes, and building them showed a fourth was needed.

* **The round takes no time.** It is held before the reform's first year (`model.haggle`), not within it. The
  reform's rules are in force at today's prices; nobody ages, nothing is produced, and no inflation is expected
  within it. The first year then starts from the pay, professions and contracts the round set, and everyone
  chooses again at that pay.
* **The state does not fill every post at any price.** It seeks fewer public posts the dearer they become: the
  posts sought are those it would seek at today's pay times the pay asked, relative to today's, to the power
  −0.3 (`labour.state_pay_resistance`). At 1.5 times today's real pay it seeks about 12% fewer. The posts it
  leaves empty count as unfilled, and they add to the work of those who are there. The 0.3 is an estimate; the
  state's own demand elasticity for staff is not well measured.
* **Where posts fill, the work gets lighter.** The work per person follows staffing. A profession short of
  people carries more work per head, and one whose posts all fill carries less, down to a quarter less strain
  (`labour.workload_relief_max`). Lighter work is weighed in the choice of profession like any strain, so more
  people choose the job, and its pay falls. In the round the work is updated between sweeps, so this plays out
  in the round itself; afterwards it is updated every year.
* **The round did not settle.** In the first build, the last sweeps still moved some professions' pay by a fifth
  to nearly double. Supply in the professions anyone may enter (cleaning, driving, child-care, care, refuse)
  answers their pay far more than demand for them does. Pay cleared with everyone where they stood, then a flood
  moved in, then pay fell, and so on: cleaners went 2.8, 1.6, 2.1, 1.6, 2.0 and 0.8 times today's rate over six
  sweeps. Results depended on how many sweeps happened to run. Now:
  * each clearing counts the moves its own pay would bring, using the choice itself with each person's worths
    moved by how they answer that profession's pay (`sorting.anticipated_moves`);
  * the sweeps stop when one leaves every profession's pay within 2% of the last;
  * one last sweep then moves everyone to their choice at that pay, without the damping, and clears pay again,
    so pay and people agree;
  * at most eight sweeps. The reference reform settles in eight, with pay moving 0.4% in the last.
  * The quality check runs the round and requires it to settle, and to leave fewer essential posts unfilled
    than keeping the agreements.
* **A calibration miss, found on the way.** The search for the switching cost stopped at its upper bound, so
  4.4% moved in a round where nothing changed, against the 4% intended. The bound now widens as needed.

**Results, one year, at the cap-350 settings with the payment varied** (real pay against the status quo, and
full-time equivalents in brackets):

| Profession | 200 þús. | 350 | 450 |
|---|---|---|---|
| Nurses and midwives | 1.30 (0.98) | 1.48 (0.99) | 1.63 (0.99) |
| Primary and pre-school teachers | 1.26 (1.00) | 1.42 (1.00) | 1.57 (1.00) |
| Doctors | 1.22 (0.98) | 1.42 (0.98) | 1.61 (0.97) |
| Care assistants | 1.15 (1.02) | 1.27 (1.04) | 1.35 (0.99) |
| Child-care workers | 1.13 (1.04) | 1.22 (1.06) | 1.33 (1.06) |
| Cleaners | 1.14 (1.11) | 1.20 (1.18) | 1.36 (1.27) |
| Managers | 1.00 (0.83) | 1.03 (0.73) | 1.05 (0.66) |
| Engineers and IT | 1.02 (0.84) | 1.05 (0.74) | 1.06 (0.66) |
| Cooks | 0.97 (0.82) | 0.99 (0.71) | 0.99 (0.64) |
| Waiters and bar staff | 0.92 (0.62) | 0.92 (0.56) | 0.91 (0.48) |
| *Full-time equivalents per adult* | 0.609 | 0.560 | 0.523 (status quo 0.684) |
| *Budget, year 1, ma.kr.* | +116 | −459 | −873 (status quo −102) |
| *Essential posts unfilled* | 1,235 | 1,622 | 2,005 (status quo 1,155) |

Against the first build, the needed professions gain less pay: teachers 1.42 at 350 þús. where they had 1.93.
That is the state's resistance: rather than pay twice today's rate, it leaves about 700 teaching posts, 220
nursing posts and 400 child-care posts unsought. Fewer posts are filled than in the status quo, and those
there work somewhat harder. The rest of the table moves little.

What it says about the author's questions:

* **The higher the payment, the more pay the needed work commands.** Nursing, teaching and medicine gain a
  quarter in real pay at 200 þús. and three fifths at 450. This is the payment's bargaining power in the model,
  now held back by a state that will not pay any price.
* **Managers are not cut.** Their pay stays at today's while there are fewer of them, a quarter fewer at
  350 þús. Private employers answer dearer labour by employing less, not by paying less.
* **The least demanding jobs are not done for nothing.** Waiters and cooks lose people, and waiters lose a
  little pay, because the private demand for them falls with their price.
* **The cleaners gain most in people** (a fifth more at 350 þús.) and a fifth in pay. Their work is open to
  anyone, so the round fills it.

**Ten years at 350 þús., with the market setting pay after the round:**

| | With the round | Without it | Status quo |
|---|---|---|---|
| Budget, 2035 (ma.kr.) | +152 | +119 | −144 |
| Essential posts unfilled | 1,384 | 3,624 | 1,477 |
| Net income (kr./month) | 888,000 | 864,000 | 789,000 |
| Prices | 1.97 | 1.79 | 1.39 |

The round fills the essential posts about as well as the status quo, against two and a half times as many left
empty without it, and helps the budget, at the cost of prices about a tenth higher. The unfilled posts now
include those the state chooses not to seek; in the first build, which had no such choice, the round left 358.
By the tenth year doctors are at 1.26 times today's real pay, nurses at 1.16, teachers at 1.14. Nurses work
less hard than in the status quo (3% above a normal load against 6%).

The page has the round as a lever, "Pay renegotiated all at once", on in the reform; the Guide asks it as a third
answer to whether the agreements stay.

**Done since the first build:**

* **Strain weighs more.** The weights on meaning and strain are now 1.5 and 2.0 (were 0.6 and 0.8), against
  10.7 on income. The anchor is Mas and Pallais (2017): a schedule an employer sets at short notice is worth
  about 20% of pay to the average worker. On the survey's strain scale an irregular schedule is an eighth of the
  whole (half of the hours part, which is a quarter), so the evidence points to a weight of about 4. It is halved,
  because the survey's "irregular" takes in regular shifts as well. Meaning keeps its ratio to strain.
* **The survey traits are in the model** (`PROFESSION_TRAITS`), and the model is recalibrated with them. The
  quality check passes as before.

**What it still lacks:**

* **The constants** hold both dislike and the inability to get in (talent, hiring, place), as if the first.
* **The state's resistance** (0.3) and the most the work can lighten (a quarter) are estimates, not
  measurements.
* **The switching cost and scale** are estimates. The pay loss on switching, 10%, sits within Kambourov and
  Manovskii (2009): five years in an occupation raise pay by about 12-20%, and the switcher gives that up.

## Sources

- Kambourov, G., & Manovskii, I. (2009). Occupational specificity of human capital. *International Economic
  Review*, 50(1), 63-115. doi:10.1111/j.1468-2354.2008.00524.x
- Maestas, N., Mullen, K. J., Powell, D., von Wachter, T., & Wenger, J. B. (2023). The value of working
  conditions in the United States and implications for the structure of wages. *American Economic Review*, 113(7).
- Mas, A., & Pallais, A. (2017). Valuing alternative work arrangements. *American Economic Review*, 107(12).
- Bonhomme, S., & Jolivet, G. (2009). The pervasive absence of compensating differentials. *Journal of Applied
  Econometrics*, 24(5).
- Lavetti, K. (2023). Compensating wage differentials in labor markets: empirical challenges and applications.
  *Journal of Economic Perspectives*, 37(3).
- Dur, R., & van Lent, M. (2019). Socially useless jobs. *Industrial Relations*, 58(1).
- ISSP Research Group (2017). International Social Survey Programme: Work Orientations IV, ISSP 2015. GESIS
  ZA6770, doi:10.4232/1.12848.
- Eurofound (2014). *Occupational profiles in working conditions: identification of groups with multiple
  disadvantages*.
- What Works Centre for Wellbeing (2023). *Which jobs make us happy?* (UK Annual Population Survey, 2012-2022).
