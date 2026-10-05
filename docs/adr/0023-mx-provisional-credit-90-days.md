# 0023. MX provisional credit covers unrecognized-charge claims within 90 calendar days; the 48 h window is for theft or loss only

- **Status:** Proposed (decision D-028, pending the lead)
- **Date:** 2026-10-04
- **Deciders:** Freddy (pending) · **Owner:** @salazarvalverdeai
- **Related:** spec 02 (AC-03, §4.3, §8 Q3 and Q7) · ADRs 0019 and 0020 (both amended by this record), 0005 · the
  review of PR #67 (task 02b, 2026-10-04)

## Context
- **What the docs said.** Spec 02 AC-03 and §4.3, ADR 0019 (Context and alternatives), ADR 0020 (Context and
  alternatives), the business rules in `CLAUDE.md`, `docs/concepts.md` and `docs/stack.md` all said the same thing.
  In Mexico, the provisional credit by business day 2 applied **only to debit-card charges made within the 48 hours
  before the notice**. Older debit charges and every credit-card charge got only the LTOSF art. 23 ruling (45 days).
  For AR, the clock promised a reimbursement date (BCRA t-pusf item 2.3.5.1) on the same day as the resolution
  (item 3.1.6).
- **Where the 48 h came from.** It came from CONDUSEF's press release of 2018-10-03, *"Cargos no reconocidos en tarjeta
  de débito, se restituirán en dos días hábiles bancarios"*. The release says *"Aplica para operaciones realizadas en
  las 48 horas previas."* That sentence summarizes only fraction I of art. 19 Bis 3, which is the theft or loss case.
  ADR 0019 used the 48 h rule as its example of a condition "our contract had missed". So the fix itself came from a
  summary, which is the risk ADR 0019 exists to prevent.
- **What the official text says.** The quotes are under Sources below.
  - Banxico Circular 3/2012, art. 19 Bis 1, recognizes two kinds of notice: (i) theft or loss of the debit card, and
    (ii) a claim of charges the account holder does not recognize.
  - Art. 19 Bis 3 obliges the bank to credit by the second banking business day after the notice. Fr. I ties the
    48-hour window to notice (i). Fr. II covers notice (ii) when it is filed within **90 Días** of the charge.
  - Art. 2 defines "Días" as calendar days.
  - Art. 19 Bis 4 sets the ruling at 45 Días after the notice, or 180 for operations abroad. If the bank does not
    deliver the ruling in time, the credit becomes final.
  - Banxico Circular 34/2010 (credit cards, as amended by Circular 13/2018) repeats the same structure in numerals 3.3,
    3.4 a) and b), and 3.6. Its window is 90 *días naturales*.
- **AR.** BCRA t-pusf item 3.1.6 requires every query or claim to be resolved within 10 business days. Item 2.3.5.1
  requires reimbursement within those 10 business days, but only for a closed list of amounts the bank itself
  generated: interest, commissions or charges outside the rules, charges above cost or above what was agreed, and
  mis-settled promotions. A third-party charge the customer does not recognize is not clearly on that list.
- **How it was found.** It was found in the T3 work of PR #67 and in the independent 02b review of PR #67. Both
  re-read the primary texts on 2026-10-04, and this record re-read them again on the same day.

## Decision
1. **MX debit and MX credit, claim within 90 calendar days.** When a customer claims a charge they do not recognize,
   and the claim is filed within 90 calendar days of the charge:
   - `credit_deadline` is the **second business day after the notice**: the second *Día Hábil Bancario* for debit
     (Circular 3/2012 art. 19 Bis 3 fr. II) and the second *Día Hábil* for credit (Circular 34/2010 numeral 3.4 b)).
     Both terms are defined by the CNBV's calendar of days the institutions may not close, so the clock uses the same
     MX holiday file for both.
   - `ruling_deadline` is the notice date **+ 45 calendar days**, or **+ 180 calendar days** when the charge was made
     abroad: art. 19 Bis 4 for debit, numeral 3.6 for credit.
   - The bank may skip the credit only by delivering, within that term, a ruling that proves two-factor
     authentication.
   - Provisional credit stays a human decision (constitution rule 6). The clock computes the date. It never grants
     the credit.
2. **Counting.** The charge's age is counted in calendar days between local dates in Mexico City time. Circular 3/2012
   art. 5 refers the circular's times (*horarios*) to Mexico City time; applying it to dates is our inference
   `[assumption]`.
   - Day 90 still qualifies `[assumption]`. It is the reading that gives the earlier deadline.
   - Circular 34/2010 does not define its capitalized "Días" in numeral 3.6, so the 45 days count as calendar days
     `[assumption]`, which also gives the earlier date.
   - Numeral 2.9: when the issuer does not show a charge on the statement where it belongs, the 90 days run from the
     cut date of the statement that does show it. The gold has no statement dates, so the clock counts from the
     charge date. A credit-card claim filed after day 90 is left to the analyst, who closes every case anyway.
3. **MX claim after day 90.** There is no credit deadline. The ruling follows LTOSF art. 23 fr. II: 45 days, counted as
   calendar days `[assumption]` (the earlier date), or 180 calendar days for operations abroad. LTOSF art. 23 fr. I
   has its own 90-day window for the customer, counted from the statement cut date or, where applicable, from the
   operation. The cut date is not in the data, so the clock always gives the ruling date for an older charge
   `[assumption]`, as the comment in PR #67's `policies.yaml` says.
4. **The 48 h window is not modeled.** Fr. I of art. 19 Bis 3 and numeral 3.4 a) apply only to a theft or loss notice.
   Any charge made in the 48 hours before a notice is also within 90 days, so fr. II already covers it once the
   customer claims it.
5. **Dispute types (D-030, default applied pending the lead).** The clock computes the credit date for
   `unrecognized_charge` and `wrongful_charge` alike, but the customer sees it only where the source supports it.
   - **Receipt:** the business-day-2 credit date is shown for an unrecognized charge (art. 19 Bis 1 inciso (ii);
     numeral 3.3 inciso (ii)) and for a duplicate charge, which art. 19 Bis 3 and numeral 3.4 name as a covered
     failure (*"un cargo duplicado indebidamente"*).
   - **Other wrongful-charge types** (a wrong amount, a merchant dispute): the date drives only the analyst SLA
     (spec 02 AC-11) and never reaches the receipt, which shows the ruling date. Under ADR 0019 point 3, a reading
     that is not verified against the text cannot be shown to a customer as a commitment.
   - Until the tools can tell a duplicate from other wrongful charges (specs 03 and 04), a `wrongful_charge` receipt
     shows only the ruling date. Using the credit date for the SLA is the earlier-deadline reading `[assumption]`.
6. **AR.** The clock promises only the **resolution within 10 business days** (t-pusf 3.1.6): `ruling_deadline` =
   notice + 10 business days, and no `credit_deadline`.
   - If the analyst finds that the charge is one the bank itself generated (the list in item 2.3.5.1), the
     reimbursement is due by that same date.
   - That finding is a human decision, so the receipt never promises the customer a reimbursement date.
7. **Labels.** These rows are `[external]`, verified on 2026-10-04 against the rule texts below. Only the items marked
   `[assumption]` above carry that label.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| 90 calendar days for MX debit and credit, per the rule texts; AR resolution only (chosen) | Matches the official texts; gives the earliest legal date; never promises a date the law does not give | Amends two accepted ADRs, AC-03 and `CLAUDE.md`; MX credit needs a new clock entry |
| Keep the 48 h window (status quo) | No change to accepted records | Contradicts art. 19 Bis 3 fr. II. Every claim filed between 48 h and 90 days gets a later deadline than the law, which breaks the "earlier, never later" rule of PR #67 |
| 90 days for debit only, LTOSF ruling for credit (PR #67 as opened) | Smaller change | Circular 34/2010 numeral 3.4 b) gives credit cards the same credit by business day 2, so credit-card deadlines would come later than the law (review finding B1) |
| Keep the 90-day reading labeled `[assumption]` until a lawyer reads it | Cautious | The text is explicit. Under ADR 0019 point 3, a value that is not verified cannot be shown to a customer, so the headline rule would leave the receipt |
| AR: a reimbursement date on every claim (PR #67 as opened) | One date and a stronger promise | Item 2.3.5.1 lists amounts the bank itself generated. Promising reimbursement on third-party fraud is not supported by the text |

## Consequences
- **Spec 02.** AC-03, the MX and AR rows of §4.3, and §8 Q3 and Q7 follow this record (this PR). AC-11 (MX debit SLA:
  priority on business day 1, alert before business day 2) should extend to MX credit claims within 90 days. That
  change is task 02c, together with `case_queue.deadline_sla`.
- **`contracts/policies.yaml` (code PR #67, lead approval under rule 9).** The file needs four changes:
  - MX debit keeps `when_charged_within: {days: 90}` and adds `ruling_abroad: {days: 180, calendar: calendar}`.
  - MX credit gets a first entry with the same 90-day window, the business-day-2 credit and the 45/180 ruling. Its
    source is Circular 34/2010, numerals 3.4 and 3.6.
  - AR keeps the ruling only.
  - Each change comes with tests at the boundaries: day 0, 90 and 91, and a charge abroad.
- **ADR 0019.** Its decision stands and this case strengthens it. Its Context sentence and its "MX 48 h" example are
  corrected here: the 48 h rule was itself the summary error. Lesson: for a legal deadline, read the rule's own text
  (the official gazette or the regulator's compiled text). A press release or FAQ may be cited next to it, never
  instead of it.
- **ADR 0020.** The replay date stays **`DEMO_TODAY = 2026-06-01`**. The reasons:
  - It is the first day after the gold window (gold contract R1: `transaction_date < 2026-06-01`).
  - It is a Monday.
  - It is already wired into spec 02, `CLAUDE.md`, `.env.example`, and `clock.DEMO_TODAY` and its tests in PR #67.

  Its MX-48 h rationale is replaced:
  - In replay, **every MX charge dated 2026-03-03 to 2026-05-31** is at most 90 calendar days before the notice, so
    debit and credit charges alike get the business-day-2 credit. 2026-03-03 is day 90 and is included
    `[assumption]`.
  - The argument "on 2026-06-03 the MX rule never applies" no longer holds: that date would qualify charges from
    2026-03-05 on.
  - **Live mode still needs the synthetic recent transactions.** On 2026-10-05 the 90-day window starts on 2026-07-07,
    and every gold charge is older than that. So in October only the synthetic recent transactions (ADR 0020) show
    the business-day-2 credit.
  - ADR 0020's worked example still holds: a notice on 2026-06-01 about a charge on 2026-05-31 gives a credit by
    2026-06-03.
- **Docs.** `CLAUDE.md` business rules, `docs/concepts.md` and `docs/stack.md` drop the 48 h statements (this PR).
  Customer-facing text (spec 04 templates) must not mention 48 hours.
- **Harder.** More MX cases now carry a day-2 credit date, so the analyst queue gets more urgent MX work. In replay,
  that covers most MX evaluation cases.

## Confidence
High on the reading. The rule texts are explicit and were read three times on 2026-10-04: by the PR #67 author, by the
02b reviewer and by this record. Medium on the `[assumption]` items and the statement-date edge case: day 90
included, local dates from art. 5, the 45 days of Circular 34/2010 and of LTOSF counted as calendar days, the LTOSF
ruling always given, and the credit date driving the SLA for every `wrongful_charge`. Each of them is the reading
that gives the earlier deadline. D-030 (what the receipt shows for a `wrongful_charge`) is a default pending the
lead. Revisit if Banxico amends Circular 3/2012 or
34/2010, if Banxico or CONDUSEF publishes an interpretation that differs, or if the organizers ask us to follow a
different reading.

## Sources
All were checked on 2026-10-04. The quotes are verbatim.
- **Banxico, Circular 3/2012, compiled text through Circular 11/2026:**
  https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-3-2012/%7B4E0281A4-7AD8-1462-BC79-7F2925F3171D%7D.pdf
  - Art. 2: *"Días: a los días del año calendario."* · *"Días Hábiles Bancarios: a los días en que las Instituciones no
    estén obligadas a cerrar sus puertas ni a suspender operaciones, en términos de las disposiciones de carácter
    general que, para tal efecto, emita la Comisión Nacional Bancaria y de Valores."*
  - Art. 5: *"Los horarios que se mencionan en las presentes Disposiciones estarán referidos al huso horario de la
    Ciudad de México"*.
  - Art. 19 Bis 1: *"… avisos de: (i) robo o extravío de la Tarjeta de débito correspondiente, o (ii) reclamaciones por
    cargos a dicha Cuenta que no reconozca como propios."*
  - Art. 19 Bis 3: *"… estará obligada a abonar en la respectiva Cuenta de Depósito, a más tardar el segundo Día Hábil
    Bancario siguiente a la recepción de dicho aviso, el monto equivalente a aquellos cargos realizados en esa Cuenta
    que sean objeto del aviso de que se trate, siempre y cuando:"*
    - fr. I: *"Los referidos cargos correspondan a operaciones realizadas durante las cuarenta y ocho horas previas a
      la presentación del aviso a que se refiere el artículo 19 Bis 1, primer párrafo, inciso (i) …"*
    - fr. II: *"Si el aviso corresponde al indicado en el artículo 19 Bis 1, primer párrafo, inciso (ii), relativo a la
      reclamación por cargos que el cuentahabiente no reconozca como propios, este se haya presentado a la
      Institución dentro de un plazo de noventa Días posteriores a la fecha en que se realizó el cargo no
      reconocido."*
    - *"El plazo de noventa Días a que se refiere la fracción II de este artículo comenzará a contar a partir de la
      fecha en que se realizó el cargo no reconocido …"*
    - The bank may skip the credit only by delivering the two-factor ruling in that term, *"a menos de que exista
      evidencia de que el cargo fue producto de una falla operativa … como sería el caso de un cargo duplicado
      indebidamente."*
  - Art. 19 Bis 4: the ruling is due *"dentro de un plazo de cuarenta y cinco Días contado a partir de la fecha en la
    que haya recibido el aviso a que se refiere el artículo 19 Bis 1"*.
    - *"Tratándose de reclamaciones relativas a operaciones realizadas en el extranjero, el plazo señalado en el
      párrafo anterior será de ciento ochenta Días."*
    - *"… no entregan el mencionado dictamen en los términos señalados, el abono realizado previamente en términos del
      artículo anterior quedará firme y no podrá revertirse."*
  - Transitorio Segundo of Circular 14/2018: the business-day-2 credit *"entrará en vigor el 26 de septiembre de 2019."*
- **DOF, Circular 14/2018 (2018-10-03):** https://dof.gob.mx/nota_detalle.php?codigo=5539863&fecha=03/10/2018 (the
  `www.` host fails TLS).
- **Banxico, Circular 34/2010 (*Reglas de Tarjetas de Crédito*), compiled text through Circular 13/2018 (DOF
  2018-10-03):**
  https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-34-2010/%7B0C55B906-6DB4-6B88-FED0-67987E9FB3CC%7D.pdf
  - Numeral 3.3: *"avisos de: (i) robo o extravío de la Tarjeta de Crédito correspondiente, o (ii) reclamaciones por
    cargos a la Cuenta que no reconozcan como propios."*
  - Numeral 3.4: *"… estará obligada a abonar, en la respectiva Cuenta, a más tardar el segundo Día Hábil siguiente a
    la recepción de dicho aviso …"*
    - a) applies to *"operaciones realizadas durante las cuarenta y ocho horas previas a la presentación del aviso a
      que se refiere el numeral 3.3, primer párrafo, inciso (i)"*.
    - b): *"Si el aviso corresponde al indicado en el numeral 3.3, primer párrafo, inciso (ii), relativo a la
      reclamación por cargos que el Tarjetahabiente no reconozca como propios, este se haya presentado a la Emisora
      dentro de un plazo de noventa días naturales posteriores a la fecha en que se realizó el cargo no reconocido."*
  - Numeral 3.6: the ruling is due *"dentro de un plazo de cuarenta y cinco Días contado a partir de la fecha en la
    que se haya recibido el aviso a que se refiere el numeral 3.3"*.
    - *"En caso de reclamaciones relativas a operaciones realizadas en el extranjero, el plazo previsto en el párrafo
      anterior será de ciento ochenta días naturales."*
    - If the ruling is late, *"el abono realizado previamente por ésta quedará firme, por lo que no podrá
      revertirse."*
  - Numeral 2.9: when a charge is not reflected on the statement, *"el plazo de noventa días naturales … comenzará a
    correr a partir de la fecha de corte del estado de cuenta que lo refleje."*
  - Transitorio Segundo of Circular 13/2018: the business-day-2 credit *"entrará en vigor el 26 de septiembre de 2019."*
- **LTOSF art. 23, Orden Jurídico Nacional (texto vigente, last reform DOF 2024-01-24):**
  https://www.ordenjuridico.gob.mx/Documentos/Federal/pdf/wo46.pdf
  - fr. I: *"… dentro del plazo de noventa días naturales contados a partir de la fecha de corte o, en su caso, de la
    realización de la operación o del servicio."*
  - fr. II: *"… la institución tendrá un plazo máximo de cuarenta y cinco días para entregar al Cliente el dictamen
    correspondiente … En el caso de reclamaciones relativas a operaciones realizadas en el extranjero, el plazo
    previsto en este párrafo será hasta de ciento ochenta días naturales."*
- **BCRA, *Protección de los usuarios de servicios financieros*, texto ordenado al 06/05/26:**
  https://www.bcra.gob.ar/archivos/Pdfs/texord/t-pusf.pdf
  - Item 3.1.6: *"Toda consulta o reclamo deberá ser definitivamente resuelta/o dentro del plazo máximo de diez (10)
    días hábiles, excepto para la situación prevista en el punto 2.3.5. …"*
  - Item 2.3.5.1 lists the amounts it covers: interest, commissions or charges that break items 2.3.2–2.3.4; charges
    above the third party's cost; commissions above the BCRA maximum; interest above the card cap; amounts above what
    was agreed; *"otros generados en forma impropia por su naturaleza"*; and mis-settled promotions. It then says
    these amounts *"deberá serle reintegrado dentro de: los diez (10) días hábiles siguientes al momento de la
    presentación del reclamo ante el sujeto obligado, de conformidad con las previsiones del punto 3.1.6."*
- **CONDUSEF press release, 2018-10-03 (the origin of the 48 h rule):**
  https://www.gob.mx/condusef/prensa/cargos-no-reconocidos-en-tarjeta-de-debito-se-restituiran-en-dos-dias-habiles-bancarios?idiom=es
  - It says *"Aplica para operaciones realizadas en las 48 horas previas."* That sentence describes fr. I only.
- **Internal:**
  - The review of PR #67 (task 02b, 2026-10-04): findings B1, D1, D2 and R1, and answer Q2.
  - `contracts/gold_contract.md` R1 (the gold ends on 2026-05-31).
  - ADR 0019 and ADR 0020.
