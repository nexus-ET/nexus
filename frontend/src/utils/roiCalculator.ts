/** ROI calculator benchmark types + cash-flow / NPV math. */

export type RoiSensitivity = 'conservative' | 'expected' | 'optimistic';

export interface RoiBenchmarkInputs {
  currency: string;
  program_years: number;
  annual_tuition: number;
  visa_fees: number;
  health_insurance_annual: number;
  books_supplies_annual: number;
  monthly_rent: number;
  monthly_groceries: number;
  monthly_transit: number;
  monthly_other_living: number;
  scholarship_annual: number;
  part_time_earnings_annual: number;
  destination_starting_salary: number;
  destination_salary_growth: number;
  destination_effective_tax_rate: number;
  home_counterfactual_salary: number;
  home_salary_growth: number;
  home_effective_tax_rate: number;
  career_horizon_years: number;
  discount_rate: number;
}

export interface RoiBenchmarkResponse {
  country_code: string;
  country_iso2: string;
  metro_key?: string | null;
  location_label: string;
  institution_id?: number | null;
  institution_name?: string | null;
  as_of: string;
  disclaimer: string;
  inputs: RoiBenchmarkInputs;
  notes: string[];
}

export interface RoiYearPoint {
  year: number;
  label: string;
  phase: 'study' | 'career';
  abroadNet: number;
  homeNet: number;
  abroadCumulative: number;
  homeCumulative: number;
  differentialCumulative: number;
  abroadIncome: number;
  abroadExpense: number;
}

export interface RoiComputation {
  totalInvestment: number;
  livingAnnual: number;
  educationAnnualGross: number;
  abroadAfterTaxEarnings: number;
  homeAfterTaxEarnings: number;
  netLifetimeGain: number;
  roiPercent: number;
  npvDifferential: number;
  breakEvenYear: number | null;
  breakEvenLabel: string;
  series: RoiYearPoint[];
}

function afterTax(gross: number, taxRate: number): number {
  return gross * (1 - Math.min(Math.max(taxRate, 0), 0.6));
}

export function applySensitivity(
  inputs: RoiBenchmarkInputs,
  sensitivity: RoiSensitivity
): RoiBenchmarkInputs {
  const next = { ...inputs };
  if (sensitivity === 'conservative') {
    next.destination_starting_salary *= 0.85;
    next.destination_salary_growth = Math.max(0, next.destination_salary_growth - 0.01);
    next.monthly_rent *= 1.1;
    next.monthly_groceries *= 1.1;
    next.monthly_transit *= 1.1;
    next.monthly_other_living *= 1.1;
  } else if (sensitivity === 'optimistic') {
    next.destination_starting_salary *= 1.15;
    next.destination_salary_growth += 0.01;
    next.monthly_rent *= 0.95;
    next.monthly_groceries *= 0.95;
    next.monthly_transit *= 0.95;
    next.monthly_other_living *= 0.95;
  }
  return next;
}

export function computeRoi(inputs: RoiBenchmarkInputs): RoiComputation {
  const years = Math.max(1, Math.round(inputs.program_years));
  const horizon = Math.max(1, Math.round(inputs.career_horizon_years));
  const r = Math.max(0, inputs.discount_rate);

  const livingAnnual =
    (inputs.monthly_rent +
      inputs.monthly_groceries +
      inputs.monthly_transit +
      inputs.monthly_other_living) *
    12;

  const educationAnnualGross =
    inputs.annual_tuition +
    inputs.health_insurance_annual +
    inputs.books_supplies_annual +
    livingAnnual;

  const educationAnnualNet =
    educationAnnualGross - inputs.scholarship_annual - inputs.part_time_earnings_annual;

  const totalInvestmentClamped = Math.max(
    inputs.visa_fees,
    educationAnnualNet * years + inputs.visa_fees
  );

  const series: RoiYearPoint[] = [];
  let abroadCum = 0;
  let homeCum = 0;
  let abroadEarningsSum = 0;
  let homeEarningsSum = 0;
  let npv = 0;
  let breakEvenYear: number | null = null;

  const totalYears = years + horizon;

  for (let t = 1; t <= totalYears; t++) {
    const isStudy = t <= years;
    let abroadIncome = 0;
    let abroadExpense = 0;
    let abroadNet = 0;
    let homeNet = 0;

    if (isStudy) {
      abroadExpense = educationAnnualGross;
      abroadIncome = inputs.scholarship_annual + inputs.part_time_earnings_annual;
      abroadNet = abroadIncome - abroadExpense - (t === 1 ? inputs.visa_fees : 0);

      const homeGross =
        inputs.home_counterfactual_salary *
        Math.pow(1 + inputs.home_salary_growth, t - 1);
      homeNet = afterTax(homeGross, inputs.home_effective_tax_rate);
      homeEarningsSum += homeNet;
    } else {
      const careerYear = t - years;
      const abroadGross =
        inputs.destination_starting_salary *
        Math.pow(1 + inputs.destination_salary_growth, careerYear - 1);
      abroadIncome = afterTax(abroadGross, inputs.destination_effective_tax_rate);
      abroadExpense = 0;
      abroadNet = abroadIncome;
      abroadEarningsSum += abroadIncome;

      const homeGross =
        inputs.home_counterfactual_salary *
        Math.pow(1 + inputs.home_salary_growth, t - 1);
      homeNet = afterTax(homeGross, inputs.home_effective_tax_rate);
      homeEarningsSum += homeNet;
    }

    abroadCum += abroadNet;
    homeCum += homeNet;
    const differentialCumulative = abroadCum - homeCum;
    npv += (abroadNet - homeNet) / Math.pow(1 + r, t);

    if (breakEvenYear == null && differentialCumulative >= 0 && t > years) {
      breakEvenYear = t;
    }

    series.push({
      year: t,
      label: isStudy ? `Y${t} study` : `Y${t} career`,
      phase: isStudy ? 'study' : 'career',
      abroadNet,
      homeNet,
      abroadCumulative: abroadCum,
      homeCumulative: homeCum,
      differentialCumulative,
      abroadIncome,
      abroadExpense,
    });
  }

  const netLifetimeGain = abroadEarningsSum - homeEarningsSum - totalInvestmentClamped;
  const roiPercent =
    totalInvestmentClamped > 0 ? (netLifetimeGain / totalInvestmentClamped) * 100 : 0;

  let breakEvenLabel = 'Not within modelled horizon';
  if (breakEvenYear != null) {
    const postGrad = breakEvenYear - years;
    breakEvenLabel =
      postGrad <= 0
        ? `Year ${breakEvenYear} (during / end of study)`
        : `${postGrad} year${postGrad === 1 ? '' : 's'} after graduation (model year ${breakEvenYear})`;
  }

  return {
    totalInvestment: totalInvestmentClamped,
    livingAnnual,
    educationAnnualGross,
    abroadAfterTaxEarnings: abroadEarningsSum,
    homeAfterTaxEarnings: homeEarningsSum,
    netLifetimeGain,
    roiPercent,
    npvDifferential: npv,
    breakEvenYear,
    breakEvenLabel,
    series,
  };
}

export function formatMoney(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${currency} ${Math.round(value).toLocaleString()}`;
  }
}
