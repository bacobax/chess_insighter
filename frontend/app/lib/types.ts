export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type Hparams = Record<string, JsonValue>;

export type GameSummary = {
  id: string | null;
  url: string | null;
  result: "win" | "loss" | "draw" | "unknown";
  player_username: string;
  player_color: "white" | "black";
  player_elo_before: number | null;
  player_elo_after: number | null;
  opponent_username: string | null;
  opponent_elo_before: number | null;
  opponent_elo_after: number | null;
  opponent_result: string | null;
  end_time: number | null;
  end_time_iso: string | null;
  time_class: string | null;
  time_control: string | null;
  rated: boolean | null;
  opening_eco: string | null;
  opening_name: string | null;
};

export type GamesQueryRequest = {
  username: string;
  page: number;
  page_size: number;
  time_classes?: string[] | null;
  rated_filter?: boolean | null;
  since_year?: number | null;
  since_month?: number | null;
  until_year?: number | null;
  until_month?: number | null;
};

export type GamesQueryResponse = {
  items: GameSummary[];
  page: number;
  page_size: number;
  has_more: boolean;
  total_loaded: number;
};

export type MetricPoint = {
  key: string;
  label: string;
  value: number | null;
  direction: "higher" | "lower";
};

export type OpeningCount = {
  name: string;
  count: number;
  color: "white" | "black";
};

export type OpeningFeatureSet = {
  opening_name: string;
  color: "white" | "black";
  count: number;
  family_name: string | null;
  features: MetricPoint[];
};

export type OpeningMatch = {
  opening_name: string;
  similarity_score: number | null;
  weighted_cosine_score: number | null;
  dot_product_score: number | null;
  match_mode: "cosine" | "dot_product";
  structure_distribution_similarity: number | null;
  target_color: "white" | "black" | "both" | null;
  used_vector_color: "white" | "black" | "global";
  eco_values: string | null;
  line_count: number | null;
  representative_pgn: string | null;
  representative_uci: string | null;
  fen: string | null;
  used_features: string[];
};

export type OpeningMatchMode = "cosine" | "dot_product";

export type OpeningReportGroup = {
  opening_characteristics: MetricPoint[];
  top_opening_features: OpeningFeatureSet[];
  top_opening_matches: OpeningMatch[];
};

export type ReportCharts = {
  skill_profile: MetricPoint[];
  favourite_openings: OpeningCount[];
  top_opening_features: OpeningFeatureSet[];
  opening_characteristics: MetricPoint[];
  top_opening_matches: OpeningMatch[];
  opening_report_groups: Record<"white" | "black" | "both", OpeningReportGroup>;
  opening_components: MetricPoint[];
  time_management_indicators: MetricPoint[];
  advantage_capitalization_components: MetricPoint[];
  resourcefulness_components: MetricPoint[];
  game_analysis_components: MetricPoint[];
  average_time_by_complexity: MetricPoint[];
};

export type ReportPayload = {
  metadata: Record<string, JsonValue>;
  statistics_bundle: Record<string, JsonValue>;
  charts: ReportCharts;
};

export type ReportBuildRequest = {
  username: string;
  hparams: Hparams;
  max_games: number;
  engine_depth: number;
  use_engine: boolean;
  refresh_cache: boolean;
  target_color?: "white" | "black" | "both";
  time_classes?: string[] | null;
  rated_filter?: boolean | null;
  since_year?: number | null;
  since_month?: number | null;
  until_year?: number | null;
  until_month?: number | null;
};

export type OpeningMatchRequest = {
  cache_hash: string;
  match_mode: OpeningMatchMode;
  target_color: "white" | "black" | "both";
  limit?: number;
};

export type OpeningMatchResponse = {
  top_opening_matches: OpeningMatch[];
  match_mode: OpeningMatchMode;
  target_color: "white" | "black" | "both";
};

export type ReportBuildResponse = {
  cache_hash: string;
  cache_hit: boolean;
  normalized_hparams: Hparams;
  report: ReportPayload;
};

// ---------------------------------------------------------------------------
// Opening Study Suggestion Tree
// ---------------------------------------------------------------------------

export type TargetColor = "white" | "black";
export type StudySimilarityType = "cosine" | "dot_product";

export type MatcherFeatureKey =
  | "tactical_density"
  | "quiet_position_density"
  | "king_safety_risk"
  | "early_castling_tendency"
  | "opposite_side_castling_tendency"
  | "middlegame_complexity"
  | "pawn_structure_sharpness"
  | "material_imbalance"
  | "endgame_likelihood_proxy";

export type OpeningStudyWeights = {
  playerStyleMatch?: number;
  aggressiveness?: number;
  gambleness?: number;
  systemness?: number;
  memorySimplicity?: number;
};

export type OpeningStudyTreeChildrenRequest = {
  /** Preferred source: hash from a /api/report/build response. Uses the
   *  player vector computed from the exact games+filters of that report. */
  cacheHash?: string;
  /** Fallback: username lookup in the flat player_vectors.json cache.
   *  Ignores game filters; uses whichever vector was cached most recently. */
  username?: string;
  playerVectorCachePath?: string;
  openingVectorsPath?: string;
  targetColor: TargetColor;
  prefixUci: string[];
  topK: number;
  opponentTopK: number;
  weights?: OpeningStudyWeights;
  similarityType?: StudySimilarityType;
  weightedMatching?: boolean;
  matcherWeights?: Partial<Record<MatcherFeatureKey, number>>;
};

export type MetricComponent = {
  key: string;
  label: string;
  value: number;
  weight: number;
  rawValue?: number;
  rawUnit?: string;
};

export type StyleMatchComponent = {
  key: string;
  label: string;
  playerValue: number;
  openingValue: number;
  weight: number;
};

export type NodeBreakdown = {
  aggressiveness?: MetricComponent[];
  gambleness?: MetricComponent[];
  memoryComplexity?: MetricComponent[];
  systemness?: MetricComponent[];
  playerStyleMatch?: StyleMatchComponent[];
  openingFeatures?: Record<string, number>;
};

export type OpeningStudyTreeNode = {
  id: string;
  moveUci: string;
  moveSan: string;
  fen: string;
  prefixUci: string[];
  compatibleLineCount: number;
  openingNames: string[];
  representativeUci?: string | null;
  representativePgn?: string | null;
  playerStyleMatch: number;
  aggressiveness: number;
  gambleness: number;
  memoryComplexity: number;
  systemness: number;
  studyScore: number;
  sideToMove: "white" | "black";
  targetColor: TargetColor;
  isTargetMove: boolean;
  boardPreviewFen: string;
  stats: {
    playerStyleMatch: number;
    aggressiveness: number;
    gambleness: number;
    memoryComplexity: number;
    systemness: number;
  };
  breakdown?: NodeBreakdown;
};

export type OpeningStudyTreeChildrenResponse = {
  targetColor: TargetColor;
  prefixUci: string[];
  children: OpeningStudyTreeNode[];
  vectorSource?: string | null;
  playerVector?: Record<string, number> | null;
};
