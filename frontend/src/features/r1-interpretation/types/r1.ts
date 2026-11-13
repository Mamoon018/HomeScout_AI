/** Output of R1's extraction step, as the run view returns it. */
export type AmbiguityFlag = {
  /** The renter's own words that R1 could not pin down. */
  phrase: string
  target: 'category' | 'characteristic' | 'persona'
  category: string | null
  category_id: number | null
  characteristic: string | null
}

export type ExplicitCategory = {
  name: string
  category_id: number
  characteristics: string[]
}

export type ExtractionOutput = {
  persona_facts: string[]
  ambiguity_flags: AmbiguityFlag[]
  explicit_categories: ExplicitCategory[]
}

export type MetricDepth = 'basic_profile' | 'operating_details' | 'specific_attributes'

export type PredefinedMetric = {
  band: MetricDepth
  label: string
  resolution_source: { tool: string; target: string }
}

export type SpecificMetric = {
  band: MetricDepth
  unit: string | null
  label: string
  question: string
  /** `number_with_unit`, `boolean`, `enum` or `date_time` today; kept open so a new one still renders. */
  value_type: string
  /** The fixed answers of an `enum` check; empty for every other type. */
  enum_values: string[]
  null_policy: string
  verification: string
  evidence_class: 'factual' | 'experiential'
  resolution_source: {
    web_target: string | null
    review_target: string | null
    scrape_target: string | null
  }
}

/** One category R1 will look for, with the facts agents will collect about its places. */
export type CategoryMetricPlan = {
  depth: MetricDepth
  category_id: number
  taxonomy_node: string
  specific_metrics: SpecificMetric[]
  predefined_metrics: PredefinedMetric[]
}

/** The stage the R1 section is in. */
export type R1Phase = 'idle' | 'extracting' | 'asking' | 'planning' | 'done'
